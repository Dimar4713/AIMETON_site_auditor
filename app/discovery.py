from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.heuristics import heuristic_analysis
from app.hunter_forensic_trace import HunterForensicTrace
from app.hunter_handbook import OPPORTUNITY_PATTERNS, resolve_industries
from app.hunter_query_intelligence import generate_hunter_query_plan
from app.models import HuntCandidate, HuntFunnel, HuntRequest, HuntResult
from app.scraper import FetchError, fetch_site
from app.search_gateway import (
    SearchDiagnostics,
    SearchRequest,
    get_search_gateway,
    search_policy_from_env,
)
from app.trace_ledger import TraceState


EXCLUDED_HOSTS = {
    "vk.com",
    "t.me",
    "youtube.com",
    "rutube.ru",
    "instagram.com",
    "facebook.com",
    "2gis.ru",
    "yandex.ru",
    "google.com",
    "avito.ru",
    "hh.ru",
}

COMMERCIAL_MARKERS = ("каталог", "товар", "оборудован", "услуг", "подбор", "расчет", "заказать")
COMPLEXITY_MARKERS = ("опт", "производ", "монтаж", "проект", "комплектац", "прайс")


@dataclass(frozen=True)
class PreScoreResult:
    score: int | None
    status: str
    factors: dict[str, int | None]
    reasons: list[str]


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _build_queries(req: HuntRequest) -> list[str]:
    selected = resolve_industries(req.industries)
    queries: list[str] = []
    seen: set[str] = set()

    def add(query: str) -> None:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen and len(queries) < req.max_queries:
            seen.add(normalized)
            queries.append(normalized)

    for industry in selected:
        variants = [industry["name"], *industry["aliases"]]
        for variant in variants[:4]:
            add(f'{variant} {req.region} официальный сайт компания')
            if req.search_zone:
                add(f'{variant} {req.search_zone} официальный сайт')

        for signal_id in industry.get("signals", [])[:3]:
            signal = OPPORTUNITY_PATTERNS.get(signal_id, signal_id)
            add(f'{industry["name"]} {signal} {req.region} компания')

    for focus in req.focus:
        add(f'{focus} {req.region} компания официальный сайт')

    return queries


def _industry_markers(req: HuntRequest) -> list[str]:
    """Return bounded lexical markers from the normalized user-requested industry.

    We intentionally derive these from the actual requested values rather than every
    broad handbook alias. For example a dentistry hunt should not receive an
    industry-match merely because a result contains the generic word `клиника`.
    """
    markers: list[str] = []
    seen: set[str] = set()
    for industry in req.industries:
        normalized = " ".join(industry.casefold().replace("ё", "е").split())
        if not normalized:
            continue
        candidates = [normalized]
        for token in normalized.replace(",", " ").split():
            clean = token.strip("-—–()[]{}.,:;!?")
            if len(clean) >= 5:
                stem_length = max(5, len(clean) - 3)
                candidates.append(clean[:stem_length])
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                markers.append(candidate)
    return markers[:20]


