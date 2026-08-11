from decimal import Decimal

from scripts.search_observer_shadow_benchmark import (
    MAX_BENCHMARK_SEARCH_COST_RUB,
    SCENARIOS,
    estimated_search_cost_rub,
    validate_benchmark_contract,
)


def test_shadow_benchmark_contract_is_heterogeneous_and_bounded() -> None:
    validate_benchmark_contract()
    assert len(SCENARIOS) == 4
    assert len({item.region for item in SCENARIOS}) == 4
    assert len({item.industry for item in SCENARIOS}) == 4
    assert all(item.max_queries == 2 for item in SCENARIOS)
    assert all(item.output_limit == 10 for item in SCENARIOS)


def test_shadow_benchmark_search_cost_is_hard_capped() -> None:
    assert estimated_search_cost_rub() == Decimal("0.08")
    assert estimated_search_cost_rub() <= MAX_BENCHMARK_SEARCH_COST_RUB


def test_shadow_benchmark_contains_reference_dentistry_case() -> None:
    reference = next(item for item in SCENARIOS if item.slug == "dentistry-krasnoyarsk")
    assert reference.region == "Красноярск"
    assert reference.industry == "Стоматология"
