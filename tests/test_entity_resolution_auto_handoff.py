from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.document_pipeline.models import FetchPath
from app.entity_resolution import reset_entity_resolver
from app.evidence_crawler.models import (
    BootstrapCrawlResult,
    CrawledPage,
    CrawlStatus,
    IdentitySignal,
    IdentitySignalKind,
    PageType,
    RobotsState,
)
from app.main import app
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionLifecycle,
    PolicySnapshot,
    get_mission_orchestrator,
    reset_mission_orchestrator,
    default_site_mission_request,
)


DIGEST = f"sha256:{'c' * 64}"


def _bootstrap_batch():
    orchestrator = get_mission_orchestrator()
    mission = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )
    mission_id = mission.contract.mission_id
    plan = orchestrator.plan(
        mission_id,
        deficits=["identity", "contacts"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target="https://example.test/",
                deficit_code="bootstrap",
                expected_sufficiency_gain=0.4,
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_actions=10,
        ),
    )
    page = CrawledPage(
        requested_url="https://example.test/requisites",
        final_url="https://example.test/requisites",
        depth=1,
        page_type=PageType.REQUISITES,
        document_id="document_requisites",
        title="Реквизиты",
        accessed_at=datetime(2026, 7, 31, tzinfo=UTC),
        media_type="text/html",
        fetch_path=FetchPath.STATIC,
        raw_content_digest=DIGEST,
        normalized_content_digest=DIGEST,
        link_count=0,
    )
    signals = [
        IdentitySignal(
            kind=IdentitySignalKind.LEGAL_NAME,
            value='ООО "Дедал"',
            document_id=page.document_id,
            source_url=page.final_url,
            locator="css:#name",
        ),
        IdentitySignal(
            kind=IdentitySignalKind.INN,
            value="2400000009",
            document_id=page.document_id,
            source_url=page.final_url,
            locator="css:#inn",
        ),
        IdentitySignal(
            kind=IdentitySignalKind.OGRN,
            value="1022400000006",
            document_id=page.document_id,
            source_url=page.final_url,
            locator="css:#ogrn",
        ),
        IdentitySignal(
            kind=IdentitySignalKind.EMAIL,
            value="office@example.test",
            document_id=page.document_id,
            source_url=page.final_url,
            locator="css:#email",
        ),
    ]
    batch = BootstrapCrawlResult(
        status=CrawlStatus.COMPLETED,
        mission_id=mission_id,
        analysis_id=mission.contract.analysis_id,
        correlation_id=mission.contract.correlation_id,
        root_url="https://example.test/",
        plan=plan,
        robots_state=RobotsState.ALLOWED,
        pages=[page],
        identity_signals=signals,
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=[page.document_id],
        ),
    )
    return mission_id, batch


def setup_function() -> None:
    reset_mission_orchestrator()
    reset_entity_resolver()


def test_resolve_identity_without_client_plan_records_both_turns():
    mission_id, batch = _bootstrap_batch()

    response = TestClient(app).post(
        f"/api/missions/{mission_id}/resolve-identity",
        json={"bootstrap_results": [batch.model_dump(mode="json")]},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state"] == "provisional"
    assert payload["selected_candidate_id"]
    assert payload["plan"]["selected_action"]["action_type"] == "resolve_identity"

    snapshot = get_mission_orchestrator().get(mission_id)
    assert len(snapshot.turns) == 2
    assert snapshot.turns[0].selected_action.action_type == ActionType.CRAWL_URL
    assert snapshot.turns[1].selected_action.action_type == ActionType.RESOLVE_IDENTITY
    assert snapshot.lifecycle == MissionLifecycle.RUNNING
    assert snapshot.question_states["identity"] == "partially_verified"
    assert "document_requisites" in snapshot.artifact_refs


def test_auto_handoff_rejects_bootstrap_from_another_mission():
    mission_id, batch = _bootstrap_batch()
    other = get_mission_orchestrator().create_mission(
        default_site_mission_request("https://other.test/"),
        entry_point=EntryPoint.REST,
    )

    response = TestClient(app).post(
        f"/api/missions/{other.contract.mission_id}/resolve-identity",
        json={"bootstrap_results": [batch.model_dump(mode="json")]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "bootstrap result belongs to another mission"
    assert len(get_mission_orchestrator().get(mission_id).turns) == 0