def _pre_score(req: HuntRequest, title: str, snippet: str, url: str) -> PreScoreResult:
    host = _domain(url)
    title = title.strip()
    snippet = snippet.strip()
    factors: dict[str, int | None] = {
        "region_match": None,
        "industry_match": None,
        "commercial_choice": None,
        "commercial_complexity": None,
        "focus_match": None,
        "local_domain": None,
    }
    reasons: list[str] = []

    if not host or not (title or snippet):
        reasons.append("недостаточно данных: отсутствует домен либо текст поискового результата")
        return PreScoreResult(None, "insufficient_data", factors, reasons)

    haystack = f"{title} {snippet} {url}".casefold().replace("ё", "е")
    region_tokens = [token for token in req.region.replace(",", " ").casefold().split() if len(token) > 3]
    if region_tokens:
        factors["region_match"] = 25 if any(token in haystack for token in region_tokens) else 0
        if factors["region_match"]:
            reasons.append("обнаружено соответствие территории охоты")

    industry_markers = _industry_markers(req)
    if industry_markers:
        factors["industry_match"] = 25 if any(marker in haystack for marker in industry_markers) else 0
        if factors["industry_match"]:
            reasons.append("обнаружено прямое соответствие заданной отрасли")

    factors["commercial_choice"] = 20 if any(marker in haystack for marker in COMMERCIAL_MARKERS) else 0
    if factors["commercial_choice"]:
        reasons.append("есть признаки коммерческого каталога или сложного выбора")

    factors["commercial_complexity"] = 15 if any(marker in haystack for marker in COMPLEXITY_MARKERS) else 0
    if factors["commercial_complexity"]:
        reasons.append("есть признаки содержательной коммерческой задачи")

    if req.focus:
        factors["focus_match"] = 10 if any(focus.casefold() in haystack for focus in req.focus) else 0
        if factors["focus_match"]:
            reasons.append("обнаружено соответствие заданному фокусу охоты")

    factors["local_domain"] = 5 if host.endswith(".ru") else 0
    if factors["local_domain"]:
        reasons.append("используется домен российской зоны")

    score = 20 + sum(value for value in factors.values() if value is not None)
    return PreScoreResult(min(score, 100), "calculated", factors, reasons)


def _shallow_candidate(
    title: str,
    snippet: str,
    url: str,
    result: PreScoreResult,
    *,
    qualification: str,
    summary: str,
    recommendation: str,
) -> HuntCandidate:
    return HuntCandidate(
        company_name=title or _domain(url),
        url=url,
        source_title=title,
        source_snippet=snippet[:500],
        region_confirmed=None,
        preliminary_score=result.score,
        pre_score_status=result.status,
        pre_score_factors=result.factors,
        deep_analysis_performed=False,
        final_score=result.score,
        qualification=qualification,
        business_summary=summary,
        recommended_solution=recommendation,
        reasons=result.reasons,
        analysis=None,
    )


def _score_metadata(result: PreScoreResult) -> dict[str, object]:
    metadata: dict[str, object] = {
        "pre_score_status": result.status,
        "pre_score_reasons": result.reasons,
    }
    if result.score is not None:
        metadata["pre_score"] = result.score
    for factor, value in result.factors.items():
        metadata[f"factor_{factor}"] = value
    return metadata


