from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.document_pipeline import (
    DocumentPipeline,
    StaticHttpFetcher,
)
from app.document_pipeline.extractor import extract_html
from app.document_pipeline.models import (
    DocumentDiagnostics,
    FetchPath,
    FetchedDocument,
)
from app.evidence_crawler import (
    BootstrapCrawlPolicy,
    BootstrapEvidenceCrawler,
    CrawlStatus,
    MetadataFetcher,
    MetadataResponse,
    RobotsState,
)
from app.evidence_crawler.models import IdentitySignalKind
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
from app.sef.models import Document, DocumentFetchState


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "bootstrap"
IDENTITY_FIXTURES = ROOT / "tests" / "fixtures" / "entity_resolution"


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


def _fixture_document(filename: str) -> FetchedDocument:
    html = (IDENTITY_FIXTURES / filename).read_text(encoding="utf-8")
    url = f"https://example.test/{filename}"
    extraction = extract_html(html, base_url=url)
    digest = f"sha256:{'a' * 64}"
    return FetchedDocument(
        document=Document(
            id=f"document_{filename}",
            mission_id="mission_fixture",
            source_id="source_fixture",
            correlation_id="correlation_fixture",
            url=url,
            title=filename,
            accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
            fetch_status=DocumentFetchState.FETCHED,
            content_digest=digest,
            media_type="text/html",
        ),
        raw_content_digest=f"sha256:{'b' * 64}",
        normalized_content_digest=digest,
        normalized_text=extraction.text,
        blocks=extraction.blocks,
        links=extraction.links,
        tables=extraction.tables,
        diagnostics=DocumentDiagnostics(
            request_fingerprint=f"sha256:{'c' * 64}",
            path=FetchPath.STATIC,
            raw_bytes=len(html.encode("utf-8")),
            latency_ms=1,
        ),
    )


@pytest.mark.parametrize(
    ("filename", "expected_target", "expected_bank"),
    [
        ("selectel_requisites.html", "АО «Селектел»", None),
        ("sendy_requisites.html", 'ООО "СЭНДИ"', "ПАО «БАНК УРАЛСИБ»"),
        ("bsk_requisites.html", "ООО „Анатомика“", 'ПАО "СБЕРБАНК"'),
    ],
)
def test_real_world_identity_extraction_has_exact_boundaries(
    filename,
    expected_target,
    expected_bank,
):
    signals = BootstrapEvidenceCrawler._extract_identity_signals(
        _fixture_document(filename)
    )
    legal_names = [
        item.value
        for item in signals
        if item.kind == IdentitySignalKind.LEGAL_NAME
    ]
    addresses = [
        item.value
        for item in signals
        if item.kind == IdentitySignalKind.ADDRESS
    ]

    assert expected_target in legal_names
    if expected_bank is not None:
        assert expected_bank in legal_names
    assert all("официальный сайт" not in item.casefold() for item in legal_names)
    assert all("адреса и контакты" not in item.casefold() for item in addresses)


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
