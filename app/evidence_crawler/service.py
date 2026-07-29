from __future__ import annotations

import asyncio
import hashlib
import heapq
import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from app.document_pipeline import (
    DocumentPipeline,
    DocumentRequest,
    FetchPolicy,
    FetchedDocument,
)
from app.evidence_crawler.fetchers import MetadataFetcher, StaticMetadataFetcher, origin
from app.evidence_crawler.models import (
    BootstrapCrawlPolicy,
    BootstrapCrawlResult,
    CrawledPage,
    CrawlStatus,
    IdentitySignal,
    IdentitySignalKind,
    PageType,
    PrimaryDocumentCandidate,
    RobotsState,
)
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    MissionOrchestrator,
    NextActionPlan,
)
from app.scraper import FetchError, normalize_url


USER_AGENT = "AIMETON-EvidenceCrawler/0.1"
SITEMAP_LOC_RE = re.compile(r"<loc\b[^>]*>(.*?)</loc>", re.I | re.S)
SITEMAP_DIRECTIVE_RE = re.compile(r"^\s*sitemap\s*:\s*(\S+)\s*$", re.I)
DOCUMENT_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
PAGE_TERMS: tuple[tuple[PageType, tuple[str, ...], int], ...] = (
    (
        PageType.REQUISITES,
        ("реквизит", "инн", "огрн", "legal", "company-details"),
        95,
    ),
    (
        PageType.CONTACTS,
        ("контакт", "адрес", "телефон", "contact", "office"),
        90,
    ),
    (
        PageType.ABOUT,
        ("о-компании", "о_компании", "about", "company", "история"),
        80,
    ),
    (
        PageType.PRODUCTS,
        ("услуг", "продук", "каталог", "service", "product", "catalog"),
        55,
    ),
)

INN_RE = re.compile(r"(?i)\bинн\s*[:№-]?\s*(\d{10}|\d{12})\b")
OGRN_RE = re.compile(r"(?i)\bогрн(?:ип)?\s*[:№-]?\s*(\d{13}|\d{15})\b")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
)
ADDRESS_RE = re.compile(
    r"(?i)\b(?:юридический\s+)?адрес\s*[:№-]?\s*(.{8,220})"
)
LEGAL_NAME_RE = re.compile(
    r"(?i)\b(?:ООО|ПАО|АО|ЗАО|ИП)\s+[«\"']?[^,\n.;]{2,120}[»\"']?"
)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _canonical_url(value: str) -> str:
    parsed = urlsplit(normalize_url(value))
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
    )


def _host_family_match(left: str, right: str) -> bool:
    left_host = (urlsplit(left).hostname or "").lower().removeprefix("www.")
    right_host = (urlsplit(right).hostname or "").lower().removeprefix("www.")
    return bool(left_host) and left_host == right_host


def _allowed_host_family(value: str) -> frozenset[str]:
    host = (urlsplit(value).hostname or "").lower()
    if not host:
        return frozenset()
    bare = host.removeprefix("www.")
    return frozenset({bare, f"www.{bare}"})


def _document_media_type(value: str) -> str | None:
    suffix = PurePosixPath(urlsplit(value).path.casefold()).suffix
    return DOCUMENT_EXTENSIONS.get(suffix)


def _page_type_and_priority(url: str, text: str = "") -> tuple[PageType, int]:
    parsed = urlsplit(url)
    if parsed.path in {"", "/"}:
        return PageType.ROOT, 100
    haystack = f"{parsed.path} {text}".casefold()
    for page_type, terms, priority in PAGE_TERMS:
        if any(term in haystack for term in terms):
            return page_type, priority
    return PageType.OTHER, 10


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return f"+{digits}"


@dataclass
class RobotsPolicy:
    state: RobotsState
    rules: list[tuple[str, bool]]
    sitemap_urls: list[str]
    reason_codes: list[str]

    def allows(self, url: str) -> bool:
        if self.state in {RobotsState.BLOCKED, RobotsState.UNAVAILABLE}:
            return False
        if not self.rules:
            return True
        path = urlsplit(url).path or "/"
        matches: list[tuple[int, bool]] = []
        for pattern, allowed in self.rules:
            expression = re.escape(pattern).replace(r"\*", ".*")
            if pattern.endswith("$"):
                expression = f"{expression[:-2]}$"
            else:
                expression = f"{expression}.*"
            if re.fullmatch(expression, path):
                specificity = len(pattern.replace("*", "").removesuffix("$"))
                matches.append((specificity, allowed))
        if not matches:
            return True
        best = max(item[0] for item in matches)
        return any(allowed for specificity, allowed in matches if specificity == best)


