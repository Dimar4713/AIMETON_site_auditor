from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.document_pipeline import (
    DocumentPipeline,
    StaticHttpFetcher,
)
from app.evidence_crawler import (
    BootstrapCrawlPolicy,
    BootstrapEvidenceCrawler,
    CrawlStatus,
    MetadataFetcher,
    MetadataResponse,
    RobotsState,
)
from app.entity_resolution import (
    IdentityResolutionState,
    ProvisionalEntityResolver,
)
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcomeState,
    ActionType,
    EntryPoint,
    MissionOrchestrator,
    PolicySnapshot,
    QuestionState,
    SufficiencyFeedback,
    SufficiencyLevel,
    default_site_mission_request,
)
from app.scraper import FetchError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "bootstrap"


class FakeMetadataFetcher(MetadataFetcher):
    def __init__(
        self,
        responses: dict[str, MetadataResponse] | None = None,
        *,
        error: FetchError | None = None,
    ) -> None:
        self.responses = responses or {}
        self.error = error
        self.calls: list[str] = []

    async def fetch_text(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_redirects: int = 4,
        allowed_hosts: frozenset[str] = frozenset(),
    ) -> MetadataResponse:
        del timeout_seconds, max_bytes, max_redirects, allowed_hosts
        self.calls.append(url)
        if self.error:
            raise self.error
        return self.responses.get(
            url,
            MetadataResponse(
                status_code=404,
                final_url=url,
                text="",
                media_type="",
            ),
        )


def _mission_and_plan(orchestrator: MissionOrchestrator):
    mission = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )
    plan = orchestrator.plan(
        mission.contract.mission_id,
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
            remaining_actions=5,
        ),
    )
    return mission, plan


@pytest.fixture
def document_pipeline(monkeypatch):
    monkeypatch.setattr(
        "app.document_pipeline.fetchers._validate_public_url",
        lambda _url: None,
    )
    pages = {
        "/": "root.html",
        "/contacts": "contacts.html",
        "/about": "about.html",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        filename = pages.get(request.url.path)
        if filename is None:
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(FIXTURES / filename).read_text(encoding="utf-8"),
        )

    return DocumentPipeline(
        static_fetcher=StaticHttpFetcher(
            transport=httpx.MockTransport(handler),
        )
    )


