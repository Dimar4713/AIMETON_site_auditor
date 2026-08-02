from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.evidence_crawler.models import CrawlStatus, IdentitySignalKind, PageType
from app.evidence_crawler.targeted_api import IdentityGuardState, TargetedCrawlEnvelope
from app.mission_orchestrator import (
    ActionCandidate,
    ActionType,
    MissionOrchestrator,
    PolicySnapshot,
    QuestionState,
    StopReason,
    SufficiencyLevel,
)
from app.sufficiency_evaluator.models import (
    DimensionAssessment,
    SufficiencyDelta,
    SufficiencyDimension,
    SufficiencyEvaluation,
    SufficiencyTurnRecord,
)
from app.sufficiency_evaluator.trace_store import get_sufficiency_trace_store


_LEVEL_VALUE = {level: index for index, level in enumerate(SufficiencyLevel)}


def _minimum(levels: list[SufficiencyLevel]) -> SufficiencyLevel:
    return min(levels, key=_LEVEL_VALUE.__getitem__) if levels else SufficiencyLevel.L0


def _coverage_level(states: dict[str, QuestionState], critical: set[str]) -> SufficiencyLevel:
    if not critical:
        return SufficiencyLevel.L4
    values = [states.get(code, QuestionState.NOT_SEARCHED) for code in critical]
    if any(item in {QuestionState.CONFLICTING, QuestionState.BLOCKED} for item in values):
        return SufficiencyLevel.L0
    verified = sum(
        item in {QuestionState.VERIFIED, QuestionState.NOT_FOUND_AFTER_SUFFICIENT_SEARCH}
        for item in values
    )
    partial = sum(item == QuestionState.PARTIALLY_VERIFIED for item in values)
    if verified == len(values):
        return SufficiencyLevel.L4
    if verified + partial == len(values) and verified:
        return SufficiencyLevel.L3
    if verified + partial:
        return SufficiencyLevel.L2
    return SufficiencyLevel.L0


