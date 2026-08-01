#!/usr/bin/env python3
"""Compatibility entrypoint with fail-closed actual-date governance."""
from __future__ import annotations

import os

import project_status_sync as sync

EXECUTION_STATUSES = {"In Progress", "In Review", "Validation"}
NON_EXECUTION_REASONS = {"not_planned", "duplicate"}


def guarded_actual_date_updates(
    ctx: sync.Context,
    current_status: str | None,
    target_status: str,
    current_dates: dict[str, str],
) -> dict[str, str]:
    """Set start for every execution state and repair finish from terminal state."""
    updates: dict[str, str] = {}
    created_at = os.getenv("ITEM_CREATED_AT", "").strip()
    state_reason = os.getenv("ITEM_STATE_REASON", "").strip().casefold()

    if target_status in EXECUTION_STATUSES and "Actual start" not in current_dates:
        timestamp = (
            created_at
            if ctx.item_kind == "pull_request" and created_at
            else ctx.event_at or sync.datetime.now(sync.UTC).isoformat()
        )
        updates["Actual start"] = sync._date_from_timestamp(
            timestamp,
            "Actual start",
        )

    finish_timestamp = ""
    if ctx.item_kind == "issue" and ctx.item_state == "closed":
        if state_reason in NON_EXECUTION_REASONS:
            return updates
        finish_timestamp = ctx.item_closed_at
    elif ctx.item_kind == "pull_request" and ctx.pr_merged:
        finish_timestamp = ctx.pr_merged_at

    if finish_timestamp and "Actual finish" not in current_dates:
        effective_start = updates.get("Actual start") or current_dates.get("Actual start")
        if not effective_start and ctx.item_kind == "pull_request" and created_at:
            effective_start = sync._date_from_timestamp(created_at, "Actual start")
            updates["Actual start"] = effective_start
        if not effective_start:
            raise RuntimeError(
                "Refusing to write Actual finish without a provable Actual start"
            )
        updates["Actual finish"] = sync._date_from_timestamp(
            finish_timestamp,
            "Actual finish",
        )

    start = updates.get("Actual start") or current_dates.get("Actual start")
    finish = updates.get("Actual finish") or current_dates.get("Actual finish")
    if finish and not start:
        raise RuntimeError("Actual finish exists without Actual start")
    if start and finish and finish < start:
        raise RuntimeError(
            f"Actual finish {finish} is earlier than Actual start {start}"
        )
    return updates


sync.determine_actual_date_updates = guarded_actual_date_updates


if __name__ == "__main__":
    try:
        raise SystemExit(sync.main())
    except Exception as exc:  # noqa: BLE001
        print(f"Project status sync failed: {exc}", file=sync.sys.stderr)
        raise SystemExit(1)
