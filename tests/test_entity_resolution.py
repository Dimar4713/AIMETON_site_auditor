from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.document_pipeline.models import FetchPath
from app.entity_resolution import (
    IdentityResolutionState,
    ProvisionalEntityResolver,
    reset_entity_resolver,
)
from app.evidence_crawler.models import (
    BootstrapCrawlResult,
    CrawledPage,
    CrawlStatus,
    IdentitySignal,
    IdentitySignalKind,
    PageType,
    PrimaryDocumentCandidate,
    RobotsState,
)
from app.main import app
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionOrchestrator,
    NextActionPlan,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
    default_site_mission_request,
    reset_mission_orchestrator,
)
from scripts.export_identity_resolution_schema import TARGET, render_schema


DIGEST_A = f"sha256:{'a' * 64}"
DIGEST_B = f"sha256:{'b' * 64}"


def test_committed_identity_schema_is_current_and_valid():
    assert TARGET.read_text(encoding="utf-8") == render_schema()
    Draft202012Validator.check_schema(
        json.loads(TARGET.read_text(encoding="utf-8"))
    )


def _crawl_plan(orchestrator: MissionOrchestrator):
    mission = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )
    plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target="https://example.test/",
                deficit_code="bootstrap",
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_actions=10,
        ),
    )
    return mission, plan


def _page(document_id: str, path: str, digest: str) -> CrawledPage:
    url = f"https://example.test/{path.lstrip('/')}"
    return CrawledPage(
        requested_url=url,
        final_url=url,
        depth=1,
        page_type=PageType.REQUISITES,
        document_id=document_id,
        title="Реквизиты",
        accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
        media_type="text/html",
        fetch_path=FetchPath.STATIC,
        raw_content_digest=digest,
        normalized_content_digest=digest,
        link_count=1,
    )


def _signal(
    kind: IdentitySignalKind,
    value: str,
    document_id: str,
    path: str,
) -> IdentitySignal:
    return IdentitySignal(
        kind=kind,
        value=value,
        document_id=document_id,
        source_url=f"https://example.test/{path.lstrip('/')}",
        locator=f"css:#{kind.value}",
    )


def _batch(
    mission,
    plan,
    *,
    document_id: str = "document_requisites",
    path: str = "requisites",
    name: str = 'ООО "Дедал"',
    inn: str = "2400000009",
    ogrn: str = "1022400000006",
    digest: str = DIGEST_A,
) -> BootstrapCrawlResult:
    page = _page(document_id, path, digest)
    return BootstrapCrawlResult(
        status=CrawlStatus.COMPLETED,
        mission_id=mission.contract.mission_id,
        analysis_id=mission.contract.analysis_id,
        correlation_id=mission.contract.correlation_id,
        root_url="https://example.test/",
        plan=plan,
        robots_state=RobotsState.ALLOWED,
        pages=[page],
        identity_signals=[
            _signal(IdentitySignalKind.LEGAL_NAME, name, document_id, path),
            _signal(IdentitySignalKind.INN, inn, document_id, path),
            _signal(IdentitySignalKind.OGRN, ogrn, document_id, path),
            _signal(
                IdentitySignalKind.EMAIL,
                "office@example.test",
                document_id,
                path,
            ),
        ],
        primary_document_candidates=[
            PrimaryDocumentCandidate(
                url="https://example.test/files/requisites.pdf",
                media_type="application/pdf",
                source_document_id=document_id,
                source_locator="css:a[href$='.pdf']",
                link_text="Карточка предприятия",
                same_domain=True,
            )
        ],
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=[document_id],
        ),
    )


def _record_crawl_and_plan_resolution(
    orchestrator: MissionOrchestrator,
    mission,
    crawl_plan,
):
    orchestrator.record_turn(
        mission.contract.mission_id,
        plan=crawl_plan,
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=["document_requisites"],
        ),
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L1,
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )
    return orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                target=mission.contract.mission_id,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(remaining_actions=9),
    )


