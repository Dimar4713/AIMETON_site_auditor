from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_status_sync as sync  # noqa: E402
import project_status_sync_entry as entry  # noqa: E402


def context(**overrides: object) -> sync.Context:
    values = {
        "token": "token",
        "project_owner": "owner",
        "project_number": 1,
        "content_node_id": "node",
        "repository": "owner/repo",
        "item_number": 1,
        "event_name": "pull_request",
        "event_action": "opened",
        "item_kind": "pull_request",
        "item_state": "open",
        "event_at": "2026-07-31T12:00:00Z",
    }
    values.update(overrides)
    return sync.Context(**values)


def test_pr_in_review_gets_start_from_created_at(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITEM_CREATED_AT", "2026-07-30T09:00:00Z")
    updates = entry.guarded_actual_date_updates(
        context(), None, "In Review", {}
    )
    assert updates == {"Actual start": "2026-07-30"}


def test_merged_pr_gets_start_before_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITEM_CREATED_AT", "2026-07-30T09:00:00Z")
    updates = entry.guarded_actual_date_updates(
        context(
            event_action="closed",
            item_state="closed",
            pr_merged=True,
            pr_merged_at="2026-07-31T10:00:00Z",
        ),
        "In Review",
        "Done",
        {},
    )
    assert updates == {
        "Actual start": "2026-07-30",
        "Actual finish": "2026-07-31",
    }


def test_manual_repair_restores_merged_pr_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITEM_CREATED_AT", "2026-07-30T09:00:00Z")
    updates = entry.guarded_actual_date_updates(
        context(
            event_name="workflow_dispatch",
            event_action="workflow_dispatch",
            item_state="closed",
            pr_merged=True,
            pr_merged_at="2026-08-01T18:05:00Z",
        ),
        "Done",
        "Done",
        {"Actual start": "2026-07-30"},
    )
    assert updates == {"Actual finish": "2026-08-01"}


def test_issue_finish_without_start_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITEM_STATE_REASON", raising=False)
    with pytest.raises(RuntimeError, match="without a provable Actual start"):
        entry.guarded_actual_date_updates(
            context(
                event_name="issues",
                event_action="closed",
                item_kind="issue",
                item_state="closed",
                item_closed_at="2026-07-31T10:00:00Z",
            ),
            "Backlog",
            "Done",
            {},
        )


def test_manual_repair_restores_closed_issue_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ITEM_STATE_REASON", raising=False)
    updates = entry.guarded_actual_date_updates(
        context(
            event_name="workflow_dispatch",
            event_action="workflow_dispatch",
            item_kind="issue",
            item_state="closed",
            item_closed_at="2026-08-01T18:05:00Z",
        ),
        "Done",
        "Done",
        {"Actual start": "2026-07-30"},
    )
    assert updates == {"Actual finish": "2026-08-01"}


def test_not_planned_issue_does_not_get_execution_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITEM_STATE_REASON", "not_planned")
    updates = entry.guarded_actual_date_updates(
        context(
            event_name="issues",
            event_action="closed",
            item_kind="issue",
            item_state="closed",
            item_closed_at="2026-07-31T10:00:00Z",
        ),
        "Backlog",
        "Done",
        {},
    )
    assert updates == {}
