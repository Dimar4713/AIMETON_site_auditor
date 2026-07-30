from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from app.document_pipeline import DocumentPipeline, FetchPath, StaticHttpFetcher
from app.entity_resolution import ProvisionalEntityResolver
from app.evidence_crawler.models import (
    BootstrapCrawlResult,
    CrawledPage,
    CrawlStatus,
    IdentitySignal,
    IdentitySignalKind,
    PageType,
    RobotsState,
)
from app.identity_evidence import EvidenceGuardState, IdentityEvidenceService
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionBudget,
    MissionOrchestrator,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
    default_site_mission_request,
)
from app.search_gateway import SearchGateway
from app.search_gateway.providers import TavilyProvider
from scripts.export_identity_evidence_schemas import TARGETS, render_schema


DIGEST = f"sha256:{'a' * 64}"


def test_committed_identity_evidence_schemas_are_current_and_valid():
    for target, model in TARGETS.items():
        content = target.read_text(encoding="utf-8")
        assert content == render_schema(model)
        Draft202012Validator.check_schema(json.loads(content))


def _mission_and_identity(
    orchestrator: MissionOrchestrator,
    resolver: ProvisionalEntityResolver,
):
    request = default_site_mission_request("https://example.test/")
    request.budget = MissionBudget(
        max_cost_by_currency={"USD": Decimal("0.016")},
        max_actions=10,
    )
    mission = orchestrator.create_mission(request, entry_point=EntryPoint.REST)
    mission_id = mission.contract.mission_id
    crawl_plan = orchestrator.plan(
        mission_id,
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
            remaining_cost_by_currency={"USD": Decimal("0.016")},
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
        accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
        media_type="text/html",
        fetch_path=FetchPath.STATIC,
        raw_content_digest=DIGEST,
        normalized_content_digest=DIGEST,
        link_count=0,
    )
    batch = BootstrapCrawlResult(
        status=CrawlStatus.COMPLETED,
        mission_id=mission_id,
        analysis_id=mission.contract.analysis_id,
        correlation_id=mission.contract.correlation_id,
        root_url="https://example.test/",
        plan=crawl_plan,
        robots_state=RobotsState.ALLOWED,
        pages=[page],
        identity_signals=[
            IdentitySignal(
                kind=kind,
                value=value,
                document_id=page.document_id,
                source_url=page.final_url,
                locator=f"body/{kind.value}",
            )
            for kind, value in (
                (IdentitySignalKind.LEGAL_NAME, 'ООО "Дедал"'),
                (IdentitySignalKind.INN, "2400000009"),
                (IdentitySignalKind.OGRN, "1022400000006"),
            )
        ],
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=[page.document_id],
        ),
    )
    orchestrator.record_turn(
        mission_id,
        plan=crawl_plan,
        outcome=batch.outcome,
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L1,
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )
    resolution_plan = orchestrator.plan(
        mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.RESOLVE_IDENTITY,
                target=mission_id,
                deficit_code="identity",
            )
        ],
        policy=PolicySnapshot(
            remaining_cost_by_currency={"USD": Decimal("0.016")},
            remaining_actions=9,
        ),
    )
    identity = resolver.resolve(
        orchestrator,
        mission_id,
        plan=resolution_plan,
        bootstrap_results=[batch],
    )
    orchestrator.record_turn(
        mission_id,
        plan=resolution_plan,
        outcome=identity.outcome,
        feedback=identity.recommended_feedback,
    )
    query_plan = orchestrator.plan(
        mission_id,
        deficits=identity.gaps,
        candidates=identity.next_action_candidates,
        policy=PolicySnapshot(
            remaining_cost_by_currency={"USD": Decimal("0.016")},
            remaining_actions=8,
        ),
    )
    assert query_plan.selected_action.action_type == ActionType.QUERY_PROVIDER
    return mission, identity, query_plan


def _service(
    document_html: str,
) -> tuple[IdentityEvidenceService, ProvisionalEntityResolver]:
    def search_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tvly-test"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.test/current-requisites",
                        "title": "Реквизиты ООО Дедал",
                        "content": (
                            "Search snippet with candidate identifiers; "
                            "it must remain a discovery hint."
                        ),
                    }
                ]
            },
        )

    def document_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=document_html,
        )

    resolver = ProvisionalEntityResolver()
    service = IdentityEvidenceService(
        search_gateway=SearchGateway(
            [
                TavilyProvider(
                    "tvly-test",
                    cost_amount=Decimal("0.008"),
                    transport=httpx.MockTransport(search_handler),
                )
            ],
            global_quotas={"tavily": 10},
        ),
        document_pipeline=DocumentPipeline(
            static_fetcher=StaticHttpFetcher(
                transport=httpx.MockTransport(document_handler)
            )
        ),
        entity_resolver=resolver,
    )
    return service, resolver


@pytest.fixture(autouse=True)
def _identity_search_environment(monkeypatch):
    monkeypatch.setenv("TAVILY_TOKEN", "tvly-test")
    monkeypatch.setenv("TAVILY_SEARCH_COST_USD", "0.008")
    monkeypatch.setenv("SEARCH_MISSION_BUDGET_USD", "0.008")
    monkeypatch.setenv("IDENTITY_SEARCH_PROVIDER_ORDER", "tavily")
    monkeypatch.setattr(
        "app.document_pipeline.fetchers._validate_public_url",
        lambda _url: None,
    )