def evaluate_targeted_crawl(
    orchestrator: MissionOrchestrator,
    mission_id: str,
    envelope: TargetedCrawlEnvelope,
    *,
    protocol_completed_questions: set[str] | None = None,
) -> SufficiencyEvaluation:
    protocol_completed_questions = protocol_completed_questions or set()
    snapshot = orchestrator.get(mission_id)
    if envelope.crawl.mission_id != mission_id:
        raise ValueError("targeted crawl belongs to another mission")
    if envelope.crawl.analysis_id != snapshot.contract.analysis_id:
        raise ValueError("targeted crawl breaks analysis_id")
    if envelope.crawl.correlation_id != snapshot.contract.correlation_id:
        raise ValueError("targeted crawl breaks correlation_id")

    states = dict(snapshot.question_states)
    page_types = {page.page_type for page in envelope.crawl.pages}
    signal_kinds = {signal.kind for signal in envelope.crawl.identity_signals}

    if envelope.guard_state == IdentityGuardState.ALIGNED:
        states["identity"] = QuestionState.VERIFIED
    elif envelope.guard_state == IdentityGuardState.CONFLICTING:
        states["identity"] = QuestionState.CONFLICTING
    else:
        states["identity"] = QuestionState.PARTIALLY_VERIFIED

    if page_types & {PageType.CONTACTS, PageType.REQUISITES} or signal_kinds & {
        IdentitySignalKind.PHONE,
        IdentitySignalKind.EMAIL,
        IdentitySignalKind.ADDRESS,
    }:
        states["contacts"] = QuestionState.PARTIALLY_VERIFIED
    if PageType.ABOUT in page_types:
        states["company_profile"] = QuestionState.PARTIALLY_VERIFIED
    if PageType.PRODUCTS in page_types:
        states["products"] = QuestionState.PARTIALLY_VERIFIED

    for code in protocol_completed_questions:
        if states.get(code, QuestionState.NOT_SEARCHED) == QuestionState.NOT_SEARCHED:
            states[code] = QuestionState.NOT_FOUND_AFTER_SUFFICIENT_SEARCH

    critical = {item.code for item in snapshot.contract.questions if item.critical}
    coverage = _coverage_level(states, critical)
    evidence_quality = (
        SufficiencyLevel.L4
        if envelope.crawl.primary_document_candidates and envelope.crawl.pages
        else SufficiencyLevel.L3
        if envelope.crawl.pages
        else SufficiencyLevel.L0
    )
    identity = (
        SufficiencyLevel.L4
        if envelope.guard_state == IdentityGuardState.ALIGNED
        else SufficiencyLevel.L0
        if envelope.guard_state == IdentityGuardState.CONFLICTING
        else SufficiencyLevel.L2
    )
    source_reliability = (
        SufficiencyLevel.L4
        if envelope.crawl.primary_document_candidates
        else SufficiencyLevel.L3
        if envelope.crawl.pages
        else SufficiencyLevel.L0
    )
    freshness = SufficiencyLevel.L4 if envelope.crawl.pages else SufficiencyLevel.L0
    consistency = (
        SufficiencyLevel.L4
        if envelope.guard_state == IdentityGuardState.ALIGNED
        else SufficiencyLevel.L0
        if envelope.guard_state == IdentityGuardState.CONFLICTING
        else SufficiencyLevel.L2
    )
    execution_integrity = (
        SufficiencyLevel.L4
        if envelope.crawl.status == CrawlStatus.COMPLETED
        else SufficiencyLevel.L2
        if envelope.crawl.status == CrawlStatus.DEGRADED
        else SufficiencyLevel.L0
    )
    dimensions = [
        DimensionAssessment(dimension=SufficiencyDimension.COVERAGE, level=coverage),
        DimensionAssessment(dimension=SufficiencyDimension.EVIDENCE_QUALITY, level=evidence_quality),
        DimensionAssessment(dimension=SufficiencyDimension.IDENTITY_RESOLUTION, level=identity),
        DimensionAssessment(dimension=SufficiencyDimension.SOURCE_RELIABILITY, level=source_reliability),
        DimensionAssessment(dimension=SufficiencyDimension.FRESHNESS, level=freshness),
        DimensionAssessment(dimension=SufficiencyDimension.CONSISTENCY, level=consistency),
        DimensionAssessment(dimension=SufficiencyDimension.EXECUTION_INTEGRITY, level=execution_integrity),
    ]
    achieved = _minimum([item.level for item in dimensions])

    gaps = sorted(
        code
        for code in critical
        if states.get(code, QuestionState.NOT_SEARCHED)
        not in {QuestionState.VERIFIED, QuestionState.NOT_FOUND_AFTER_SUFFICIENT_SEARCH}
    )
    if envelope.guard_state == IdentityGuardState.CONFLICTING:
        gaps = list(dict.fromkeys(["identity_conflict", *gaps]))
    if envelope.crawl.status == CrawlStatus.DEGRADED:
        gaps = list(dict.fromkeys([*gaps, "execution_degraded"]))
    if envelope.crawl.status == CrawlStatus.BLOCKED:
        gaps = list(dict.fromkeys([*gaps, "critical_source_blocked"]))

    target = snapshot.contract.target_sufficiency
    release_allowed = _LEVEL_VALUE[achieved] >= _LEVEL_VALUE[SufficiencyLevel.L4] and not gaps
    stop_reason = StopReason.SUFFICIENCY_REACHED if release_allowed else None

    target_url = str(snapshot.contract.target_url)
    host = (urlsplit(target_url).hostname or "").lower()
    if release_allowed:
        candidates = [
            ActionCandidate(
                action_type=ActionType.STOP,
                target=mission_id,
                deficit_code="sufficiency_reached",
                expected_sufficiency_gain=0,
                ai_priority=1,
            )
        ]
    elif envelope.guard_state == IdentityGuardState.CONFLICTING:
        candidates = [
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target=target_url,
                deficit_code="identity_conflict",
                expected_sufficiency_gain=0.8,
                ai_priority=1,
            )
        ]
    elif envelope.crawl.primary_document_candidates:
        candidates = [
            ActionCandidate(
                action_type=ActionType.FETCH_DOCUMENT,
                target=str(envelope.crawl.primary_document_candidates[0].url),
                deficit_code=gaps[0] if gaps else "evidence_quality",
                expected_sufficiency_gain=0.6,
                ai_priority=0.9,
            )
        ]
    else:
        candidates = [
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target=target_url,
                deficit_code=gaps[0] if gaps else "coverage",
                expected_sufficiency_gain=0.5,
                ai_priority=0.8,
            )
        ]

    next_plan = orchestrator.plan(
        mission_id,
        deficits=gaps or ["sufficiency_reached"],
        candidates=candidates,
        policy=PolicySnapshot(
            allowed_hosts=frozenset({host}) if host else frozenset(),
            remaining_actions=max(0, snapshot.contract.budget.max_actions - len(snapshot.turns)),
        ),
    )
    improved = [
        item.dimension
        for item in dimensions
        if _LEVEL_VALUE[item.level] > _LEVEL_VALUE[snapshot.achieved_sufficiency]
    ]
    evidence_refs = list(
        dict.fromkeys(
            [
                *envelope.crawl.outcome.artifact_refs,
                *(page.document_id for page in envelope.crawl.pages),
                *(
                    str(candidate.url)
                    for candidate in envelope.crawl.primary_document_candidates
                ),
            ]
        )
    )
    turn_record = get_sufficiency_trace_store().append(
        SufficiencyTurnRecord(
            mission_id=mission_id,
            analysis_id=snapshot.contract.analysis_id,
            correlation_id=snapshot.contract.correlation_id,
            turn_number=len(get_sufficiency_trace_store().list_for_mission(mission_id)) + 1,
            before_level=snapshot.achieved_sufficiency,
            after_level=achieved,
            evidence_refs=evidence_refs,
            critical_gaps=gaps,
            next_action_type=next_plan.selected_action.action_type.value,
            next_action_target=next_plan.selected_action.target,
            next_action_deficit=next_plan.selected_action.deficit_code,
            next_action_reason=next_plan.selection_reason,
            recorded_at=datetime.now(UTC),
        )
    )
    return SufficiencyEvaluation(
        mission_id=mission_id,
        target_level=target,
        achieved_level=achieved,
        dimensions=dimensions,
        question_states=states,
        critical_gaps=gaps,
        delta=SufficiencyDelta(
            before=snapshot.achieved_sufficiency,
            after=achieved,
            improved_dimensions=improved,
            critical_gaps=gaps,
        ),
        report_release_allowed=release_allowed,
        stop_reason=stop_reason,
        next_plan=next_plan,
        turn_record=turn_record,
    )