@pytest.mark.asyncio
async def test_bootstrap_turn_respects_robots_and_feeds_identity_replan(
    document_pipeline,
):
    metadata = FakeMetadataFetcher(
        {
            "https://example.test/robots.txt": MetadataResponse(
                status_code=200,
                final_url="https://example.test/robots.txt",
                text=(
                    "User-agent: *\n"
                    "Allow: /\n"
                    "Disallow: /private\n"
                    "Sitemap: https://example.test/sitemap.xml\n"
                ),
                media_type="text/plain",
            ),
            "https://example.test/sitemap.xml": MetadataResponse(
                status_code=200,
                final_url="https://example.test/sitemap.xml",
                text=(
                    "<urlset>"
                    "<url><loc>https://example.test/about</loc></url>"
                    "<url><loc>https://example.test/contacts</loc></url>"
                    "</urlset>"
                ),
                media_type="application/xml",
            ),
        }
    )
    crawler = BootstrapEvidenceCrawler(
        document_pipeline=document_pipeline,
        metadata_fetcher=metadata,
    )
    orchestrator = MissionOrchestrator()
    mission, plan = _mission_and_plan(orchestrator)

    result = await crawler.run_mission(
        orchestrator,
        mission.contract.mission_id,
        plan=plan,
        policy=BootstrapCrawlPolicy(
            max_pages=5,
            max_depth=2,
            min_request_interval_ms=0,
            allow_crawl4ai=False,
            allow_browser=False,
        ),
    )

    assert result.status == CrawlStatus.COMPLETED, result.model_dump(mode="json")
    assert result.robots_state == RobotsState.ALLOWED
    assert {page.page_type for page in result.pages} >= {
        "root",
        "contacts",
        "about",
    }
    assert [str(url) for url in result.blocked_urls] == [
        "https://example.test/private"
    ]
    assert all(page.accessed_at for page in result.pages)
    assert all(page.media_type == "text/html" for page in result.pages)
    assert all(page.fetch_path == "static" for page in result.pages)
    assert all(page.title for page in result.pages)
    values = {(signal.kind, signal.value) for signal in result.identity_signals}
    assert ("inn", "2400000000") in values
    assert ("ogrn", "1022400000000") in values
    assert ("email", "office@dedal.example") in values
    assert ("phone", "+73912223344") in values
    assert any(kind == "address" for kind, _ in values)
    assert all(signal.locator for signal in result.identity_signals)
    assert len(result.outcome.artifact_refs) == len(result.pages)
    assert result.outcome.state == ActionOutcomeState.SUCCEEDED
    repeated = await crawler.run_mission(
        orchestrator,
        mission.contract.mission_id,
        plan=plan,
        policy=BootstrapCrawlPolicy(
            max_pages=1,
            min_request_interval_ms=0,
        ),
    )
    assert repeated == result
    candidates = {
        (item.action_type, item.target)
        for item in result.next_action_candidates
    }
    assert (ActionType.RESOLVE_IDENTITY, mission.contract.mission_id) in candidates
    assert (
        ActionType.FETCH_DOCUMENT,
        "https://example.test/files/requisites.pdf",
    ) in candidates
    external = next(
        item
        for item in result.primary_document_candidates
        if "cdn.other.test" in str(item.url)
    )
    assert external.same_domain is False
    assert external.lifecycle_state == "discovery_hint"
    assert "do-not-expose" not in result.model_dump_json()
    assert "query_url_skipped" in result.reason_codes

    after_crawl = orchestrator.record_turn(
        mission.contract.mission_id,
        plan=plan,
        outcome=result.outcome,
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L1,
            question_states={
                "identity": QuestionState.PARTIALLY_VERIFIED,
                "contacts": QuestionState.PARTIALLY_VERIFIED,
            },
            critical_gaps=["identity"],
        ),
    )
    next_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=after_crawl.turns[-1].resulting_gaps,
        candidates=result.next_action_candidates,
        policy=PolicySnapshot(
            allowed_hosts=frozenset({"example.test"}),
            remaining_actions=4,
        ),
    )
    assert next_plan.turn_number == 2
    assert next_plan.selected_action.action_type == ActionType.RESOLVE_IDENTITY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "expected_name", "expected_inn", "expected_ogrn"),
    [
        (
            "realworld_selectel_sanitized.html",
            "Акционерное общество «Селектел»",
            "7810962785",
            "1247800067790",
        ),
        (
            "realworld_sendy_sanitized.html",
            "Общество с ограниченной ответственностью «СЭНДИ»",
            "7720644026",
            "1207700230638",
        ),
        (
            "realworld_bsk_sanitized.html",
            "Общество с ограниченной ответственностью «Анатомика»",
            "2308284006",
            "1222300007225",
        ),
    ],
)
async def test_realworld_requisites_normalize_to_one_provisional_target(
    monkeypatch,
    fixture_name,
    expected_name,
    expected_inn,
    expected_ogrn,
):
    monkeypatch.setattr(
        "app.document_pipeline.fetchers._validate_public_url",
        lambda _url: None,
    )
    html = (FIXTURES / fixture_name).read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=html,
        )

    crawler = BootstrapEvidenceCrawler(
        document_pipeline=DocumentPipeline(
            static_fetcher=StaticHttpFetcher(
                transport=httpx.MockTransport(handler),
            )
        ),
        metadata_fetcher=FakeMetadataFetcher(),
    )
    orchestrator = MissionOrchestrator()
    mission, crawl_plan = _mission_and_plan(orchestrator)
    batch = await crawler.run_mission(
        orchestrator,
        mission.contract.mission_id,
        plan=crawl_plan,
        policy=BootstrapCrawlPolicy(
            max_pages=1,
            max_depth=0,
            min_request_interval_ms=0,
            allow_crawl4ai=False,
            allow_browser=False,
        ),
    )
    assert not any(
        signal.kind == "address"
        and signal.value.casefold() in {"а и контакты", "и контакты"}
        for signal in batch.identity_signals
    )

    after_crawl = orchestrator.record_turn(
        mission.contract.mission_id,
        plan=crawl_plan,
        outcome=batch.outcome,
        feedback=SufficiencyFeedback(
            achieved=SufficiencyLevel.L1,
            question_states={"identity": QuestionState.PARTIALLY_VERIFIED},
            critical_gaps=["identity"],
        ),
    )
    resolution_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=after_crawl.turns[-1].resulting_gaps,
        candidates=batch.next_action_candidates,
        policy=PolicySnapshot(remaining_actions=4),
    )
    resolver = ProvisionalEntityResolver()
    result = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[batch],
    )

    assert result.state == IdentityResolutionState.PROVISIONAL
    assert result.selected_candidate_id is not None
    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.id == result.selected_candidate_id
    )
    assert selected.canonical_name == expected_name
    assert {
        (identifier.scheme, identifier.normalized_value)
        for identifier in selected.identifiers
    } >= {
        ("inn", expected_inn),
        ("ogrn", expected_ogrn),
    }
    assert all(
        "банк" not in candidate.canonical_name.casefold()
        for candidate in result.candidates
        if candidate.id == result.selected_candidate_id
    )
    for candidate in result.candidates:
        if "банк" not in candidate.canonical_name.casefold():
            continue
        assert {
            identifier.scheme for identifier in candidate.identifiers
        } == {"legal_name"}


@pytest.mark.asyncio
async def test_robots_unavailable_blocks_before_document_fetch():
    class NeverFetchPipeline:
        calls = 0

        async def fetch(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("document fetch must not start")

    pipeline = NeverFetchPipeline()
    crawler = BootstrapEvidenceCrawler(
        document_pipeline=pipeline,
        metadata_fetcher=FakeMetadataFetcher(
            error=FetchError("robots network failure")
        ),
    )
    orchestrator = MissionOrchestrator()
    mission, plan = _mission_and_plan(orchestrator)

    result = await crawler.run_mission(
        orchestrator,
        mission.contract.mission_id,
        plan=plan,
        policy=BootstrapCrawlPolicy(min_request_interval_ms=0),
    )

    assert result.status == CrawlStatus.BLOCKED
    assert result.robots_state == RobotsState.UNAVAILABLE
    assert result.pages == []
    assert result.outcome.state == ActionOutcomeState.BLOCKED
    assert result.reason_codes == ["robots_unavailable"]
    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_bootstrap_rejects_unissued_or_cross_mission_plan(
    document_pipeline,
):
    crawler = BootstrapEvidenceCrawler(
        document_pipeline=document_pipeline,
        metadata_fetcher=FakeMetadataFetcher(),
    )
    orchestrator = MissionOrchestrator()
    first, plan = _mission_and_plan(orchestrator)
    second = orchestrator.create_mission(
        default_site_mission_request("https://example.test/"),
        entry_point=EntryPoint.REST,
    )

    with pytest.raises(ValueError, match="another mission|not issued"):
        await crawler.run_mission(
            orchestrator,
            second.contract.mission_id,
            plan=plan,
        )

    assert orchestrator.get(first.contract.mission_id).turns == []