@pytest.mark.asyncio
async def test_tavily_hint_requires_fetch_and_guard_before_accepted_links():
    service, resolver = _service(
        """
        <html><head><title>Реквизиты ООО Дедал</title></head>
        <body><main>
          <h1>ООО "Дедал"</h1>
          <p>Официальные реквизиты компании и контактная информация.</p>
          <p>ИНН: 2400000009</p>
          <p>ОГРН: 1022400000006</p>
        </main></body></html>
        """
    )
    orchestrator = MissionOrchestrator()
    mission, identity, query_plan = _mission_and_identity(orchestrator, resolver)
    mission_id = mission.contract.mission_id

    search = await service.search_identity(
        orchestrator,
        mission_id,
        plan=query_plan,
        identity_result_id=identity.id,
    )

    assert search.provider_call.provider_ref == "tavily"
    assert len(search.discovery_hints) == 1
    assert search.outcome.actual_cost_by_currency == {"USD": Decimal("0.008")}
    selected_before = next(
        item
        for item in resolver.history(mission_id).revisions[-1].candidates
        if item.id == identity.selected_candidate_id
    )
    assert selected_before.accepted_identifier_links == []

    orchestrator.record_turn(
        mission_id,
        plan=query_plan,
        outcome=search.outcome,
        feedback=search.recommended_feedback,
    )
    fetch_plan = orchestrator.plan(
        mission_id,
        deficits=["identity_link_evidence"],
        candidates=search.next_action_candidates,
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_cost_by_currency={"USD": Decimal("0.008")},
            remaining_actions=7,
        ),
    )
    promoted = await service.promote_identity_evidence(
        orchestrator,
        mission_id,
        plan=fetch_plan,
        identity_result_id=identity.id,
        identity_search_result_id=search.id,
    )

    assert promoted.guard_state == EvidenceGuardState.ACCEPTED
    assert {item.identifier.scheme for item in promoted.accepted} == {"inn", "ogrn"}
    assert all(item.evidence.locator for item in promoted.accepted)
    assert all(item.evidence.document_id == promoted.document.id for item in promoted.accepted)
    assert promoted.identity_revision is not None
    selected_after = next(
        item
        for item in promoted.identity_revision.candidates
        if item.id == identity.selected_candidate_id
    )
    assert set(selected_after.accepted_identifier_links) == {
        item.identifier.id for item in promoted.accepted
    }
    assert "official_registry_verification" in promoted.identity_revision.gaps
    assert {
        item.action_type for item in promoted.next_action_candidates
    } >= {ActionType.CRAWL_URL, ActionType.QUERY_PROVIDER}
    assert len(resolver.history(mission_id).revisions) == 2


@pytest.mark.asyncio
async def test_competing_valid_identifier_blocks_all_automatic_promotion():
    service, resolver = _service(
        """
        <html><head><title>Каталог организаций</title></head>
        <body><main>
          <h1>ООО "Дедал"</h1>
          <p>ИНН: 2400000009</p>
          <p>ОГРН: 1022400000006</p>
          <p>Связанная карточка ООО "Дедал Плюс", ИНН: 2465000007</p>
        </main></body></html>
        """
    )
    orchestrator = MissionOrchestrator()
    mission, identity, query_plan = _mission_and_identity(orchestrator, resolver)
    mission_id = mission.contract.mission_id
    search = await service.search_identity(
        orchestrator,
        mission_id,
        plan=query_plan,
        identity_result_id=identity.id,
    )
    orchestrator.record_turn(
        mission_id,
        plan=query_plan,
        outcome=search.outcome,
        feedback=search.recommended_feedback,
    )
    fetch_plan = orchestrator.plan(
        mission_id,
        deficits=["identity_link_evidence"],
        candidates=search.next_action_candidates,
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_cost_by_currency={"USD": Decimal("0.008")},
            remaining_actions=7,
        ),
    )

    blocked = await service.promote_identity_evidence(
        orchestrator,
        mission_id,
        plan=fetch_plan,
        identity_result_id=identity.id,
        identity_search_result_id=search.id,
    )

    assert blocked.guard_state == EvidenceGuardState.BLOCKED
    assert blocked.accepted == []
    assert blocked.identity_revision is None
    assert "identity_competing_identifier_found" in blocked.guard_reason_codes
    assert len(resolver.history(mission_id).revisions) == 1


@pytest.mark.asyncio
async def test_search_and_promotion_are_idempotent_per_issued_plan():
    service, resolver = _service(
        """
        <html><head><title>Реквизиты</title></head>
        <body><main><h1>ООО "Дедал"</h1>
        <p>ИНН: 2400000009</p><p>ОГРН: 1022400000006</p>
        </main></body></html>
        """
    )
    orchestrator = MissionOrchestrator()
    mission, identity, query_plan = _mission_and_identity(orchestrator, resolver)
    mission_id = mission.contract.mission_id
    first_search = await service.search_identity(
        orchestrator,
        mission_id,
        plan=query_plan,
        identity_result_id=identity.id,
    )
    repeated_search = await service.search_identity(
        orchestrator,
        mission_id,
        plan=query_plan,
        identity_result_id=identity.id,
    )
    assert repeated_search.id == first_search.id

    orchestrator.record_turn(
        mission_id,
        plan=query_plan,
        outcome=first_search.outcome,
        feedback=first_search.recommended_feedback,
    )
    fetch_plan = orchestrator.plan(
        mission_id,
        deficits=["identity_link_evidence"],
        candidates=first_search.next_action_candidates,
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_cost_by_currency={"USD": Decimal("0.008")},
            remaining_actions=7,
        ),
    )
    first = await service.promote_identity_evidence(
        orchestrator,
        mission_id,
        plan=fetch_plan,
        identity_result_id=identity.id,
        identity_search_result_id=first_search.id,
    )
    repeated = await service.promote_identity_evidence(
        orchestrator,
        mission_id,
        plan=fetch_plan,
        identity_result_id=identity.id,
        identity_search_result_id=first_search.id,
    )
    assert repeated.id == first.id
    assert len(resolver.history(mission_id).revisions) == 2
