import json

from app.hunter_forensic_trace import _compact_recommendation_controls_json
from scripts.search_observer_live_second_wave_compat import scorable_recommendations_compat


def test_compact_controls_drop_rationale_and_preserve_scoring_fields():
    evidence = {
        "recommendations": [
            {
                "direction_index": 0,
                "action": "continue",
                "confidence": 0.8,
                "rationale": "x" * 300,
                "refined_queries": [],
            },
            {
                "direction_index": 1,
                "action": "refine",
                "confidence": 0.7,
                "rationale": "y" * 300,
                "refined_queries": ["q1"],
            },
        ]
    }
    raw = _compact_recommendation_controls_json(evidence)
    assert json.loads(raw) == [
        {"direction_index": 0, "action": "continue", "confidence": 0.8},
        {"direction_index": 1, "action": "refine", "confidence": 0.7},
    ]
    assert "rationale" not in raw
    assert len(raw) < 4096


def test_live_compat_prefers_compact_controls_over_truncated_legacy_list():
    metadata = {
        "recommendation_controls_json": json.dumps(
            [
                {"direction_index": 0, "action": "continue", "confidence": 0.8},
                {"direction_index": 1, "action": "refine", "confidence": 0.7},
            ]
        ),
        "recommendations": [
            "{'direction_index': 0, 'action': 'continue', 'confidence': 0.8, 'rationale': 'truncated"
        ],
    }
    selected = scorable_recommendations_compat(metadata, direction_count=2)
    assert [(item["direction_index"], item["action"]) for item in selected] == [
        (0, "continue"),
        (1, "refine"),
    ]


def test_malformed_compact_controls_fail_closed_without_legacy_fallback():
    assert scorable_recommendations_compat(
        {
            "recommendation_controls_json": "not-json",
            "recommendations": [
                {"direction_index": 0, "action": "continue", "confidence": 0.8}
            ],
        },
        direction_count=1,
    ) == []