def test_provisional_candidate_preserves_provenance_without_accepted_links():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    batch = _batch(mission, crawl_plan)
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    result = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[batch],
    )

    assert result.state == IdentityResolutionState.PROVISIONAL
    assert result.selected_candidate_id
    selected = next(
        item for item in result.candidates if item.id == result.selected_candidate_id
    )
    assert selected.canonical_name == 'ООО "Дедал"'
    assert selected.entity_type == "company"
    assert selected.confidence >= 0.85
    assert selected.accepted_identifier_links == []
    assert {
        (item.scheme, item.normalized_value)
        for item in selected.identifiers
    } >= {
        ("inn", "2400000009"),
        ("ogrn", "1022400000006"),
    }
    assert all(
        ref.document_digest == DIGEST_A
        and ref.locator
        and ref.accessed_at
        for item in selected.identifiers
        for ref in item.signal_refs
    )
    assert {
        item.action_type for item in result.next_action_candidates
    } >= {
        ActionType.QUERY_PROVIDER,
        ActionType.FETCH_DOCUMENT,
    }
    assert result.recommended_feedback.question_states == {
        "identity": QuestionState.PARTIALLY_VERIFIED
    }


def test_same_name_with_different_identifiers_stays_competing():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    first = _batch(mission, crawl_plan)
    second = _batch(
        mission,
        crawl_plan,
        document_id="document_other",
        path="partner",
        inn="2465000007",
        ogrn="1232400000007",
        digest=DIGEST_B,
    )
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    result = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[first, second],
    )

    assert result.state == IdentityResolutionState.CONFLICTING
    assert result.selected_candidate_id is None
    assert len(result.candidates) == 2
    assert any(
        item.code == "same_name_different_identifiers"
        for item in result.conflicts
    )
    assert all(
        item.state.value == "competing"
        for item in result.candidates
    )
    assert result.recommended_feedback.question_states == {
        "identity": QuestionState.CONFLICTING
    }
    assert result.next_action_candidates[0].action_type == ActionType.REVIEW_CONFLICT


def test_invalid_identifier_is_not_promoted_and_requires_more_search():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    batch = _batch(
        mission,
        crawl_plan,
        inn="2400000000",
        ogrn="1022400000000",
    )
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    result = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[batch],
    )

    assert result.state == IdentityResolutionState.UNRESOLVED
    assert {item.validation_reason for item in result.invalid_signals} >= {
        "invalid_inn_checksum",
        "invalid_ogrn_checksum",
    }
    assert "identity_unresolved" in result.gaps
    assert all(
        identifier.scheme not in {"inn", "ogrn"}
        for candidate in result.candidates
        for identifier in candidate.identifiers
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda batch: setattr(
                batch.identity_signals[0],
                "source_url",
                "https://other.test/requisites",
            ),
            "source_url",
        ),
        (
            lambda batch: setattr(
                batch.primary_document_candidates[0],
                "same_domain",
                False,
            ),
            "same_domain",
        ),
    ],
)
def test_inconsistent_bootstrap_provenance_is_rejected(mutation, message):
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    batch = _batch(mission, crawl_plan)
    mutation(batch)
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    with pytest.raises(ValueError, match=message):
        resolver.resolve(
            orchestrator,
            mission.contract.mission_id,
            plan=resolution_plan,
            bootstrap_results=[batch],
        )


def test_new_resolution_revision_preserves_history_and_supersedes_old_result():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    first_batch = _batch(mission, crawl_plan)
    first_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )
    first = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=first_plan,
        bootstrap_results=[first_batch],
    )
    orchestrator.record_turn(
        mission.contract.mission_id,
        plan=first_plan,
        outcome=first.outcome,
        feedback=first.recommended_feedback,
    )
    second_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity_link_evidence"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                target=mission.contract.mission_id,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(remaining_actions=8),
    )
    second_batch = _batch(
        mission,
        crawl_plan,
        document_id="document_corrected",
        path="official",
        name='ООО "Дедал Плюс"',
        inn="2465000007",
        ogrn="1232400000007",
        digest=DIGEST_B,
    )

    second = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=second_plan,
        bootstrap_results=[second_batch],
    )
    history = resolver.history(mission.contract.mission_id)

    assert second.revision_number == 2
    assert second.supersedes_result_id == first.id
    assert second.selected_candidate_id != first.selected_candidate_id
    assert [item.id for item in history.revisions] == [first.id, second.id]
    assert (
        history.revisions[0].candidates[0].canonical_name
        == 'ООО "Дедал"'
    )


