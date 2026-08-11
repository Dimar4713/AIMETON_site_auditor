from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ShadowBenchmarkScenario:
    slug: str
    region: str
    industry: str
    max_queries: int = 2
    results_per_query: int = 5
    max_candidates: int = 25
    output_limit: int = 10


SCENARIOS: tuple[ShadowBenchmarkScenario, ...] = (
    ShadowBenchmarkScenario(
        slug="dentistry-krasnoyarsk",
        region="Красноярск",
        industry="Стоматология",
    ),
    ShadowBenchmarkScenario(
        slug="metalworking-ekaterinburg",
        region="Екатеринбург",
        industry="Металлообработка",
    ),
    ShadowBenchmarkScenario(
        slug="accounting-novosibirsk",
        region="Новосибирск",
        industry="Бухгалтерские услуги",
    ),
    ShadowBenchmarkScenario(
        slug="industrial-equipment-kazan",
        region="Казань",
        industry="Промышленное оборудование",
    ),
)

# Current accepted Yandex accounting contract is RUB 0.01 per executed query.
YANDEX_ESTIMATED_COST_PER_QUERY_RUB = Decimal("0.01")
MAX_BENCHMARK_SEARCH_COST_RUB = Decimal("0.08")


def estimated_search_cost_rub(
    scenarios: tuple[ShadowBenchmarkScenario, ...] = SCENARIOS,
) -> Decimal:
    return sum(
        (Decimal(item.max_queries) * YANDEX_ESTIMATED_COST_PER_QUERY_RUB for item in scenarios),
        start=Decimal("0"),
    )


def validate_benchmark_contract() -> None:
    slugs = [item.slug for item in SCENARIOS]
    regions = [item.region for item in SCENARIOS]
    industries = [item.industry for item in SCENARIOS]

    if len(SCENARIOS) < 4:
        raise ValueError("shadow benchmark requires at least four heterogeneous scenarios")
    if len(set(slugs)) != len(slugs):
        raise ValueError("shadow benchmark scenario slugs must be unique")
    if len(set(regions)) < 4:
        raise ValueError("shadow benchmark must cover at least four regions")
    if len(set(industries)) < 4:
        raise ValueError("shadow benchmark must cover at least four industries")
    if any(item.max_queries > 2 for item in SCENARIOS):
        raise ValueError("shadow benchmark max_queries must remain bounded at 2")
    if any(item.output_limit > 10 for item in SCENARIOS):
        raise ValueError("shadow benchmark output_limit must remain bounded at 10")
    if estimated_search_cost_rub() > MAX_BENCHMARK_SEARCH_COST_RUB:
        raise ValueError("shadow benchmark estimated search cost exceeds hard cap")


if __name__ == "__main__":
    validate_benchmark_contract()
    print(f"scenario_count={len(SCENARIOS)}")
    print(f"estimated_search_cost_rub={estimated_search_cost_rub()}")