async def run_hunt(req: HuntRequest) -> HuntResult:
    mission_id = f"hunt-{uuid4()}"
    correlation_id = f"corr-{uuid4()}"
    trace = HunterForensicTrace(mission_id, correlation_id)

    query_plan = await generate_hunter_query_plan(
        region=req.region,
        industries=req.industries,
        focus=req.focus,
        max_queries=req.max_queries,
    )
    effective_req = req
    if query_plan is not None:
        effective_req = req.model_copy(
            update={
                "region": query_plan.normalized_region,
                "industries": query_plan.normalized_industries or req.industries,
                "focus": query_plan.normalized_focus or req.focus,
            }
        )
        queries = query_plan.query_variants[: req.max_queries]
        query_intelligence_note = (
            "Query Intelligence: LLM-нормализация применена; "
            f"вариантов поиска: {len(queries)}."
        )
        plan_source = "llm"
    else:
        queries = _build_queries(req)
        query_intelligence_note = "Query Intelligence: fallback на детерминированный план поиска."
        plan_source = "deterministic_fallback"

    trace.append(
        "hunt_plan",
        state=TraceState.SUCCEEDED,
        reason_code="hunter_query_plan_built",
        summary="Hunter search plan and effective thresholds prepared",
        counters={
            "query_count": len(queries),
            "results_per_query": req.results_per_query,
            "max_candidates": req.max_candidates,
            "output_limit": req.output_limit,
        },
        metadata={
            "plan_source": plan_source,
            "input_region": req.region,
            "effective_region": effective_req.region,
            "input_industries": req.industries,
            "effective_industries": effective_req.industries,
            "input_focus": req.focus,
            "effective_focus": effective_req.focus,
            "queries": queries,
            "minimum_pre_score": req.minimum_pre_score,
            "deep_audit_score": req.deep_audit_score,
            "concurrency": req.concurrency,
        },
    )

    raw_results: list[dict] = []
    search_diagnostics: list[SearchDiagnostics] = []
    gateway = get_search_gateway()
    policy = search_policy_from_env()
    for query in queries:
        response = await gateway.search(
            SearchRequest(
                query=query,
                limit=req.results_per_query,
                mission_id=mission_id,
                correlation_id=correlation_id,
            ),
            policy,
        )
        search_diagnostics.append(response.diagnostics)
        raw_results.extend(item.as_legacy_dict() for item in response.results)
    aggregate = SearchDiagnostics.aggregate(search_diagnostics)
    if not raw_results:
        funnel = HuntFunnel()
        trace.append(
            "hunt_funnel_complete",
            state=TraceState.SUCCEEDED,
            reason_code="hunter_no_raw_results",
            summary="Hunter completed with no raw search results",
            counters=funnel.model_dump(),
        )
        return HuntResult(
            region=effective_req.region,
            search_zone=req.search_zone,
            queries=queries,
            discovered=0,
            candidates=[],
            funnel=funnel,
            notes=[query_intelligence_note, f"Поиск не дал результатов: gateway state={aggregate.state}."],
            search=aggregate,
        )

    unique: dict[str, dict] = {}
    excluded_count = 0
    duplicate_count = 0
    pool_omitted_count = 0
    for raw_rank, item in enumerate(raw_results, start=1):
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        host = _domain(url)
        identity = host or f"raw-{raw_rank}"
        if not host:
            excluded_count += 1
            trace.append(
                "candidate_excluded",
                state=TraceState.SKIPPED,
                reason_code="missing_candidate_host",
                summary="Search result excluded because no usable host was present",
                identity=identity,
                url=url,
                title=title,
                counters={"raw_rank": raw_rank},
            )
            continue
        if host in EXCLUDED_HOSTS or any(host.endswith(f".{excluded}") for excluded in EXCLUDED_HOSTS):
            excluded_count += 1
            trace.append(
                "candidate_excluded",
                state=TraceState.SKIPPED,
                reason_code="excluded_host",
                summary="Search result excluded by Hunter host policy",
                identity=host,
                url=url,
                title=title,
                counters={"raw_rank": raw_rank},
                metadata={"candidate_host": host},
            )
            continue
        if host in unique:
            duplicate_count += 1
            trace.append(
                "candidate_deduplicated",
                state=TraceState.SKIPPED,
                reason_code="duplicate_domain",
                summary="Duplicate domain removed from Hunter candidate pool",
                identity=host,
                url=url,
                title=title,
                counters={"raw_rank": raw_rank},
                metadata={"candidate_host": host},
            )
            continue
        if len(unique) >= req.max_candidates:
            pool_omitted_count += 1
            trace.append(
                "candidate_pool_omitted",
                state=TraceState.SKIPPED,
                reason_code="max_candidates_reached",
                summary="Unique result omitted because Hunter candidate pool is full",
                identity=host,
                url=url,
                title=title,
                counters={"raw_rank": raw_rank, "max_candidates": req.max_candidates},
                metadata={"candidate_host": host},
            )
            continue
        unique[host] = item
        trace.append(
            "candidate_dedupe_retained",
            state=TraceState.SUCCEEDED,
            reason_code="unique_domain_retained",
            summary="Unique domain retained for Hunter qualification",
            identity=host,
            url=url,
            title=title,
            counters={"raw_rank": raw_rank, "unique_rank": len(unique)},
            metadata={"candidate_host": host},
        )

    async def inspect(item: dict) -> HuntCandidate | None:
        url = str(item.get("url") or "")
        raw_title = str(item.get("title") or "")
        display_title = raw_title or _domain(url)
        snippet = str(item.get("content") or item.get("snippet") or "")
        host = _domain(url) or "unknown"
        result = _pre_score(effective_req, raw_title, snippet, url)
        trace.append(
            "candidate_pre_scored",
            state=TraceState.SUCCEEDED if result.status == "calculated" else TraceState.DEGRADED,
            reason_code="pre_score_calculated" if result.status == "calculated" else "pre_score_insufficient_data",
            summary="Hunter candidate pre-score evaluated",
            identity=host,
            url=url,
            title=display_title,
            metadata=_score_metadata(result),
        )

        if result.status == "insufficient_data":
            trace.append(
                "candidate_observation",
                state=TraceState.DEGRADED,
                reason_code="insufficient_data_retained",
                summary="Candidate retained as observation because pre-score data is insufficient",
                identity=host,
                url=url,
                title=display_title,
            )
            return _shallow_candidate(
                display_title,
                snippet,
                url,
                result,
                qualification="Недостаточно данных",
                summary="Pre-score не рассчитан: поисковый результат не содержит достаточных признаков.",
                recommendation="Уточнить поисковый результат или получить первичный документ до глубокой разведки.",
            )

        assert result.score is not None
        if result.score < req.minimum_pre_score:
            trace.append(
                "candidate_rejected",
                state=TraceState.SKIPPED,
                reason_code="below_minimum_pre_score",
                summary="Candidate rejected below Hunter minimum pre-score",
                identity=host,
                url=url,
                title=display_title,
                counters={"pre_score": result.score, "minimum_pre_score": req.minimum_pre_score},
                metadata=_score_metadata(result),
            )
            return None

        if result.score < req.deep_audit_score:
            trace.append(
                "candidate_observation",
                state=TraceState.SUCCEEDED,
                reason_code="below_deep_audit_score",
                summary="Candidate retained as observation below deep-audit threshold",
                identity=host,
                url=url,
                title=display_title,
                counters={"pre_score": result.score, "deep_audit_score": req.deep_audit_score},
                metadata=_score_metadata(result),
            )
            return _shallow_candidate(
                display_title,
                snippet,
                url,
                result,
                qualification="Наблюдение",
                summary="Кандидат прошёл минимальный pre-score, но не достиг порога глубокой разведки.",
                recommendation="Сохранить в наблюдении и усилить признаки до запуска глубокой обработки.",
            )

        trace.append(
            "candidate_deep_audit_started",
            state=TraceState.STARTED,
            reason_code="deep_audit_threshold_met",
            summary="Candidate crossed deep-audit threshold and site processing started",
            identity=host,
            url=url,
            title=display_title,
            counters={"pre_score": result.score, "deep_audit_score": req.deep_audit_score},
        )
        try:
            page = await fetch_site(url)
            analysis = heuristic_analysis(page["final_url"], page["title"], page["text"])
            regional_text = f'{page["title"]} {page["text"][:12000]}'.lower()
            region_tokens = [token for token in effective_req.region.lower().split() if len(token) > 3]
            region_confirmed = any(token in regional_text for token in region_tokens)
            final_score = round((result.score + analysis.commercial_opportunity.score) / 2)
            reasons = list(result.reasons)
            if not region_confirmed:
                final_score = max(0, final_score - 20)
                reasons.append("региональная принадлежность требует проверки")
            trace.append(
                "candidate_deep_audit_completed",
                state=TraceState.SUCCEEDED,
                reason_code="deep_audit_completed",
                summary="Candidate site processed and final Hunter score produced",
                identity=host,
                url=str(analysis.url),
                title=analysis.company_name,
                counters={
                    "pre_score": result.score,
                    "analysis_score": analysis.commercial_opportunity.score,
                    "final_score": final_score,
                },
                metadata={
                    "region_confirmed": region_confirmed,
                    "qualification": analysis.commercial_opportunity.qualification,
                    "source_host": host,
                },
            )
            return HuntCandidate(
                company_name=analysis.company_name,
                url=analysis.url,
                source_title=display_title,
                source_snippet=snippet[:500],
                region_confirmed=region_confirmed,
                preliminary_score=result.score,
                pre_score_status=result.status,
                pre_score_factors=result.factors,
                deep_analysis_performed=True,
                final_score=final_score,
                qualification=analysis.commercial_opportunity.qualification,
                business_summary=analysis.business_summary,
                recommended_solution=analysis.commercial_opportunity.recommended_solution,
                reasons=reasons,
                analysis=analysis,
            )
        except (FetchError, httpx.HTTPError, ValueError) as exc:
            trace.append(
                "candidate_deep_audit_failed",
                state=TraceState.DEGRADED,
                reason_code="deep_audit_fetch_or_analysis_failed",
                summary="Candidate crossed deep-audit threshold but site processing failed",
                identity=host,
                url=url,
                title=display_title,
                counters={"pre_score": result.score},
                metadata={"error_type": type(exc).__name__},
            )
            fallback = _shallow_candidate(
                display_title,
                snippet,
                url,
                result,
                qualification="Наблюдение",
                summary="Порог глубокой разведки достигнут, но первичный сайт не удалось обработать.",
                recommendation="Повторить загрузку или проверить сайт вручную.",
            )
            fallback.reasons.append(f"глубокая обработка не выполнена: {type(exc).__name__}")
            return fallback

    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: dict) -> HuntCandidate | None:
        async with semaphore:
            return await inspect(item)

    inspected = await asyncio.gather(*(guarded(item) for item in unique.values()))
    candidates = [candidate for candidate in inspected if candidate is not None]
    candidates.sort(
        key=lambda candidate: (
            candidate.pre_score_status == "calculated",
            candidate.final_score if candidate.final_score is not None else -1,
            candidate.preliminary_score if candidate.preliminary_score is not None else -1,
        ),
        reverse=True,
    )
    returned = candidates[: req.output_limit]
    for rank, candidate in enumerate(candidates, start=1):
        url = str(candidate.url)
        host = _domain(url) or f"candidate-{rank}"
        if rank <= req.output_limit:
            trace.append(
                "candidate_returned",
                state=TraceState.SUCCEEDED,
                reason_code="within_output_limit",
                summary="Qualified candidate returned in Hunter response",
                identity=host,
                url=url,
                title=candidate.company_name,
                counters={"output_rank": rank, "final_score": candidate.final_score or 0},
                metadata={
                    "qualification": candidate.qualification,
                    "deep_analysis_performed": candidate.deep_analysis_performed,
                },
            )
        else:
            trace.append(
                "candidate_output_omitted",
                state=TraceState.SKIPPED,
                reason_code="output_limit_reached",
                summary="Qualified candidate omitted from response by Hunter output limit",
                identity=host,
                url=url,
                title=candidate.company_name,
                counters={"qualified_rank": rank, "output_limit": req.output_limit},
                metadata={"qualification": candidate.qualification},
            )

    funnel = HuntFunnel(
        raw_results=len(raw_results),
        excluded_results=excluded_count,
        duplicate_results=duplicate_count,
        pool_omitted_results=pool_omitted_count,
        unique_candidates=len(unique),
        inspected_candidates=len(inspected),
        qualified_candidates=len(candidates),
        returned_candidates=len(returned),
        output_omitted_candidates=max(0, len(candidates) - len(returned)),
    )
    trace.append(
        "hunt_funnel_complete",
        state=TraceState.SUCCEEDED,
        reason_code="hunter_candidate_funnel_completed",
        summary="Hunter candidate funnel completed with bounded forensic counters",
        counters=funnel.model_dump(),
    )
    return HuntResult(
        region=effective_req.region,
        search_zone=req.search_zone,
        queries=queries,
        discovered=len(unique),
        candidates=returned,
        funnel=funnel,
        notes=[
            query_intelligence_note,
            "План охоты сформирован по Справочнику охотника.",
            "Каждый кандидат получает объяснимый pre-score либо явный статус insufficient_data.",
            f"Глубокая обработка запускается только при pre-score >= {req.deep_audit_score}.",
            "Количество найденных ссылок не входит в формулу pre-score.",
        ],
        search=aggregate,
    )