def test_concurrent_identical_execution_creates_one_revision():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)
    batch = _batch(mission, crawl_plan)
    resolution_plan = _record_crawl_and_plan_resolution(
        orchestrator,
        mission,
        crawl_plan,
    )

    def execute():
        return resolver.resolve(
            orchestrator,
            mission.contract.mission_id,
            plan=resolution_plan,
            bootstrap_results=[batch],
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _index: execute(), range(8)))

    assert len({item.id for item in results}) == 1
    assert len(resolver.history(mission.contract.mission_id).revisions) == 1


@pytest.fixture(autouse=True)
def _reset_global_services():
    reset_mission_orchestrator()
    reset_entity_resolver()
    yield
    reset_mission_orchestrator()
    reset_entity_resolver()


def test_http_cycle_resolves_pending_plan_idempotently():
    with TestClient(app) as client:
        created = client.post(
            "/api/missions",
            json={
                "target_url": "https://example.test/",
                "goal": "Resolve the company identity.",
                "questions": [{"code": "identity"}],
            },
        )
        assert created.status_code == 200, created.text
        mission = created.json()
        mission_id = mission["contract"]["mission_id"]
        crawl_plan_response = client.post(
            f"/api/missions/{mission_id}/plan",
            json={
                "deficits": ["identity"],
                "candidates": [
                    {
                        "action_type": "crawl_url",
                        "target": "https://example.test/",
                        "deficit_code": "bootstrap",
                    }
                ],
                "policy": {
                    "allowed_hosts": ["example.test"],
                    "remaining_actions": 10,
                },
            },
        )
        assert crawl_plan_response.status_code == 200, crawl_plan_response.text
        crawl_plan = crawl_plan_response.json()
        fake_mission = SimpleNamespace(
            contract=SimpleNamespace(
                mission_id=mission_id,
                analysis_id=mission["contract"]["analysis_id"],
                correlation_id=mission["contract"]["correlation_id"],
            )
        )
        batch = _batch(
            fake_mission,
            NextActionPlan.model_validate(crawl_plan),
        )
        recorded = client.post(
            f"/api/missions/{mission_id}/turns",
            json={
                "plan": crawl_plan,
                "outcome": batch.outcome.model_dump(mode="json"),
                "feedback": {
                    "achieved": "L1",
                    "question_states": {"identity": "partially_verified"},
                    "critical_gaps": ["identity"],
                },
            },
        )
        assert recorded.status_code == 200, recorded.text
        resolution_plan_response = client.post(
            f"/api/missions/{mission_id}/plan",
            json={
                "deficits": ["identity"],
                "candidates": [
                    {
                        "action_type": "resolve_identity",
                        "target": mission_id,
                        "deficit_code": "identity",
                    }
                ],
                "policy": {"remaining_actions": 9},
            },
        )
        assert resolution_plan_response.status_code == 200
        resolution_plan = resolution_plan_response.json()
        payload = {
            "plan": resolution_plan,
            "bootstrap_results": [batch.model_dump(mode="json")],
        }
        first = client.post(
            f"/api/missions/{mission_id}/resolve-identity",
            json=payload,
        )
        repeated = client.post(
            f"/api/missions/{mission_id}/resolve-identity",
            json=payload,
        )
        assert first.status_code == 200, first.text
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["id"] == first.json()["id"]
        history = client.get(f"/api/missions/{mission_id}/identity-history")
        assert history.status_code == 200
        assert len(history.json()["revisions"]) == 1

        altered = deepcopy(payload)
        altered["bootstrap_results"][0]["identity_signals"][1]["value"] = "2465000007"
        conflict = client.post(
            f"/api/missions/{mission_id}/resolve-identity",
            json=altered,
        )
        assert conflict.status_code == 409
        assert "different input" in conflict.json()["detail"]
