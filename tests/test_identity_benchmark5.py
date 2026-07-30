from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from app.document_pipeline.extractor import extract_html
from app.document_pipeline.models import (
    DocumentDiagnostics,
    FetchPath,
    FetchedDocument,
)
from app.entity_resolution import (
    IdentityResolutionState,
    ProvisionalEntityResolver,
)
from app.entity_resolution.service import _normalized_legal_name
from app.evidence_crawler import BootstrapEvidenceCrawler
from app.evidence_crawler.models import (
    BootstrapCrawlResult,
    CrawledPage,
    CrawlStatus,
    IdentitySignal,
    PageType,
    RobotsState,
)
from app.mission_orchestrator import (
    ActionCandidate,
    ActionOutcome,
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
from app.sef.models import Document, DocumentFetchState


ROOT = Path(__file__).parents[1]
GOLDEN_PATH = ROOT / "benchmarks" / "sef" / "golden-5-v0.1.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "identity_benchmark5"
DIGEST = f"sha256:{'d' * 64}"


def _golden_cases() -> list[tuple[str, dict[str, str], str]]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    result = []
    for case in golden["cases"]:
        facts = {
            fact["predicate"]: fact["value"]
            for fact in case["facts"]
            if fact["predicate"] in {"legal_name", "inn", "ogrn", "official_domain"}
        }
        result.append((case["case_id"], facts, golden["golden_version"]))
    return result


def _fetched_document(case_id: str, url: str) -> FetchedDocument:
    html = (FIXTURE_ROOT / f"{case_id}.html").read_text(encoding="utf-8")
    extraction = extract_html(html, base_url=url)
    return FetchedDocument(
        document=Document(
            id=f"document_{case_id}",
            mission_id=f"mission_{case_id}",
            source_id=f"source_{case_id}",
            correlation_id=f"correlation_{case_id}",
            url=url,
            title=f"Identity benchmark {case_id}",
            accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
            fetch_status=DocumentFetchState.FETCHED,
            content_digest=DIGEST,
            media_type="text/html",
        ),
        raw_content_digest=f"sha256:{'e' * 64}",
        normalized_content_digest=DIGEST,
        normalized_text=extraction.text,
        blocks=extraction.blocks,
        links=extraction.links,
        tables=extraction.tables,
        diagnostics=DocumentDiagnostics(
            request_fingerprint=f"sha256:{'f' * 64}",
            path=FetchPath.STATIC,
            raw_bytes=len(html.encode("utf-8")),
            latency_ms=1,
        ),
    )


@pytest.mark.parametrize(
    ("case_id", "expected", "golden_version"),
    _golden_cases(),
    ids=lambda value: value if isinstance(value, str) and value.startswith("SEF-") else None,
)
def test_identity_benchmark5_resolves_exact_golden_company(
    case_id,
    expected,
    golden_version,
):
    root_url = f"https://{expected['official_domain']}/"
    source_url = f"{root_url}benchmark-requisites"
    fetched = _fetched_document(case_id, source_url)
    signals = BootstrapEvidenceCrawler._extract_identity_signals(fetched)
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission = orchestrator.create_mission(
        default_site_mission_request(root_url),
        entry_point=EntryPoint.REST,
    )
    crawl_plan = orchestrator.plan(
        mission.contract.mission_id,
        deficits=["identity"],
        candidates=[
            ActionCandidate(
                action_type=ActionType.CRAWL_URL,
                target=root_url,
                deficit_code="bootstrap",
            )
        ],
        policy=PolicySnapshot(
            allowed_hosts=frozenset({expected["official_domain"]}),
            remaining_actions=10,
        ),
    )
    page = CrawledPage(
        requested_url=source_url,
        final_url=source_url,
        depth=1,
        page_type=PageType.REQUISITES,
        document_id=fetched.document.id,
        title=fetched.document.title,
        accessed_at=fetched.document.accessed_at,
        media_type="text/html",
        fetch_path=FetchPath.STATIC,
        raw_content_digest=fetched.raw_content_digest,
        normalized_content_digest=fetched.normalized_content_digest,
        link_count=0,
    )
    batch = BootstrapCrawlResult(
        status=CrawlStatus.COMPLETED,
        mission_id=mission.contract.mission_id,
        analysis_id=mission.contract.analysis_id,
        correlation_id=mission.contract.correlation_id,
        root_url=root_url,
        plan=crawl_plan,
        robots_state=RobotsState.ALLOWED,
        pages=[page],
        identity_signals=[
            IdentitySignal.model_validate(
                {
                    **signal.model_dump(mode="json"),
                    "document_id": page.document_id,
                    "source_url": source_url,
                }
            )
            for signal in signals
        ],
        outcome=ActionOutcome(
            state=ActionOutcomeState.SUCCEEDED,
            artifact_refs=[page.document_id],
        ),
    )
    orchestrator.record_turn(
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

    result = resolver.resolve(
        orchestrator,
        mission.contract.mission_id,
        plan=resolution_plan,
        bootstrap_results=[batch],
    )

    assert golden_version == "0.1.0"
    assert result.state == IdentityResolutionState.PROVISIONAL
    selected = next(
        candidate
        for candidate in result.candidates
        if candidate.id == result.selected_candidate_id
    )
    actual = {
        identifier.scheme: identifier.normalized_value
        for identifier in selected.identifiers
        if identifier.scheme in {"legal_name", "inn", "ogrn"}
    }
    assert actual == {
        "legal_name": _normalized_legal_name(expected["legal_name"]),
        "inn": expected["inn"],
        "ogrn": expected["ogrn"],
    }
    assert selected.accepted_identifier_links == []
    assert not result.conflicts
