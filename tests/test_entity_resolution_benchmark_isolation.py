from __future__ import annotations

import pytest

from app.entity_resolution import IdentityResolutionState, ProvisionalEntityResolver
from app.mission_orchestrator import MissionOrchestrator
from tests.test_entity_resolution import (
    DIGEST_B,
    _batch,
    _crawl_plan,
    _record_crawl_and_plan_resolution,
)


@pytest.mark.parametrize(
    (
        "left_name",
        "left_inn",
        "left_ogrn",
        "right_name",
        "right_inn",
        "right_ogrn",
    ),
    [
        (
            'ООО "Дедал Плюс"',
            "2400000009",
            "1022400000006",
            'ООО "Дедал Сервис"',
            "2465000007",
            "1232400000007",
        ),
        (
            'ООО "Славдом"',
            "7800000003",
            "1027800000005",
            'ООО "Славдом Красноярск"',
            "2460000005",
            "1242400000005",
        ),
        (
            'ИП Дедал',
            "246500000089",
            "323240000000007",
            'ООО "Дедал Плюс"',
            "2400000009",
            "1022400000006",
        ),
    ],
)
def test_identity_benchmark_keeps_cross_company_legal_facts_isolated(
    left_name: str,
    left_inn: str,
    left_ogrn: str,
    right_name: str,
    right_inn: str,
    right_ogrn: str,
):
    orchestrator = MissionOrchestrator()
    resolver = ProvisionalEntityResolver()
    mission, crawl_plan = _crawl_plan(orchestrator)

    left = _batch(
        mission,
        crawl_plan,
        document_id="document_left",
        path="left",
        name=left_name,
        inn=left_inn,
        ogrn=left_ogrn,
    )
    right = _batch(
        mission,
        crawl_plan,
        document_id="document_right",
        path="right",
        name=right_name,
        inn=right_inn,
        ogrn=right_ogrn,
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
        bootstrap_results=[left, right],
    )

    assert result.state == IdentityResolutionState.CONFLICTING
    assert result.selected_candidate_id is None
    assert len(result.candidates) == 2

    strong_identifier_sets = []
    for candidate in result.candidates:
        strong = {
            (identifier.scheme, identifier.normalized_value)
            for identifier in candidate.identifiers
            if identifier.scheme in {"inn", "ogrn"}
        }
        assert len(strong) == 2
        strong_identifier_sets.append(strong)

    expected = {
        frozenset({("inn", left_inn), ("ogrn", left_ogrn)}),
        frozenset({("inn", right_inn), ("ogrn", right_ogrn)}),
    }
    assert {frozenset(item) for item in strong_identifier_sets} == expected
    assert strong_identifier_sets[0].isdisjoint(strong_identifier_sets[1])
