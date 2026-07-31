from __future__ import annotations

from scripts.project_actual_dates_apply import (
    APPROVED_CUTOFF,
    EXPECTED_UNRESOLVED,
    approved_items,
)


def item(number: int, created_at: str | None) -> dict:
    return {
        "id": f"item-{number}",
        "content": {
            "__typename": "Issue",
            "number": number,
            "createdAt": created_at,
        },
    }


def test_approved_items_excludes_post_snapshot_cards() -> None:
    items = [
        item(1, "2026-07-31T12:31:59Z"),
        item(2, APPROVED_CUTOFF),
        item(3, "2026-07-31T12:32:01Z"),
    ]
    assert [entry["content"]["number"] for entry in approved_items(items)] == [1, 2]


def test_items_without_created_at_are_retained_fail_closed() -> None:
    items = [item(1, None)]
    assert approved_items(items) == items


def test_unresolved_manifest_is_exact_and_stable() -> None:
    assert EXPECTED_UNRESOLVED == {7, 19, 31, 32, 34}
