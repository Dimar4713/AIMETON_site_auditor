from scripts.search_observer_live_second_wave_compat import (
    _coerce_persisted_recommendation,
    attach_shadow_decisions,
    rotated_scenarios_for_run,
    scorable_recommendations_compat,
)


def test_coerces_trace_sanitizer_stringified_recommendation():
    item = "{'direction_index': 0, 'action': 'continue', 'confidence': 0.8, 'rationale': 'ok'}"
    parsed = _coerce_persisted_recommendation(item)
    assert parsed == {
        'direction_index': 0,
        'action': 'continue',
        'confidence': 0.8,
        'rationale': 'ok',
    }


def test_compat_selector_preserves_existing_bounds_and_filters():
    metadata = {
        'recommendations': [
            "{'direction_index': 0, 'action': 'continue', 'confidence': 0.8}",
            "{'direction_index': 0, 'action': 'boost', 'confidence': 0.9}",
            "{'direction_index': 1, 'action': 'escalate', 'confidence': 0.9}",
            "{'direction_index': 1, 'action': 'refine', 'confidence': 0.7}",
        ]
    }
    selected = scorable_recommendations_compat(metadata, direction_count=2)
    assert [(item['direction_index'], item['action']) for item in selected] == [
        (0, 'continue'),
        (1, 'refine'),
    ]


def test_malformed_or_non_dict_literals_are_ignored_fail_closed():
    metadata = {
        'recommendations': [
            'not a literal',
            "['list', 'not', 'dict']",
            123,
        ]
    }
    assert scorable_recommendations_compat(metadata, direction_count=2) == []


def test_attach_shadow_decisions_emits_high_waste_quality_gain_without_routing_authority():
    evidence = {
        'scenarios': [{
            'state': 'scored',
            'outcomes': [{
                'score': {
                    'outcome': {
                        'added_queries': 1,
                        'added_raw_results': 20,
                        'added_unique_domains': 3,
                        'added_qualified_candidates': 3,
                        'added_direct_or_official_candidates': 0,
                        'duplicate_results': 0,
                        'excluded_results': 17,
                        'latency_ms': 1779,
                        'cost_rub': 0.01,
                    }
                }
            }],
        }]
    }
    result = attach_shadow_decisions(evidence)
    decision = result['scenarios'][0]['outcomes'][0]['shadow_second_wave_decision']
    assert decision['would_run_second_wave'] is True
    assert decision['quality_gain_observed'] is True
    assert decision['high_waste'] is True
    assert decision['waste_ratio'] == 0.85
    assert decision['reason_code'] == 'shadow_run_quality_gain_refine_high_waste'
    assert decision['routing_changed'] is False


def test_attach_shadow_decisions_marks_no_gain_high_waste_as_skip_candidate():
    evidence = {
        'scenarios': [{
            'outcomes': [{
                'score': {
                    'outcome': {
                        'added_queries': 1,
                        'added_raw_results': 10,
                        'added_unique_domains': 1,
                        'added_qualified_candidates': 0,
                        'added_direct_or_official_candidates': 0,
                        'duplicate_results': 4,
                        'excluded_results': 3,
                        'latency_ms': 1000,
                        'cost_rub': 0.01,
                    }
                }
            }],
        }]
    }
    decision = attach_shadow_decisions(evidence)['scenarios'][0]['outcomes'][0]['shadow_second_wave_decision']
    assert decision['would_run_second_wave'] is False
    assert decision['high_waste'] is True
    assert decision['reason_code'] == 'shadow_skip_no_quality_gain_high_waste'
    assert decision['routing_changed'] is False


def test_scenario_rotation_changes_first_scenario_without_changing_set_or_count():
    scenarios = ('dentistry', 'metalworking', 'accounting', 'equipment')
    run_1 = rotated_scenarios_for_run(1, scenarios)
    run_2 = rotated_scenarios_for_run(2, scenarios)
    run_5 = rotated_scenarios_for_run(5, scenarios)
    assert run_1 == scenarios
    assert run_2 == ('metalworking', 'accounting', 'equipment', 'dentistry')
    assert run_5 == scenarios
    assert set(run_2) == set(scenarios)
    assert len(run_2) == len(scenarios)


def test_scenario_rotation_fail_safe_for_bad_or_zero_run_number():
    scenarios = ('a', 'b', 'c')
    assert rotated_scenarios_for_run(0, scenarios) == scenarios
    assert rotated_scenarios_for_run(-10, scenarios) == scenarios
