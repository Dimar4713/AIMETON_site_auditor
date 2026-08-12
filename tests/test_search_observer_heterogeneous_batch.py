from decimal import Decimal

import pytest

from scripts.search_observer_heterogeneous_batch import (
    DEFAULT_SCENARIO_SLUGS,
    ROTATION_SCENARIO_SLUGS,
    parse_budget_rub,
    select_scenarios,
)


def test_default_batch_is_heterogeneous_and_excludes_dentistry() -> None:
    scenarios = select_scenarios(())
    assert tuple(item.slug for item in scenarios) == DEFAULT_SCENARIO_SLUGS
    assert "dentistry-krasnoyarsk" not in DEFAULT_SCENARIO_SLUGS
    assert len({item.region for item in scenarios}) == len(scenarios)
    assert len({item.industry for item in scenarios}) == len(scenarios)


def test_rotation_batch_is_independent_and_heterogeneous() -> None:
    scenarios = select_scenarios(ROTATION_SCENARIO_SLUGS)
    assert len(scenarios) == 4
    assert set(ROTATION_SCENARIO_SLUGS).isdisjoint(DEFAULT_SCENARIO_SLUGS)
    assert "dentistry-krasnoyarsk" not in ROTATION_SCENARIO_SLUGS
    assert len({item.region for item in scenarios}) == len(scenarios)
    assert len({item.industry for item in scenarios}) == len(scenarios)


def test_batch_requires_unique_known_scenarios() -> None:
    with pytest.raises(ValueError, match="must_be_unique"):
        select_scenarios(("metalworking-ekaterinburg", "metalworking-ekaterinburg"))
    with pytest.raises(ValueError, match="unknown_scenario"):
        select_scenarios(("metalworking-ekaterinburg", "unknown"))


def test_batch_requires_two_to_four_scenarios() -> None:
    with pytest.raises(ValueError, match="2_to_4"):
        select_scenarios(("metalworking-ekaterinburg",))


def test_budget_is_bounded_by_standing_owner_cap() -> None:
    assert parse_budget_rub("100") == Decimal("100")
    assert parse_budget_rub("0.01") == Decimal("0.01")
    with pytest.raises(ValueError, match="outside_owner_authorization"):
        parse_budget_rub("100.01")
    with pytest.raises(ValueError, match="outside_owner_authorization"):
        parse_budget_rub("0")
