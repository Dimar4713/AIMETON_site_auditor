import json

from app.search_observer_llm import (
    DirectionRecommendation,
    ObserverAction,
    SearchObserverRecommendation,
    _compact_recommendation_controls_json,
)
from scripts.search_observer_live_second_wave_compat import scorable_recommendations_compat


def _recommendation() -> SearchObserverRecommendation:
    return SearchObserverRecommendation(
        observer_mode="shadow",
        routing_changed=False,
        sufficient_evidence=True,
        summary="ok",
        recommendations=[
            DirectionRecommendation(
                direction_index=0,
                action=ObserverAction.CONTINUE,
                confidence=0.8,
                rationale="x" * 300,
                refined_queries=[],
            ),
            DirectionRecommendation(
                direction_index=1,
                action=ObserverAction.REFINE,
                confidence=0.7,
                rationale="y" * 300,
                refined_queries=["q1"],
            ),
        ],
    )


def test_compact_controls_are_scalar_json_without_rationale():
    raw = _compact_recommendation_controls_json(_recommendation())
    controls = json.loads(raw)
    assert controls == [
        {"direction_index": 0, "action": "continue", "confidence": 0.8},
        {"direction_index": 1, "action": "refine", "confidence": 0.7},
    ]
    assert "rationale" not in raw
    assert len(raw) < 4096


def test_live_compat_prefers_compact_controls_json():
    metadata = {
        "recommendation_controls_json": json.dumps(
            [
                {"direction_index": 0, "action": "continue", "confidence": 0.8},
                {"direction_index": 1, "action": "refine", "confidence": 0.7},
            ]
        ),
        "recommendations": ["{'direction_index': 0, 'action': 'continue', 'confidence': 0.8, 'rationale': 'truncated"],
    }
    selected = scorable_recommendations_compat(metadata, direction_count=2)
    assert [(item["direction_index"], item["action"]) for item in selected] == [
        (0, "continue"),
        (1, "refine"),
    ]


def test_malformed_compact_controls_fail_closed():
    assert scorable_recommendations_compat(
        {"recommendation_controls_json": "not-json"},
        direction_count=2,
    ) == []
