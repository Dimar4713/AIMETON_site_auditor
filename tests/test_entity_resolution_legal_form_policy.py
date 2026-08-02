from __future__ import annotations

from app.entity_resolution import IdentityResolutionState, ProvisionalEntityResolver
from app.mission_orchestrator import MissionOrchestrator
from tests.test_entity_resolution import (
    DIGEST_B,
    _batch,
    _crawl_plan,
    _record_crawl_and_plan_resolution,
)


def test_sole_proprietor_and_company_remain_distinct_without_linking_evidence():
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)

    company = _batch(
        mission,
        crawl_plan,
        document_id="document_dedal_company",
        path="company",
        name='ООО "Дедал Плюс"',
        inn="2400000009",
        ogrn="1022400000006",
    )
    proprietor = _batch(
        mission,
        crawl_plan,
        document_id="document_dedal_ip",
        path="ip",
        name='ИП Дедал',
        inn="246500000089",
        ogrn="323240000000007",
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
        bootstrap_results=[company, proprietor],
    )

    assert result.state == IdentityResolutionState.CONFLICTING
    assert result.selected_candidate_id is None
    assert len(result.candidates) == 2
    assert {candidate.entity_type for candidate in result.candidates} == {
        "company",
        "sole_proprietor",
    }
    assert all(candidate.state.value == "competing" for candidate in result.candidates)

    identifiers_by_type = {
        candidate.entity_type: {
            (identifier.scheme, identifier.normalized_value)
            for identifier in candidate.identifiers
        }
        for candidate in result.candidates
    }
    assert identifiers_by_type["company"] >= {
        ("inn", "2400000009"),
        ("ogrn", "1022400000006"),
    }
    assert identifiers_by_type["sole_proprietor"] >= {
        ("inn", "246500000089"),
        ("ogrn", "323240000000007"),
    }
    assert identifiers_by_type["company"].isdisjoint(
        identifiers_by_type["sole_proprietor"]
    )
