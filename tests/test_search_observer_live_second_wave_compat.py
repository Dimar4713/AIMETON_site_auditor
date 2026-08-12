from scripts.search_observer_live_second_wave_compat import (
    _coerce_persisted_recommendation,
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
