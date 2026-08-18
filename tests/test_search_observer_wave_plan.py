from app.search_observer_wave_plan import plan_bounded_search_waves


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
