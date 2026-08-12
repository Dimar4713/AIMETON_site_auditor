import pytest

from scripts.search_observer_live_second_wave import (
    MAX_INCREMENTAL_QUERIES,
    OWNER_HARD_CAP_RUB,
    _scorable_recommendations,
    parse_budget_rub,
)


def test_budget_must_stay_inside_owner_authorization():
    assert parse_budget_rub("100") == OWNER_HARD_CAP_RUB
    assert parse_budget_rub("0.01") > 0
    with pytest.raises(ValueError, match="live_validation_budget_outside_owner_authorization"):
        parse_budget_rub("100.01")
    with pytest.raises(ValueError, match="live_validation_budget_outside_owner_authorization"):
        parse_budget_rub("0")


def test_scorable_recommendations_are_direction_unique_bounded_and_skip_escalate():
    metadata = {
        "recommendations": [
            {"direction_index": 0, "action": "continue", "confidence": 0.8},
            {"direction_index": 0, "action": "boost", "confidence": 0.9},
            {"direction_index": 1, "action": "escalate", "confidence": 0.9},
            {"direction_index": 1, "action": "slow", "confidence": 0.6},
            {"direction_index": 99, "action": "stop", "confidence": 0.5},
        ]
    }
    selected = _scorable_recommendations(metadata, direction_count=2)
    assert [(item["direction_index"], item["action"]) for item in selected] == [
        (0, "continue"),
        (1, "slow"),
    ]
    assert len(selected) <= MAX_INCREMENTAL_QUERIES


def test_missing_recommendation_payload_is_inconclusive_not_executable():
    assert _scorable_recommendations({}, direction_count=2) == []
    assert _scorable_recommendations({"recommendations": "bad"}, direction_count=2) == []
