from app.search_observer_wave_plan import (
    assign_reserve_queries_to_directions,
    plan_bounded_search_waves,
    prioritize_reserve_queries,
)


def test_disabled_mode_preserves_legacy_single_wave_order():
    plan = plan_bounded_search_waves(
        ["q1", "q2", "q3"],
        steering_enabled=False,
        requested_reserve_queries=2,
    )

    assert plan.first_wave_queries == ["q1", "q2", "q3"]
    assert plan.reserve_queries == []
    assert plan.total_query_budget == 3
    assert plan.reserve_query_budget == 0
    assert plan.steering_enabled is False
    assert plan.reason_code == "legacy_single_wave"


def test_enabled_mode_holds_only_existing_queries_and_never_expands_budget():
    plan = plan_bounded_search_waves(
        ["q1", "q2", "q3", "q4", "q5", "q6"],
        steering_enabled=True,
        requested_reserve_queries=2,
    )

    assert plan.first_wave_queries == ["q1", "q2", "q3", "q4"]
    assert plan.reserve_queries == ["q5", "q6"]
    assert len(plan.first_wave_queries) + len(plan.reserve_queries) == plan.total_query_budget == 6
    assert plan.reserve_query_budget == 2
    assert plan.steering_enabled is True


def test_reserve_is_capped_at_half_and_first_wave_never_empty():
    plan = plan_bounded_search_waves(
        ["q1", "q2", "q3"],
        steering_enabled=True,
        requested_reserve_queries=99,
    )

    assert plan.first_wave_queries == ["q1", "q2"]
    assert plan.reserve_queries == ["q3"]
    assert plan.reserve_query_budget == 1


def test_normalization_deduplicates_before_budget_split():
    plan = plan_bounded_search_waves(
        [" q1 ", "q1", "Q1", "q2", "", " q3  x "],
        steering_enabled=True,
        requested_reserve_queries=1,
    )

    assert plan.first_wave_queries == ["q1", "q2"]
    assert plan.reserve_queries == ["q3 x"]
    assert plan.total_query_budget == 3


def test_zero_reserve_keeps_single_wave_even_when_gate_enabled():
    plan = plan_bounded_search_waves(
        ["q1", "q2"],
        steering_enabled=True,
        requested_reserve_queries=0,
    )

    assert plan.first_wave_queries == ["q1", "q2"]
    assert plan.reserve_queries == []
    assert plan.steering_enabled is False
    assert plan.reason_code == "reserve_not_configured"


def test_reserve_queries_map_to_closest_observed_direction_deterministically():
    assignments = assign_reserve_queries_to_directions(
        [
            "стоматология красноярск официальный сайт",
            "металлообработка красноярск завод",
        ],
        [
            "клиника стоматология красноярск",
            "завод металлообработка красноярск оборудование",
        ],
    )

    assert [item.direction_index for item in assignments] == [0, 1]
    assert all(item.lexical_overlap > 0 for item in assignments)


def test_continuation_priority_reorders_but_never_drops_reserve_work():
    assignments = assign_reserve_queries_to_directions(
        ["стоматология красноярск", "металлообработка красноярск"],
        ["металлообработка завод красноярск", "стоматология клиника красноярск"],
    )
    ordered = prioritize_reserve_queries(assignments, accepted_direction_indexes=[0])

    assert ordered == [
        "стоматология клиника красноярск",
        "металлообработка завод красноярск",
    ]
    assert set(ordered) == {item.query for item in assignments}
