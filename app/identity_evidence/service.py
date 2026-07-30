from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.document_pipeline import (
    DocumentPipeline,
    DocumentRequest,
    FetchPolicy,
)
from app.entity_resolution import ProvisionalEntityResolver
from app.entity_resolution.models import IdentityResolutionResult
from app.entity_resolution.service import _normalized_text, _valid_inn, _valid_ogrn
from app.identity_evidence.models import (
    AcceptedIdentifierEvidence,
    EvidenceGuardState,
    IdentityEvidenceResult,
    IdentitySearchResult,
)
from app.mission_orchestrator.models import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    NextActionPlan,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
)
from app.mission_orchestrator.service import MissionOrchestrator
from app.search_gateway import (
    GatewayState,
    SearchGateway,
    SearchRequest,
    identity_search_policy_from_env,
)
from app.search_gateway.gateway import request_fingerprint
from app.sef.models import (
    DiscoveryHint,
    Entity,
    EntityIdentifier,
    ProviderCall,
    ProviderCallState,
    Source,
    SourceKind,
)


_INN_LABEL_RE = re.compile(
    r"\bИНН\s*[:№]?\s*([0-9][0-9\s-]{8,22}[0-9])",
    flags=re.IGNORECASE,
)
_OGRN_LABEL_RE = re.compile(
    r"\bОГРН(?:ИП)?\s*[:№]?\s*([0-9][0-9\s-]{11,27}[0-9])",
    flags=re.IGNORECASE,
)


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(
        parts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _host(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").casefold()
    port = parsed.port
    netloc = host
    if port and not (
        (parsed.scheme.casefold() == "http" and port == 80)
        or (parsed.scheme.casefold() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    return f"{parsed.scheme.casefold()}://{netloc}/"


def _authority_hosts() -> frozenset[str]:
    configured = {
        item.strip().casefold().removeprefix("www.")
        for item in os.getenv(
            "IDENTITY_AUTHORITY_HOSTS",
            "egrul.nalog.ru,service.nalog.ru,bo.nalog.ru",
        ).split(",")
        if item.strip()
    }
    return frozenset(configured)


def _source_kind(target_url: str, document_url: str) -> SourceKind | None:
    target_host = _host(target_url)
    document_host = _host(document_url)
    if target_host and document_host == target_host:
        return SourceKind.FIRST_PARTY
    if any(
        document_host == authority or document_host.endswith(f".{authority}")
        for authority in _authority_hosts()
    ):
        return SourceKind.OFFICIAL_REGISTRY
    return None


def _valid_strong_identifiers(text: str) -> dict[str, set[str]]:
    result = {"inn": set(), "ogrn": set()}
    for match in _INN_LABEL_RE.finditer(text):
        value = re.sub(r"\D", "", match.group(1))
        if _valid_inn(value):
            result["inn"].add(value)
    for match in _OGRN_LABEL_RE.finditer(text):
        value = re.sub(r"\D", "", match.group(1))
        if _valid_ogrn(value):
            result["ogrn"].add(value)
    return result


def _quote_for_identifier(text: str, scheme: str, value: str) -> str | None:
    expression = _INN_LABEL_RE if scheme == "inn" else _OGRN_LABEL_RE
    for match in expression.finditer(text):
        if re.sub(r"\D", "", match.group(1)) != value:
            continue
        if len(text) <= 7_500:
            return text
        start = max(0, match.start() - 500)
        end = min(len(text), match.end() + 500)
        return text[start:end]
    return None


class IdentityEvidenceService:
    def __init__(
        self,
        *,
        search_gateway: SearchGateway,
        document_pipeline: DocumentPipeline,
        entity_resolver: ProvisionalEntityResolver,
    ) -> None:
        self._search = search_gateway
        self._documents = document_pipeline
        self._resolver = entity_resolver
        self._search_results: dict[str, IdentitySearchResult] = {}
        self._search_execution: dict[tuple[str, int], str] = {}
        self._evidence_execution: dict[tuple[str, int], IdentityEvidenceResult] = {}
        self._lock = asyncio.Lock()

    def _identity_result(
        self,
        mission_id: str,
        identity_result_id: str,
    ) -> IdentityResolutionResult:
        history = self._resolver.history(mission_id)
        result = next(
            (item for item in history.revisions if item.id == identity_result_id),
            None,
        )
        if result is None:
            raise ValueError("identity result is not present in mission history")
        return result

    @staticmethod
    def _validate_identity_action(
        identity: IdentityResolutionResult,
        plan: NextActionPlan,
        action_type: ActionType,
    ) -> None:
        if plan.selected_action.action_type != action_type:
            raise ValueError(f"identity evidence requires an issued {action_type.value} plan")
        if plan.selected_action not in identity.next_action_candidates:
            raise ValueError("selected action was not proposed by the identity revision")

    async def search_identity(
        self,
        orchestrator: MissionOrchestrator,
        mission_id: str,
        *,
        plan: NextActionPlan,
        identity_result_id: str,
        limit: int = 5,
    ) -> IdentitySearchResult:
        orchestrator.validate_pending_plan(mission_id, plan)
        identity = self._identity_result(mission_id, identity_result_id)
        self._validate_identity_action(identity, plan, ActionType.QUERY_PROVIDER)
        snapshot = orchestrator.get(mission_id)
        key = (mission_id, plan.turn_number)
        async with self._lock:
            existing_id = self._search_execution.get(key)
            if existing_id is not None:
                existing = self._search_results[existing_id]
                if (
                    existing.identity_result_id != identity_result_id
                    or existing.plan != plan
                ):
                    raise ValueError("identity search plan already executed with different input")
                return deepcopy(existing)

        request = SearchRequest(
            query=plan.selected_action.target,
            limit=limit,
            language="ru-RU",
            mission_id=mission_id,
            correlation_id=snapshot.contract.correlation_id,
        )
        started_at = datetime.now(UTC)
        response = await self._search.search(
            request,
            identity_search_policy_from_env(),
        )
        finished_at = datetime.now(UTC)
        fingerprint = request_fingerprint(request)
        selected_provider = response.diagnostics.selected_provider
        provider_ref = selected_provider or next(
            (item.provider for item in reversed(response.diagnostics.attempts)),
            "provider_gateway",
        )
        provider_call_id = _stable_id(
            "provider_call",
            mission_id,
            plan.turn_number,
            fingerprint,
        )
        if response.results:
            call_state = ProviderCallState.SUCCEEDED
        elif response.diagnostics.state == GatewayState.UNAVAILABLE:
            call_state = ProviderCallState.SKIPPED
        else:
            call_state = ProviderCallState.PARTIAL
        provider_call = ProviderCall(
            id=provider_call_id,
            mission_id=mission_id,
            correlation_id=snapshot.contract.correlation_id,
            provider_ref=provider_ref,
            operation="identity_search.basic",
            request_fingerprint=fingerprint,
            state=call_state,
            started_at=started_at,
            finished_at=finished_at,
        )
        discovered_at = finished_at
        hints = [
            DiscoveryHint(
                id=_stable_id(
                    "discovery_hint",
                    provider_call_id,
                    str(item.url),
                ),
                mission_id=mission_id,
                provider_call_id=provider_call_id,
                correlation_id=snapshot.contract.correlation_id,
                url=item.url,
                title=item.title.strip() or _host(str(item.url)),
                snippet=(
                    item.snippet.strip()
                    or "Search result candidate; snippet is unavailable and is not evidence."
                ),
                discovered_at=discovered_at,
            )
            for item in response.results
        ]
        next_actions = [
            ActionCandidate(
                action_type=ActionType.FETCH_DOCUMENT,
                target=str(hint.url),
                deficit_code="identity_link_evidence",
                expected_sufficiency_gain=0.7,
                ai_priority=max(0.4, 0.8 - index * 0.05),
            )
            for index, hint in enumerate(hints)
        ]
        reason_codes = (
            ["identity_document_candidates_found"]
            if hints
            else ["identity_search_no_document_candidates"]
        )
        outcome = ActionOutcome(
            state=(
                ActionOutcomeState.SUCCEEDED
                if hints
                else ActionOutcomeState.PARTIAL
            ),
            artifact_refs=[provider_call.id, *(item.id for item in hints)],
            actual_cost_by_currency=response.diagnostics.total_cost_by_currency,
            reason_codes=reason_codes,
        )
        result = IdentitySearchResult(
            id=_stable_id(
                "identity_search",
                mission_id,
                plan.turn_number,
                fingerprint,
            ),
            mission_id=mission_id,
            analysis_id=snapshot.contract.analysis_id,
            correlation_id=snapshot.contract.correlation_id,
            identity_result_id=identity_result_id,
            plan=plan,
            provider_call=provider_call,
            discovery_hints=hints,
            diagnostics=response.diagnostics,
            outcome=outcome,
            recommended_feedback=SufficiencyFeedback(
                achieved=max(
                    snapshot.achieved_sufficiency,
                    SufficiencyLevel.L1,
                    key=lambda item: int(item.value[1:]),
                ),
                question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
                critical_gaps=["identity_link_evidence"],
            ),
            next_action_candidates=next_actions,
        )
        async with self._lock:
            existing_id = self._search_execution.get(key)
            if existing_id is not None:
                return deepcopy(self._search_results[existing_id])
            self._search_execution[key] = result.id
            self._search_results[result.id] = deepcopy(result)
        return result

    async def promote_identity_evidence(
        self,
        orchestrator: MissionOrchestrator,
        mission_id: str,
        *,
        plan: NextActionPlan,
        identity_result_id: str,
        identity_search_result_id: str,
    ) -> IdentityEvidenceResult:
        orchestrator.validate_pending_plan(mission_id, plan)
        identity = self._identity_result(mission_id, identity_result_id)
        if identity.selected_candidate_id is None:
            raise ValueError("identity revision has no selected candidate")
        if plan.selected_action.action_type != ActionType.FETCH_DOCUMENT:
            raise ValueError("identity evidence requires an issued fetch_document plan")
        key = (mission_id, plan.turn_number)
        async with self._lock:
            cached = self._evidence_execution.get(key)
            if cached is not None:
                if (
                    cached.identity_result_id != identity_result_id
                    or cached.identity_search_result_id != identity_search_result_id
                    or cached.plan != plan
                ):
                    raise ValueError("identity evidence plan already executed with different input")
                return deepcopy(cached)
            search_result = self._search_results.get(identity_search_result_id)
            if search_result is None:
                raise ValueError("identity search result is not present")
            search_result = deepcopy(search_result)
        if search_result.mission_id != mission_id:
            raise ValueError("identity search result belongs to another mission")
        if search_result.identity_result_id != identity_result_id:
            raise ValueError("identity search result targets another identity revision")
        if plan.selected_action not in search_result.next_action_candidates:
            raise ValueError("selected document was not proposed by identity search")
        hint = next(
            (
                item
                for item in search_result.discovery_hints
                if str(item.url) == plan.selected_action.target
            ),
            None,
        )
        if hint is None:
            raise ValueError("selected document has no provider discovery hint")

        snapshot = orchestrator.get(mission_id)
        document_url = str(hint.url)
        kind = _source_kind(str(snapshot.contract.target_url), document_url)
        source = Source(
            id=_stable_id("source", mission_id, _origin(document_url)),
            mission_id=mission_id,
            correlation_id=snapshot.contract.correlation_id,
            kind=kind or SourceKind.INDUSTRY_CATALOG,
            publisher=hint.title,
            homepage_url=_origin(document_url),
        )
        host = (urlsplit(document_url).hostname or "").casefold()
        fetched = await self._documents.fetch(
            DocumentRequest(
                mission_id=mission_id,
                source_id=source.id,
                correlation_id=snapshot.contract.correlation_id,
                url=document_url,
            ),
            FetchPolicy(
                allowed_hosts=frozenset({host}),
                allow_crawl4ai=False,
                allow_browser=False,
                min_text_length=20,
            ),
        )
        selected = next(
            item
            for item in identity.candidates
            if item.id == identity.selected_candidate_id
        )
        entity = Entity(
            id=_stable_id("entity", mission_id, selected.id),
            mission_id=mission_id,
            correlation_id=snapshot.contract.correlation_id,
            entity_type=selected.entity_type,
            canonical_name=selected.canonical_name,
        )
        expected = {
            item.scheme: item.normalized_value
            for item in selected.identifiers
            if item.scheme in {"inn", "ogrn"}
        }
        observed = _valid_strong_identifiers(fetched.normalized_text)
        name_present = (
            _normalized_text(selected.canonical_name)
            in _normalized_text(fetched.normalized_text)
        )
        competing = {
            scheme: values - ({expected[scheme]} if scheme in expected else set())
            for scheme, values in observed.items()
            if values - ({expected[scheme]} if scheme in expected else set())
        }
        matching = {
            scheme: value
            for scheme, value in expected.items()
            if value in observed.get(scheme, set())
        }
        guard_reasons: list[str] = []
        if kind is None:
            guard_reasons.append("identity_source_not_trusted")
        if not name_present:
            guard_reasons.append("identity_legal_name_not_found")
        if not matching:
            guard_reasons.append("identity_strong_identifier_not_found")
        if competing:
            guard_reasons.append("identity_competing_identifier_found")

        accepted: list[AcceptedIdentifierEvidence] = []
        if not guard_reasons:
            for scheme, value in sorted(matching.items()):
                block = next(
                    (
                        block
                        for block in fetched.blocks
                        if _quote_for_identifier(block.text, scheme, value) is not None
                    ),
                    None,
                )
                if block is None:
                    guard_reasons.append("identity_identifier_locator_not_found")
                    break
                quote = _quote_for_identifier(block.text, scheme, value)
                assert quote is not None
                promotion = self._documents.promote_quote(
                    fetched,
                    locator=block.locator,
                    quote=quote,
                )
                identifier = EntityIdentifier(
                    id=_stable_id(
                        "entity_identifier",
                        entity.id,
                        scheme,
                        value,
                    ),
                    mission_id=mission_id,
                    entity_id=entity.id,
                    correlation_id=snapshot.contract.correlation_id,
                    scheme=scheme,
                    value=next(
                        item.value
                        for item in selected.identifiers
                        if item.scheme == scheme
                        and item.normalized_value == value
                    ),
                    normalized_value=value,
                )
                accepted.append(
                    AcceptedIdentifierEvidence(
                        identifier=identifier,
                        evidence=promotion.evidence,
                    )
                )
        if guard_reasons:
            accepted = []

        guard_state = (
            EvidenceGuardState.ACCEPTED
            if accepted
            else EvidenceGuardState.BLOCKED
        )
        revision: IdentityResolutionResult | None = None
        next_actions: list[ActionCandidate]
        if accepted:
            revision = self._resolver.promote_identifier_links(
                orchestrator,
                mission_id,
                plan=plan,
                base_result_id=identity_result_id,
                accepted_identifier_ids=[
                    item.identifier.id for item in accepted
                ],
                artifact_ids=[
                    fetched.document.id,
                    *(item.evidence.id for item in accepted),
                    *(item.identifier.id for item in accepted),
                ],
                authority_verified=kind == SourceKind.OFFICIAL_REGISTRY,
            )
            next_actions = revision.next_action_candidates
            feedback = revision.recommended_feedback
            outcome = revision.outcome
        else:
            next_actions = [
                ActionCandidate(
                    action_type=ActionType.QUERY_PROVIDER,
                    target=search_result.plan.selected_action.target,
                    deficit_code="identity_link_evidence",
                    expected_sufficiency_gain=0.5,
                    ai_priority=0.6,
                )
            ]
            feedback = SufficiencyFeedback(
                achieved=max(
                    snapshot.achieved_sufficiency,
                    SufficiencyLevel.L1,
                    key=lambda item: int(item.value[1:]),
                ),
                question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
                critical_gaps=["identity_link_evidence"],
            )
            outcome = ActionOutcome(
                state=ActionOutcomeState.PARTIAL,
                artifact_refs=[fetched.document.id],
                reason_codes=list(dict.fromkeys(guard_reasons)),
            )
        result = IdentityEvidenceResult(
            id=_stable_id(
                "identity_evidence",
                mission_id,
                plan.turn_number,
                fetched.normalized_content_digest,
                [item.identifier.id for item in accepted],
            ),
            mission_id=mission_id,
            analysis_id=snapshot.contract.analysis_id,
            correlation_id=snapshot.contract.correlation_id,
            identity_result_id=identity_result_id,
            identity_search_result_id=identity_search_result_id,
            plan=plan,
            guard_state=guard_state,
            guard_reason_codes=list(dict.fromkeys(guard_reasons)),
            source=source,
            document=fetched.document,
            raw_content_digest=fetched.raw_content_digest,
            normalized_content_digest=fetched.normalized_content_digest,
            entity=entity,
            accepted=accepted,
            identity_revision=revision,
            outcome=outcome,
            recommended_feedback=feedback,
            next_action_candidates=next_actions,
        )
        async with self._lock:
            cached = self._evidence_execution.get(key)
            if cached is not None:
                return deepcopy(cached)
            self._evidence_execution[key] = deepcopy(result)
        return result
