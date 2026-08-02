from __future__ import annotations

from app.entity_resolution import IdentityResolutionState, ProvisionalEntityResolver
from app.mission_orchestrator import (
    ActionCandidate,
    ActionType,
    PolicySnapshot,
)
from tests.test_entity_resolution import (
    DIGEST_B,
    _batch,
    _crawl_plan,
    _record_crawl_and_plan_resolution,
)
from app.mission_orchestrator import MissionOrchestrator


def _candidate_signature(result):
    return {
        (
            candidate.id,
            candidate.canonical_name,
            candidate.entity_type,
            tuple(
                sorted(
                    (identifier.scheme, identifier.normalized_value)
                    for identifier in candidate.identifiers
                )
            ),
        )
        for candidate in result.candidates
    }


def test_competing_candidates_are_preserved_verbatim_in_history():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    first_batch = _batch(mission, crawl_plan)
    competing_batch = _batch(
        mission,
        crawl_plan,
        document_id="document_dedal_plus",
        path="dedal-plus",
        name='ООО "Дедал"',
        inn="2465000007",
        ogrn="1232400000007",
        digest=DIGEST_B,
    )
    first_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    first = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=first_plan,
        bootstrap_results=[first_batch, competing_batch],
    )

    assert first.state == IdentityResolutionState.CONFLICTING
    assert first.selected_candidate_id is None
    assert len(first.candidates) == 2
    first_signature = _candidate_signature(first)

    orchestrator.record_turn(
        mission.contract.mission_id,
        plan=first_plan,
        outcome=first.outcome,
        feedback=first.recommended_feedback,
    )
    second_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity_conflict"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                target=mission.contract.mission_id,
                deficit_code="identity_conflict",
            )
        ],
        policy=PolicySnapshot(remaining_actions=8),
    )
    second = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=second_plan,
        bootstrap_results=[first_batch, competing_batch],
    )
    history = resolver.history(mission.contract.mission_id)

    assert second.revision_number == 2
    assert second.supersedes_result_id == first.id
    assert _candidate_signature(second) == first_signature
    assert len(history.revisions) == 2
    assert _candidate_signature(history.revisions[0]) == first_signature
    assert _candidate_signature(history.revisions[1]) == first_signature


def test_reordered_evidence_keeps_deterministic_competing_candidate_ids():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    first_batch = _batch(mission, crawl_plan)
    competing_batch = _batch(
        mission,
        crawl_plan,
        document_id="document_dedal_plus",
        path="dedal-plus",
        name='ООО "Дедал"',
        inn="2465000007",
        ogrn="1232400000007",
        digest=DIGEST_B,
    )
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    first = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[first_batch, competing_batch],
    )
    repeated = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[competing_batch, first_batch],
    )

    assert repeated.id == first.id
    assert _candidate_signature(repeated) == _candidate_signature(first)
    assert len(resolver.history(mission.contract.mission_id).revisions) == 1
