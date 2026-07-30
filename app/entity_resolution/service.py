from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from functools import wraps
from threading import RLock
from typing import Callable, ParamSpec, TypeVar
from urllib.parse import urlsplit

from app.entity_resolution.models import (
    CandidateIdentifier,
    IdentityCandidate,
    IdentityCandidateState,
    IdentityConflict,
    IdentityResolutionHistory,
    IdentityResolutionResult,
    IdentityResolutionState,
    IdentitySignalRef,
    SignalValidationState,
)
from app.evidence_crawler.models import (
    BootstrapCrawlResult,
    IdentitySignal,
    IdentitySignalKind,
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


_LEGAL_PREFIXES = {
    "ооо": "company",
    "ао": "company",
    "пао": "company",
    "зао": "company",
    "ип": "sole_proprietor",
}
_WEIGHTS = {
    IdentitySignalKind.INN: 0.34,
    IdentitySignalKind.OGRN: 0.34,
    IdentitySignalKind.LEGAL_NAME: 0.17,
    IdentitySignalKind.ADDRESS: 0.05,
    IdentitySignalKind.PHONE: 0.05,
    IdentitySignalKind.EMAIL: 0.05,
}
_P = ParamSpec("_P")
_R = TypeVar("_R")


def _serialized(
    method: Callable[_P, _R],
) -> Callable[_P, _R]:
    @wraps(method)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        resolver = args[0]
        with resolver._lock:
            return method(*args, **kwargs)

    return wrapper


def _stable_id(prefix: str, *parts: object) -> str:
    encoded = json.dumps(
        parts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"


def _digest(payload: list[BootstrapCrawlResult]) -> str:
    encoded = json.dumps(
        [item.model_dump(mode="json") for item in payload],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _normalized_text(value: str) -> str:
    return " ".join(
        re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).split()
    )


def _normalize_signal(signal: IdentitySignal) -> str:
    value = " ".join(signal.value.split()).strip(" ,.;")
    if signal.kind in {IdentitySignalKind.INN, IdentitySignalKind.OGRN}:
        return "".join(char for char in value if char.isdigit())
    if signal.kind == IdentitySignalKind.PHONE:
        digits = "".join(char for char in value if char.isdigit())
        if len(digits) == 11 and digits.startswith("8"):
            digits = f"7{digits[1:]}"
        return f"+{digits}"
    if signal.kind == IdentitySignalKind.EMAIL:
        return value.casefold()
    return _normalized_text(value)


def _valid_inn(value: str) -> bool:
    if len(value) == 10:
        check = sum(
            int(value[index]) * weight
            for index, weight in enumerate((2, 4, 10, 3, 5, 9, 4, 6, 8))
        )
        return check % 11 % 10 == int(value[9])
    if len(value) == 12:
        first = sum(
            int(value[index]) * weight
            for index, weight in enumerate((7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
        )
        second = sum(
            int(value[index]) * weight
            for index, weight in enumerate(
                (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
            )
        )
        return (
            first % 11 % 10 == int(value[10])
            and second % 11 % 10 == int(value[11])
        )
    return False


def _valid_ogrn(value: str) -> bool:
    if len(value) == 13:
        return int(value[:-1]) % 11 % 10 == int(value[-1])
    if len(value) == 15:
        return int(value[:-1]) % 13 % 10 == int(value[-1])
    return False


def _validate_signal(
    signal: IdentitySignal,
    normalized: str,
) -> tuple[SignalValidationState, str | None]:
    if signal.state != "candidate":
        return SignalValidationState.INVALID, "unsupported_signal_state"
    if signal.kind == IdentitySignalKind.INN and not _valid_inn(normalized):
        return SignalValidationState.INVALID, "invalid_inn_checksum"
    if signal.kind == IdentitySignalKind.OGRN and not _valid_ogrn(normalized):
        return SignalValidationState.INVALID, "invalid_ogrn_checksum"
    if signal.kind == IdentitySignalKind.PHONE and not 10 <= len(normalized[1:]) <= 15:
        return SignalValidationState.INVALID, "invalid_phone_length"
    if signal.kind == IdentitySignalKind.EMAIL and not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        normalized,
    ):
        return SignalValidationState.INVALID, "invalid_email"
    if signal.kind in {IdentitySignalKind.LEGAL_NAME, IdentitySignalKind.ADDRESS}:
        if len(normalized) < 3:
            return SignalValidationState.INVALID, "identity_text_too_short"
    if not normalized:
        return SignalValidationState.INVALID, "empty_normalized_signal"
    return SignalValidationState.VALID, None


def _entity_type(name: str) -> str:
    first = _normalized_text(name).split(maxsplit=1)[0]
    return _LEGAL_PREFIXES.get(first, "organization")


def _anchor_key(
    signal: IdentitySignal,
    ref: IdentitySignalRef,
) -> tuple[str, str]:
    if signal.kind == IdentitySignalKind.LEGAL_NAME:
        return f"legal_name:{ref.document_id}", ref.normalized_value
    return signal.kind.value, ref.normalized_value


class _DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[tuple[str, str], tuple[str, str]] = {}

    def add(self, item: tuple[str, str]) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: tuple[str, str]) -> tuple[str, str]:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, first: tuple[str, str], second: tuple[str, str]) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parent[second_root] = first_root


class ProvisionalEntityResolver:
    def __init__(self) -> None:
        self._history: dict[str, list[IdentityResolutionResult]] = {}
        self._execution_cache: dict[
            tuple[str, int],
            tuple[str, IdentityResolutionResult],
        ] = {}
        self._promotion_cache: dict[
            tuple[str, int],
            tuple[str, IdentityResolutionResult],
        ] = {}
        self._lock = RLock()

    @staticmethod
    def _validate_inputs(
        orchestrator: MissionOrchestrator,
        mission_id: str,
        plan: NextActionPlan,
        batches: list[BootstrapCrawlResult],
    ) -> None:
        orchestrator.validate_pending_plan(mission_id, plan)
        if plan.selected_action.action_type != ActionType.RESOLVE_IDENTITY:
            raise ValueError("identity resolver requires a resolve_identity plan")
        if plan.selected_action.target not in {"", mission_id}:
            raise ValueError("resolve_identity plan targets another mission")
        if not batches:
            raise ValueError("identity resolver requires at least one bootstrap result")
        snapshot = orchestrator.get(mission_id)
        seen_documents: set[str] = set()
        for batch in batches:
            if batch.mission_id != mission_id:
                raise ValueError("bootstrap result belongs to another mission")
            if batch.analysis_id != snapshot.contract.analysis_id:
                raise ValueError("bootstrap result breaks analysis_id")
            if batch.correlation_id != snapshot.contract.correlation_id:
                raise ValueError("bootstrap result breaks correlation_id")
            pages = {page.document_id: page for page in batch.pages}
            if len(pages) != len(batch.pages):
                raise ValueError("bootstrap result contains duplicate document ids")
            for document_id in pages:
                if document_id in seen_documents:
                    raise ValueError("document appears in more than one bootstrap result")
                seen_documents.add(document_id)
            for signal in batch.identity_signals:
                if signal.document_id not in pages:
                    raise ValueError("identity signal references an unknown document")
                page = pages[signal.document_id]
                if str(signal.source_url) not in {
                    str(page.requested_url),
                    str(page.final_url),
                }:
                    raise ValueError("identity signal source_url does not match its document")
            root_host = (urlsplit(str(batch.root_url)).hostname or "").casefold()
            for candidate in batch.primary_document_candidates:
                if candidate.source_document_id not in pages:
                    raise ValueError(
                        "primary document hint references an unknown source document"
                    )
                candidate_host = (
                    urlsplit(str(candidate.url)).hostname or ""
                ).casefold()
                if candidate.same_domain != (candidate_host == root_host):
                    raise ValueError("primary document same_domain classification is invalid")

    @staticmethod
    def _signal_refs(
        batches: list[BootstrapCrawlResult],
    ) -> list[tuple[IdentitySignal, IdentitySignalRef]]:
        result: list[tuple[IdentitySignal, IdentitySignalRef]] = []
        for batch in batches:
            pages = {page.document_id: page for page in batch.pages}
            for signal in batch.identity_signals:
                page = pages[signal.document_id]
                normalized = _normalize_signal(signal)
                validation, reason = _validate_signal(signal, normalized)
                result.append(
                    (
                        signal,
                        IdentitySignalRef(
                            kind=signal.kind.value,
                            value=signal.value,
                            normalized_value=normalized,
                            validation_state=validation,
                            validation_reason=reason,
                            document_id=signal.document_id,
                            source_url=signal.source_url,
                            locator=signal.locator,
                            accessed_at=page.accessed_at,
                            document_digest=page.normalized_content_digest,
                        ),
                    )
                )
        return sorted(
            result,
            key=lambda item: (
                item[1].document_id,
                item[1].kind,
                item[1].normalized_value,
                item[1].locator,
            ),
        )

    @staticmethod
    def _build_candidates(
        mission_id: str,
        signal_refs: list[tuple[IdentitySignal, IdentitySignalRef]],
    ) -> tuple[list[IdentityCandidate], list[IdentityConflict]]:
        valid = [
            (signal, ref)
            for signal, ref in signal_refs
            if ref.validation_state == SignalValidationState.VALID
        ]
        by_document: dict[str, list[tuple[IdentitySignal, IdentitySignalRef]]] = {}
        for item in valid:
            by_document.setdefault(item[1].document_id, []).append(item)

        anchors = {
            _anchor_key(signal, ref)
            for signal, ref in valid
            if signal.kind
            in {
                IdentitySignalKind.INN,
                IdentitySignalKind.OGRN,
                IdentitySignalKind.LEGAL_NAME,
            }
        }
        sets = _DisjointSet()
        for anchor in anchors:
            sets.add(anchor)

        raw_conflicts: list[tuple[str, list[str], str]] = []
        for document_id, items in by_document.items():
            names = {
                _anchor_key(signal, ref)
                for signal, ref in items
                if signal.kind == IdentitySignalKind.LEGAL_NAME
            }
            strong = {
                _anchor_key(signal, ref)
                for signal, ref in items
                if signal.kind in {IdentitySignalKind.INN, IdentitySignalKind.OGRN}
            }
            if len(names) == 1:
                name = next(iter(names))
                for identifier in strong:
                    sets.union(name, identifier)
            elif len(names) > 1 and strong:
                raw_conflicts.append(
                    (
                        "ambiguous_document_attribution",
                        [document_id],
                        "Несколько юридических наименований и реквизиты найдены "
                        "в одном документе; автоматическое объединение запрещено.",
                    )
                )

        initial_groups: dict[
            tuple[str, str],
            set[tuple[str, str]],
        ] = {}
        for anchor in anchors:
            initial_groups.setdefault(sets.find(anchor), set()).add(anchor)

        name_roots: dict[str, set[tuple[str, str]]] = {}
        for root, group in initial_groups.items():
            for kind, normalized in group:
                if kind.startswith("legal_name:"):
                    name_roots.setdefault(normalized, set()).add(root)
        for roots in name_roots.values():
            strong_roots = {
                root
                for root in roots
                if any(
                    kind in {
                        IdentitySignalKind.INN.value,
                        IdentitySignalKind.OGRN.value,
                    }
                    for kind, _normalized in initial_groups[root]
                )
            }
            if len(strong_roots) <= 1:
                ordered_roots = sorted(roots)
                for other in ordered_roots[1:]:
                    sets.union(ordered_roots[0], other)

        grouped_anchors: dict[
            tuple[str, str],
            set[tuple[str, str]],
        ] = {}
        for anchor in anchors:
            grouped_anchors.setdefault(sets.find(anchor), set()).add(anchor)

        candidates: list[IdentityCandidate] = []
        anchor_to_candidate: dict[tuple[str, str], str] = {}
        for group in sorted(grouped_anchors.values(), key=lambda value: sorted(value)):
            relevant = [
                (signal, ref)
                for signal, ref in valid
                if _anchor_key(signal, ref) in group
            ]
            document_ids = {ref.document_id for _signal, ref in relevant}
            weak = [
                (signal, ref)
                for signal, ref in valid
                if ref.document_id in document_ids
                and signal.kind
                in {
                    IdentitySignalKind.PHONE,
                    IdentitySignalKind.EMAIL,
                    IdentitySignalKind.ADDRESS,
                }
            ]
            relevant.extend(weak)
            names = [
                ref.value
                for signal, ref in relevant
                if signal.kind == IdentitySignalKind.LEGAL_NAME
            ]
            canonical_name = (
                sorted(
                    set(names),
                    key=lambda value: (-len(value), value.casefold()),
                )[0]
                if names
                else "Неустановленная организация"
            )
            identifiers: list[CandidateIdentifier] = []
            identifier_keys = {
                (signal.kind, ref.normalized_value)
                for signal, ref in relevant
            }
            for kind, normalized in sorted(
                identifier_keys,
                key=lambda item: (item[0].value, item[1]),
            ):
                refs = [
                    ref
                    for signal, ref in relevant
                    if signal.kind == kind and ref.normalized_value == normalized
                ]
                identifiers.append(
                    CandidateIdentifier(
                        scheme=kind.value,
                        value=refs[0].value,
                        normalized_value=normalized,
                        signal_refs=refs,
                    )
                )
            unique_kinds = {IdentitySignalKind(item.scheme) for item in identifiers}
            confidence = min(
                0.95,
                sum(_WEIGHTS[kind] for kind in unique_kinds)
                + min(0.05, max(0, len(document_ids) - 1) * 0.02),
            )
            candidate_id = _stable_id(
                "identity_candidate",
                mission_id,
                sorted(group),
            )
            candidate = IdentityCandidate(
                id=candidate_id,
                entity_type=_entity_type(canonical_name),
                canonical_name=canonical_name,
                confidence=round(confidence, 4),
                state=IdentityCandidateState.COMPETING,
                identifiers=identifiers,
                supporting_document_ids=sorted(document_ids),
            )
            candidates.append(candidate)
            for anchor in group:
                anchor_to_candidate[anchor] = candidate_id

        conflicts: list[IdentityConflict] = []
        for code, document_ids, detail in raw_conflicts:
            candidate_ids = sorted(
                {
                    anchor_to_candidate[_anchor_key(signal, ref)]
                    for signal, ref in valid
                    if ref.document_id in document_ids
                    and _anchor_key(signal, ref) in anchor_to_candidate
                }
            )
            conflicts.append(
                IdentityConflict(
                    id=_stable_id("identity_conflict", mission_id, code, document_ids),
                    code=code,
                    candidate_ids=candidate_ids,
                    document_ids=sorted(document_ids),
                    detail=detail,
                )
            )

        by_name: dict[str, list[IdentityCandidate]] = {}
        for candidate in candidates:
            names = {
                item.normalized_value
                for item in candidate.identifiers
                if item.scheme == IdentitySignalKind.LEGAL_NAME.value
            }
            for name in names:
                by_name.setdefault(name, []).append(candidate)
        for name, items in by_name.items():
            strong_sets = {
                tuple(
                    sorted(
                        (identifier.scheme, identifier.normalized_value)
                        for identifier in item.identifiers
                        if identifier.scheme
                        in {
                            IdentitySignalKind.INN.value,
                            IdentitySignalKind.OGRN.value,
                        }
                    )
                )
                for item in items
            }
            if len(items) > 1 and len(strong_sets) > 1:
                candidate_ids = sorted(item.id for item in items)
                document_ids = sorted(
                    {
                        document_id
                        for item in items
                        for document_id in item.supporting_document_ids
                    }
                )
                conflicts.append(
                    IdentityConflict(
                        id=_stable_id(
                            "identity_conflict",
                            mission_id,
                            "same_name_different_identifiers",
                            name,
                        ),
                        code="same_name_different_identifiers",
                        candidate_ids=candidate_ids,
                        document_ids=document_ids,
                        detail=(
                            "Одинаковое нормализованное наименование связано с "
                            "разными реквизитами; кандидаты не объединены."
                        ),
                    )
                )
        return sorted(candidates, key=lambda item: item.id), sorted(
            conflicts,
            key=lambda item: item.id,
        )

    @staticmethod
    def _select_candidate(
        candidates: list[IdentityCandidate],
        conflicts: list[IdentityConflict],
    ) -> tuple[IdentityResolutionState, str | None]:
        if not candidates:
            return IdentityResolutionState.UNRESOLVED, None
        ordered = sorted(
            candidates,
            key=lambda item: (-item.confidence, item.id),
        )
        blocked = {
            candidate_id
            for conflict in conflicts
            for candidate_id in conflict.candidate_ids
        }
        lead = ordered[0]
        runner_up = ordered[1].confidence if len(ordered) > 1 else 0
        if (
            lead.confidence >= 0.55
            and lead.confidence - runner_up >= 0.15
            and lead.id not in blocked
        ):
            return IdentityResolutionState.PROVISIONAL, lead.id
        if conflicts or len(ordered) > 1:
            return IdentityResolutionState.CONFLICTING, None
        return IdentityResolutionState.UNRESOLVED, None

    @staticmethod
    def _next_actions(
        mission_id: str,
        batches: list[BootstrapCrawlResult],
        state: IdentityResolutionState,
        candidates: list[IdentityCandidate],
        selected_candidate_id: str | None,
    ) -> list[ActionCandidate]:
        actions: list[ActionCandidate] = []
        selected = next(
            (item for item in candidates if item.id == selected_candidate_id),
            None,
        )
        if state == IdentityResolutionState.CONFLICTING:
            actions.append(
                ActionCandidate(
                    action_type=ActionType.REVIEW_CONFLICT,
                    target=mission_id,
                    deficit_code="identity_conflict",
                    expected_sufficiency_gain=0.7,
                    ai_priority=0.9,
                )
            )
        query_parts: list[str] = []
        if selected is not None:
            for identifier in selected.identifiers:
                if identifier.scheme in {"inn", "ogrn", "legal_name"}:
                    query_parts.append(f'"{identifier.value}"')
        if not query_parts:
            host = urlsplit(str(batches[0].root_url)).hostname or ""
            query_parts.append(f'site:{host} "реквизиты"')
        actions.append(
            ActionCandidate(
                action_type=ActionType.QUERY_PROVIDER,
                target=" OR ".join(dict.fromkeys(query_parts)),
                deficit_code=(
                    "identity_link_evidence"
                    if selected is not None
                    else "identity_unresolved"
                ),
                expected_sufficiency_gain=0.6,
                ai_priority=0.8,
                estimated_cost_by_currency={"USD": Decimal("0.008")},
            )
        )
        document_urls = sorted(
            {
                str(item.url)
                for batch in batches
                for item in batch.primary_document_candidates
                if item.same_domain and item.lifecycle_state == "discovery_hint"
            }
        )
        for url in document_urls[:5]:
            actions.append(
                ActionCandidate(
                    action_type=ActionType.FETCH_DOCUMENT,
                    target=url,
                    deficit_code="identity_link_evidence",
                    expected_sufficiency_gain=0.5,
                    ai_priority=0.7,
                )
            )
        return actions

    @_serialized
    def resolve(
        self,
        orchestrator: MissionOrchestrator,
        mission_id: str,
        *,
        plan: NextActionPlan,
        bootstrap_results: list[BootstrapCrawlResult],
    ) -> IdentityResolutionResult:
        self._validate_inputs(
            orchestrator,
            mission_id,
            plan,
            bootstrap_results,
        )
        input_digest = _digest(bootstrap_results)
        cache_key = (mission_id, plan.turn_number)
        with self._lock:
            cached = self._execution_cache.get(cache_key)
            if cached is not None:
                if cached[0] != input_digest:
                    raise ValueError("identity plan already executed with different input")
                return deepcopy(cached[1])

        snapshot = orchestrator.get(mission_id)
        refs = self._signal_refs(bootstrap_results)
        candidates, conflicts = self._build_candidates(mission_id, refs)
        state, selected_candidate_id = self._select_candidate(candidates, conflicts)
        for candidate in candidates:
            if candidate.id == selected_candidate_id:
                candidate.state = IdentityCandidateState.PROVISIONAL
        invalid = [
            ref
            for _signal, ref in refs
            if ref.validation_state == SignalValidationState.INVALID
        ]
        gaps = ["identity_link_evidence"]
        if state == IdentityResolutionState.UNRESOLVED:
            gaps = ["identity_unresolved", "legal_identifier_missing"]
        elif state == IdentityResolutionState.CONFLICTING:
            gaps = ["identity_conflict", "identity_link_evidence"]
        question_state = (
            QuestionState.CONFLICTING
            if state == IdentityResolutionState.CONFLICTING
            else QuestionState.PARTIALLY_VERIFIED
        )
        achieved = snapshot.achieved_sufficiency
        if achieved == SufficiencyLevel.L0 and refs:
            achieved = SufficiencyLevel.L1
        next_actions = self._next_actions(
            mission_id,
            bootstrap_results,
            state,
            candidates,
            selected_candidate_id,
        )
        outcome = ActionOutcome(
            state=(
                ActionOutcomeState.SUCCEEDED
                if state == IdentityResolutionState.PROVISIONAL
                else ActionOutcomeState.PARTIAL
            ),
            artifact_refs=[],
            reason_codes=list(dict.fromkeys(gaps)),
        )
        with self._lock:
            previous = self._history.get(mission_id, [])
            revision_number = len(previous) + 1
            result_id = _stable_id(
                "identity_result",
                mission_id,
                revision_number,
                input_digest,
            )
            outcome.artifact_refs = [
                result_id,
                *([selected_candidate_id] if selected_candidate_id else []),
            ]
            result = IdentityResolutionResult(
                id=result_id,
                mission_id=mission_id,
                analysis_id=snapshot.contract.analysis_id,
                correlation_id=snapshot.contract.correlation_id,
                revision_number=revision_number,
                supersedes_result_id=previous[-1].id if previous else None,
                input_digest=input_digest,
                created_at=datetime.now(UTC),
                plan=plan,
                state=state,
                selected_candidate_id=selected_candidate_id,
                candidates=candidates,
                conflicts=conflicts,
                invalid_signals=invalid,
                gaps=gaps,
                outcome=outcome,
                recommended_feedback=SufficiencyFeedback(
                    achieved=achieved,
                    question_states={"identity": question_state},
                    critical_gaps=gaps,
                ),
                next_action_candidates=next_actions,
            )
            self._history.setdefault(mission_id, []).append(result)
            self._execution_cache[cache_key] = (input_digest, result)
            return deepcopy(result)

    @_serialized
    def promote_identifier_links(
        self,
        orchestrator: MissionOrchestrator,
        mission_id: str,
        *,
        plan: NextActionPlan,
        base_result_id: str,
        accepted_identifier_ids: list[str],
        artifact_ids: list[str],
        authority_verified: bool,
    ) -> IdentityResolutionResult:
        orchestrator.validate_pending_plan(mission_id, plan)
        if plan.selected_action.action_type != ActionType.FETCH_DOCUMENT:
            raise ValueError("identity promotion requires a fetch_document plan")
        if not accepted_identifier_ids:
            raise ValueError("identity promotion requires accepted identifier links")
        payload = {
            "base_result_id": base_result_id,
            "accepted_identifier_ids": sorted(set(accepted_identifier_ids)),
            "artifact_ids": sorted(set(artifact_ids)),
            "authority_verified": authority_verified,
        }
        promotion_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        promotion_digest = f"sha256:{hashlib.sha256(promotion_bytes).hexdigest()}"
        cache_key = (mission_id, plan.turn_number)
        cached = self._promotion_cache.get(cache_key)
        if cached is not None:
            if cached[0] != promotion_digest:
                raise ValueError("identity promotion plan already executed with different input")
            return deepcopy(cached[1])

        history = self._history.get(mission_id)
        if not history:
            raise ValueError("identity history is empty")
        base = next(
            (item for item in history if item.id == base_result_id),
            None,
        )
        if base is None:
            raise ValueError("base identity result is not present in history")
        if history[-1].id != base_result_id:
            raise ValueError("identity promotion requires the latest revision")
        if base.selected_candidate_id is None:
            raise ValueError("base identity result has no selected candidate")

        snapshot = orchestrator.get(mission_id)
        candidates = deepcopy(base.candidates)
        selected = next(
            item
            for item in candidates
            if item.id == base.selected_candidate_id
        )
        selected.accepted_identifier_links = sorted(
            set(selected.accepted_identifier_links)
            | set(accepted_identifier_ids)
        )
        query_parts = [
            f'"{identifier.value}"'
            for identifier in selected.identifiers
            if identifier.scheme in {"inn", "ogrn", "legal_name"}
        ]
        next_actions = [
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target=str(snapshot.contract.target_url),
                deficit_code="targeted_company_profile",
                expected_sufficiency_gain=0.8,
                ai_priority=0.9,
            )
        ]
        if not authority_verified:
            next_actions.append(
                ActionCandidate(
                    action_type=ActionType.QUERY_PROVIDER,
                    target=" OR ".join(dict.fromkeys(query_parts)),
                    deficit_code="official_registry_verification",
                    expected_sufficiency_gain=0.65,
                    ai_priority=0.75,
                    estimated_cost_by_currency={"USD": Decimal("0.008")},
                )
            )
        gaps = ["identity_relationship_scope"]
        if not authority_verified:
            gaps.insert(0, "official_registry_verification")
        revision_number = len(history) + 1
        result_id = _stable_id(
            "identity_result",
            mission_id,
            revision_number,
            promotion_digest,
        )
        result = IdentityResolutionResult(
            id=result_id,
            mission_id=mission_id,
            analysis_id=snapshot.contract.analysis_id,
            correlation_id=snapshot.contract.correlation_id,
            revision_number=revision_number,
            supersedes_result_id=base.id,
            input_digest=promotion_digest,
            created_at=datetime.now(UTC),
            plan=plan,
            state=IdentityResolutionState.PROVISIONAL,
            selected_candidate_id=base.selected_candidate_id,
            candidates=candidates,
            conflicts=deepcopy(base.conflicts),
            invalid_signals=deepcopy(base.invalid_signals),
            gaps=gaps,
            outcome=ActionOutcome(
                state=ActionOutcomeState.SUCCEEDED,
                artifact_refs=[
                    result_id,
                    *sorted(set(artifact_ids)),
                    *sorted(set(accepted_identifier_ids)),
                ],
                reason_codes=[
                    "identity_identifier_link_accepted",
                    *(
                        []
                        if authority_verified
                        else ["official_registry_verification_pending"]
                    ),
                ],
            ),
            recommended_feedback=SufficiencyFeedback(
                achieved=max(
                    snapshot.achieved_sufficiency,
                    SufficiencyLevel.L2,
                    key=lambda item: int(item.value[1:]),
                ),
                question_states={
                    "identity": (
                        QuestionState.VERIFIED
                        if authority_verified
                        else QuestionState.PARTIALLY_VERIFIED
                    )
                },
                critical_gaps=gaps,
            ),
            next_action_candidates=next_actions,
        )
        self._history[mission_id].append(result)
        self._promotion_cache[cache_key] = (promotion_digest, result)
        return deepcopy(result)

    def history(self, mission_id: str) -> IdentityResolutionHistory:
        with self._lock:
            if mission_id not in self._history:
                raise KeyError(mission_id)
            return IdentityResolutionHistory(
                mission_id=mission_id,
                revisions=deepcopy(self._history[mission_id]),
            )