def _robots_rules(text: str) -> list[tuple[str, bool]]:
    groups: list[tuple[list[str], list[tuple[str, bool]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, bool]] = []

    def finish_group() -> None:
        nonlocal agents, rules
        if agents:
            groups.append((agents, rules))
        agents = []
        rules = []

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            if rules:
                finish_group()
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().casefold()
        value = value.strip()
        if key == "user-agent":
            if rules:
                finish_group()
            agents.append(value.casefold())
        elif key in {"allow", "disallow"} and agents:
            if key == "disallow" and not value:
                continue
            rules.append((value or "/", key == "allow"))
    finish_group()

    user_agent = USER_AGENT.casefold()
    exact = [
        group_rules
        for group_agents, group_rules in groups
        if any(agent != "*" and agent in user_agent for agent in group_agents)
    ]
    selected = exact or [
        group_rules
        for group_agents, group_rules in groups
        if "*" in group_agents
    ]
    return [rule for group in selected for rule in group]


class BootstrapEvidenceCrawler:
    def __init__(
        self,
        *,
        document_pipeline: DocumentPipeline | None = None,
        metadata_fetcher: MetadataFetcher | None = None,
    ) -> None:
        self._documents = document_pipeline or DocumentPipeline(max_concurrency=2)
        self._metadata = metadata_fetcher or StaticMetadataFetcher()
        self._run_semaphore = asyncio.Semaphore(2)
        self._run_lock = asyncio.Lock()
        self._active_runs: set[tuple[str, int]] = set()
        self._completed_runs: dict[tuple[str, int], BootstrapCrawlResult] = {}

    async def _load_robots(
        self,
        root_url: str,
        policy: BootstrapCrawlPolicy,
    ) -> RobotsPolicy:
        robots_url = f"{origin(root_url)}/robots.txt"
        try:
            response = await self._metadata.fetch_text(
                robots_url,
                timeout_seconds=policy.timeout_seconds,
                max_bytes=policy.metadata_max_bytes,
                allowed_hosts=_allowed_host_family(root_url),
            )
        except FetchError:
            return RobotsPolicy(
                state=RobotsState.UNAVAILABLE,
                rules=[],
                sitemap_urls=[],
                reason_codes=["robots_unavailable"],
            )
        if response.status_code in {404, 410}:
            return RobotsPolicy(
                state=RobotsState.MISSING,
                rules=[],
                sitemap_urls=[f"{origin(root_url)}/sitemap.xml"],
                reason_codes=["robots_missing"],
            )
        if not _host_family_match(root_url, response.final_url):
            return RobotsPolicy(
                state=RobotsState.BLOCKED,
                rules=[],
                sitemap_urls=[],
                reason_codes=["robots_cross_domain_redirect"],
            )
        rules = _robots_rules(response.text)
        sitemaps = [
            match.group(1)
            for line in response.text.splitlines()
            if (match := SITEMAP_DIRECTIVE_RE.match(line))
            and _host_family_match(root_url, match.group(1))
        ]
        if not sitemaps:
            sitemaps = [f"{origin(root_url)}/sitemap.xml"]
        robots = RobotsPolicy(
            state=RobotsState.ALLOWED,
            rules=rules,
            sitemap_urls=list(dict.fromkeys(sitemaps)),
            reason_codes=[],
        )
        if robots.allows(root_url):
            return robots
        robots.state = RobotsState.BLOCKED
        robots.reason_codes = ["robots_blocked"]
        return robots

    async def _load_sitemaps(
        self,
        root_url: str,
        robots: RobotsPolicy,
        policy: BootstrapCrawlPolicy,
    ) -> tuple[list[str], list[str], list[str]]:
        if policy.max_sitemaps == 0 or robots.state in {
            RobotsState.BLOCKED,
            RobotsState.UNAVAILABLE,
        }:
            return [], [], []
        queue = list(robots.sitemap_urls)
        visited: list[str] = []
        locations: list[str] = []
        reason_codes: list[str] = []
        while queue and len(visited) < policy.max_sitemaps:
            sitemap_url = _canonical_url(queue.pop(0))
            if sitemap_url in visited or not _host_family_match(root_url, sitemap_url):
                continue
            try:
                response = await self._metadata.fetch_text(
                    sitemap_url,
                    timeout_seconds=policy.timeout_seconds,
                    max_bytes=policy.metadata_max_bytes,
                    allowed_hosts=_allowed_host_family(root_url),
                )
            except FetchError:
                visited.append(sitemap_url)
                reason_codes.append("sitemap_unavailable")
                continue
            visited.append(sitemap_url)
            if response.status_code in {404, 410}:
                continue
            if not _host_family_match(root_url, response.final_url):
                reason_codes.append("sitemap_cross_domain_redirect")
                continue
            for raw_location in SITEMAP_LOC_RE.findall(response.text):
                location = unescape(raw_location.strip())
                if not location.startswith(("http://", "https://")):
                    continue
                if not _host_family_match(root_url, location):
                    continue
                canonical = _canonical_url(location)
                if urlsplit(canonical).query:
                    reason_codes.append("query_url_skipped")
                    continue
                if _document_media_type(canonical):
                    locations.append(canonical)
                elif canonical.casefold().endswith(".xml"):
                    if len(visited) + len(queue) < policy.max_sitemaps:
                        queue.append(canonical)
                else:
                    locations.append(canonical)
                if len(locations) >= policy.max_sitemap_urls:
                    queue.clear()
                    break
        return (
            visited,
            list(dict.fromkeys(locations)),
            list(dict.fromkeys(reason_codes)),
        )

    @staticmethod
    def _extract_identity_signals(
        fetched: FetchedDocument,
    ) -> list[IdentitySignal]:
        signals: list[IdentitySignal] = []
        seen: set[tuple[IdentitySignalKind, str]] = set()

        def add(kind: IdentitySignalKind, value: str, locator: str) -> None:
            normalized = " ".join(value.split()).strip(" ,.;")
            if kind == IdentitySignalKind.PHONE:
                normalized = _normalize_phone(normalized)
            key = (kind, normalized.casefold())
            if not normalized or key in seen:
                return
            seen.add(key)
            signals.append(
                IdentitySignal(
                    kind=kind,
                    value=normalized,
                    document_id=fetched.document.id,
                    source_url=fetched.document.url,
                    locator=locator,
                )
            )

        for block in fetched.blocks:
            text = block.text
            for match in INN_RE.finditer(text):
                add(IdentitySignalKind.INN, match.group(1), block.locator)
            for match in OGRN_RE.finditer(text):
                add(IdentitySignalKind.OGRN, match.group(1), block.locator)
            for match in EMAIL_RE.finditer(text):
                add(IdentitySignalKind.EMAIL, match.group(0), block.locator)
            for match in PHONE_RE.finditer(text):
                add(IdentitySignalKind.PHONE, match.group(0), block.locator)
            for match in ADDRESS_RE.finditer(text):
                add(IdentitySignalKind.ADDRESS, match.group(1), block.locator)
            for match in LEGAL_NAME_RE.finditer(text):
                add(IdentitySignalKind.LEGAL_NAME, match.group(0), block.locator)
        return signals

    async def run_mission(
        self,
        orchestrator: MissionOrchestrator,
        mission_id: str,
        *,
        plan: NextActionPlan,
        policy: BootstrapCrawlPolicy | None = None,
    ) -> BootstrapCrawlResult:
        orchestrator.validate_pending_plan(mission_id, plan)
        key = (mission_id, plan.turn_number)
        async with self._run_lock:
            completed = self._completed_runs.get(key)
            if completed is not None:
                return completed.model_copy(deep=True)
            if key in self._active_runs:
                raise ValueError("bootstrap plan execution is already in progress")
            self._active_runs.add(key)
        try:
            async with self._run_semaphore:
                result = await self._run_mission_once(
                    orchestrator,
                    mission_id,
                    plan=plan,
                    policy=policy,
                )
        except Exception:
            async with self._run_lock:
                self._active_runs.discard(key)
            raise
        async with self._run_lock:
            self._active_runs.discard(key)
            self._completed_runs[key] = result.model_copy(deep=True)
        return result

    async def _run_mission_once(
        self,
        orchestrator: MissionOrchestrator,
        mission_id: str,
        *,
        plan: NextActionPlan,
        policy: BootstrapCrawlPolicy | None = None,
    ) -> BootstrapCrawlResult:
        policy = policy or BootstrapCrawlPolicy()
        orchestrator.validate_pending_plan(mission_id, plan)
        if plan.selected_action.action_type != ActionType.CRAWL_URL:
            raise ValueError("bootstrap requires an issued crawl_url action")
        snapshot = orchestrator.get(mission_id)
        root_url = _canonical_url(plan.selected_action.target)
        if not _host_family_match(str(snapshot.contract.target_url), root_url):
            raise ValueError("bootstrap target is outside mission host family")

        robots = await self._load_robots(root_url, policy)
        if not robots.allows(root_url):
            outcome = ActionOutcome(
                state=ActionOutcomeState.BLOCKED,
                reason_codes=robots.reason_codes or ["robots_blocked"],
            )
            return BootstrapCrawlResult(
                status=CrawlStatus.BLOCKED,
                mission_id=mission_id,
                analysis_id=snapshot.contract.analysis_id,
                correlation_id=snapshot.contract.correlation_id,
                root_url=root_url,
                plan=plan,
                robots_state=robots.state,
                reason_codes=outcome.reason_codes,
                outcome=outcome,
            )

        sitemap_urls, sitemap_locations, sitemap_reasons = await self._load_sitemaps(
            root_url,
            robots,
            policy,
        )
        queue: list[tuple[int, int, str]] = []
        queued: set[str] = set()
        counter = 0

        def enqueue(url: str, depth: int, priority: int) -> None:
            nonlocal counter
            canonical = _canonical_url(url)
            if canonical in queued or not _host_family_match(root_url, canonical):
                return
            if _document_media_type(canonical):
                return
            queued.add(canonical)
            counter += 1
            heapq.heappush(queue, (-priority, depth, f"{counter:08d}\x1f{canonical}"))

        enqueue(root_url, 0, 100)
        for location in sitemap_locations:
            page_type, priority = _page_type_and_priority(location)
            del page_type
            if priority >= 55:
                enqueue(location, 1, priority)

        pages: list[CrawledPage] = []
        signals: list[IdentitySignal] = []
        documents: list[PrimaryDocumentCandidate] = []
        discovered: list[str] = []
        blocked: list[str] = []
        failed: list[str] = []
        signal_keys: set[tuple[IdentitySignalKind, str, str]] = set()
        document_urls: set[str] = set()
        visited: set[str] = set()
        started = time.monotonic()
        attempts = 0
        last_request_started: float | None = None
        query_url_skipped = False

        while queue and len(pages) < policy.max_pages:
            if time.monotonic() - started >= policy.max_duration_seconds:
                break
            _, depth, tagged_url = heapq.heappop(queue)
            url = tagged_url.split("\x1f", 1)[1]
            if url in visited or depth > policy.max_depth:
                continue
            visited.add(url)
            attempts += 1
            if attempts > policy.max_pages * 3:
                break
            if not robots.allows(url):
                blocked.append(url)
                continue
            if last_request_started is not None and policy.min_request_interval_ms:
                elapsed = time.monotonic() - last_request_started
                wait_for = policy.min_request_interval_ms / 1_000 - elapsed
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
            last_request_started = time.monotonic()
            source_id = _stable_id("source", f"{mission_id}\x1f{url}")
            try:
                fetched = await self._documents.fetch(
                    DocumentRequest(
                        mission_id=mission_id,
                        source_id=source_id,
                        correlation_id=snapshot.contract.correlation_id,
                        url=url,
                    ),
                    FetchPolicy(
                        timeout_seconds=policy.timeout_seconds,
                        allowed_hosts=_allowed_host_family(root_url),
                        allow_crawl4ai=policy.allow_crawl4ai,
                        allow_browser=policy.allow_browser,
                    ),
                )
            except FetchError:
                failed.append(url)
                continue
            final_url = _canonical_url(str(fetched.document.url))
            if not _host_family_match(root_url, final_url):
                failed.append(url)
                continue
            page_type, _ = _page_type_and_priority(
                final_url,
                fetched.document.title,
            )
            pages.append(
                CrawledPage(
                    requested_url=url,
                    final_url=final_url,
                    depth=depth,
                    page_type=page_type,
                    document_id=fetched.document.id,
                    title=fetched.document.title,
                    accessed_at=fetched.document.accessed_at,
                    media_type=fetched.document.media_type,
                    fetch_path=fetched.diagnostics.path,
                    raw_content_digest=fetched.raw_content_digest,
                    normalized_content_digest=fetched.normalized_content_digest,
                    declared_canonical_url=fetched.declared_canonical_url,
                    canonical_same_origin=fetched.canonical_same_origin,
                    redirect_history=fetched.diagnostics.redirect_history,
                    link_count=len(fetched.links),
                )
            )
            for signal in self._extract_identity_signals(fetched):
                key = (
                    signal.kind,
                    signal.value.casefold(),
                    signal.document_id,
                )
                if key not in signal_keys:
                    signal_keys.add(key)
                    signals.append(signal)

            for link in fetched.links[: policy.max_links_per_page]:
                link_url = _canonical_url(str(link.url))
                if urlsplit(link_url).query:
                    query_url_skipped = True
                    continue
                media_type = _document_media_type(link_url)
                same_domain = _host_family_match(root_url, link_url)
                if media_type:
                    if link_url not in document_urls:
                        document_urls.add(link_url)
                        documents.append(
                            PrimaryDocumentCandidate(
                                url=link_url,
                                media_type=media_type,
                                source_document_id=fetched.document.id,
                                source_locator=link.locator,
                                link_text=link.text,
                                same_domain=same_domain,
                            )
                        )
                    continue
                if not same_domain:
                    continue
                if link_url not in discovered:
                    discovered.append(link_url)
                if depth < policy.max_depth:
                    _, priority = _page_type_and_priority(link_url, link.text)
                    if priority >= 55:
                        enqueue(link_url, depth + 1, priority)

        reason_codes = [*robots.reason_codes, *sitemap_reasons]
        if query_url_skipped:
            reason_codes.append("query_url_skipped")
        if failed:
            reason_codes.append("page_fetch_failed")
        if blocked:
            reason_codes.append("page_robots_blocked")
        if time.monotonic() - started >= policy.max_duration_seconds:
            reason_codes.append("crawl_deadline_reached")
        if len(pages) >= policy.max_pages and queue:
            reason_codes.append("page_budget_reached")
        sitemap_degraded = any(
            code != "query_url_skipped" for code in sitemap_reasons
        )
        status = (
            CrawlStatus.COMPLETED
            if pages and not failed and not sitemap_degraded
            else CrawlStatus.DEGRADED
            if pages
            else CrawlStatus.BLOCKED
        )
        outcome_state = (
            ActionOutcomeState.SUCCEEDED
            if status == CrawlStatus.COMPLETED
            else ActionOutcomeState.PARTIAL
            if status == CrawlStatus.DEGRADED
            else ActionOutcomeState.BLOCKED
        )
        outcome = ActionOutcome(
            state=outcome_state,
            artifact_refs=[page.document_id for page in pages],
            reason_codes=list(dict.fromkeys(reason_codes)),
        )
        next_actions: list[ActionCandidate] = []
        if signals:
            next_actions.append(
                ActionCandidate(
                    action_type=ActionType.RESOLVE_IDENTITY,
                    target=mission_id,
                    deficit_code="identity",
                    expected_sufficiency_gain=0.7,
                    ai_priority=0.9,
                )
            )
        for item in documents[:5]:
            if item.same_domain:
                next_actions.append(
                    ActionCandidate(
                        action_type=ActionType.FETCH_DOCUMENT,
                        target=str(item.url),
                        deficit_code="primary_documents",
                        expected_sufficiency_gain=0.4,
                        ai_priority=0.6,
                    )
                )
        return BootstrapCrawlResult(
            status=status,
            mission_id=mission_id,
            analysis_id=snapshot.contract.analysis_id,
            correlation_id=snapshot.contract.correlation_id,
            root_url=root_url,
            plan=plan,
            robots_state=robots.state,
            sitemap_urls=sitemap_urls,
            pages=pages,
            identity_signals=signals,
            primary_document_candidates=documents,
            discovered_urls=discovered,
            blocked_urls=blocked,
            failed_urls=failed,
            reason_codes=outcome.reason_codes,
            outcome=outcome,
            next_action_candidates=next_actions,
        )
