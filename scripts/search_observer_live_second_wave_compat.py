from __future__ import annotations

import ast

import scripts.search_observer_live_second_wave as target


_original_scorable_recommendations = target._scorable_recommendations


def _coerce_persisted_recommendation(item: object) -> dict[str, object] | None:
    if isinstance(item, dict):
        return item
    if not isinstance(item, str):
        return None
    try:
        parsed = ast.literal_eval(item)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def scorable_recommendations_compat(
    metadata: dict[str, object],
    direction_count: int,
) -> list[dict[str, object]]:
    raw = metadata.get("recommendations")
    if not isinstance(raw, list):
        return []
    normalized = [
        parsed
        for item in raw
        if (parsed := _coerce_persisted_recommendation(item)) is not None
    ]
    return _original_scorable_recommendations(
        {**metadata, "recommendations": normalized},
        direction_count,
    )


def main() -> int:
    target._scorable_recommendations = scorable_recommendations_compat
    return target.main()


if __name__ == "__main__":
    raise SystemExit(main())
