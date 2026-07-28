from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import project_status_sync as sync


def context(**overrides) -> sync.Context:
    values = {
        "token": "token",
        "project_owner": "owner",
        "project_number": 1,
        "content_node_id": "content",
        "repository": "owner/repo",
        "item_number": 75,
        "event_name": "issues",
        "event_action": "labeled",
        "item_kind": "issue",
        "item_state": "open",
        "item_title": "GOV-ROADMAP-01",
        "labels": {"status:in-progress"},
        "event_at": "2026-07-28T21:15:00Z",
    }
    values.update(overrides)
    return sync.Context(**values)


def project() -> dict:
    return {
        "id": "project",
        "title": "AIMETON",
        "fields": {
            "nodes": [
                {
                    "id": "status",
                    "name": "Status",
                    "dataType": "SINGLE_SELECT",
                    "options": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "ready", "name": "Ready"},
                        {"id": "progress", "name": "In Progress"},
                        {"id": "review", "name": "In Review"},
                        {"id": "validation", "name": "Validation"},
                        {"id": "blocked", "name": "Blocked"},
                        {"id": "done", "name": "Done"},
                    ],
                }
            ]
        },
        "views": {"nodes": []},
    }


class ProjectStatusDateTests(unittest.TestCase):
    def test_first_in_progress_transition_sets_actual_start_once(self):
        ctx = context()
        first = sync.determine_actual_date_updates(
            ctx,
            "Backlog",
            "In Progress",
            {},
        )
        repeated = sync.determine_actual_date_updates(
            ctx,
            "Blocked",
            "In Progress",
            {"Actual start": "2026-07-20"},
        )

        self.assertEqual(first, {"Actual start": "2026-07-28"})
        self.assertEqual(repeated, {})

    def test_issue_close_sets_actual_finish_from_closed_at(self):
        ctx = context(
            event_action="closed",
            item_state="closed",
            item_closed_at="2026-07-29T01:02:03Z",
            labels=set(),
        )

        updates = sync.determine_actual_date_updates(
            ctx,
            "Validation",
            "Done",
            {"Actual start": "2026-07-28"},
        )

        self.assertEqual(updates, {"Actual finish": "2026-07-29"})

    def test_merged_pr_sets_finish_but_closed_unmerged_pr_does_not(self):
        merged = context(
            item_kind="pull_request",
            event_action="closed",
            item_state="closed",
            pr_merged=True,
            pr_merged_at="2026-07-30T10:00:00Z",
            labels=set(),
        )
        abandoned = context(
            item_kind="pull_request",
            event_action="closed",
            item_state="closed",
            pr_merged=False,
            pr_merged_at="",
            labels=set(),
        )

        self.assertEqual(
            sync.determine_actual_date_updates(
                merged,
                "In Review",
                "Done",
                {"Actual start": "2026-07-28"},
            ),
            {"Actual finish": "2026-07-30"},
        )
        self.assertEqual(
            sync.determine_actual_date_updates(
                abandoned,
                "In Review",
                "Done",
                {"Actual start": "2026-07-28"},
            ),
            {},
        )

    def test_existing_actual_finish_is_immutable(self):
        ctx = context(
            event_action="closed",
            item_state="closed",
            item_closed_at="2026-08-01T00:00:00Z",
            labels=set(),
        )

        updates = sync.determine_actual_date_updates(
            ctx,
            "Validation",
            "Done",
            {
                "Actual start": "2026-07-28",
                "Actual finish": "2026-07-31",
            },
        )

        self.assertEqual(updates, {})

    def test_finish_before_start_fails_closed(self):
        ctx = context(
            event_action="closed",
            item_state="closed",
            item_closed_at="2026-07-27T00:00:00Z",
            labels=set(),
        )

        with self.assertRaisesRegex(RuntimeError, "earlier"):
            sync.determine_actual_date_updates(
                ctx,
                "Validation",
                "Done",
                {"Actual start": "2026-07-28"},
            )

    def test_ensure_schema_is_idempotent_and_dry_run_has_no_graphql(self):
        ctx = context(operation="ensure_schema", dry_run=True)
        value = project()

        with patch.object(
            sync,
            "graphql",
            side_effect=AssertionError(
                "dry-run must not call GraphQL mutations"
            ),
        ):
            first = sync.ensure_project_schema(ctx, value)
            second = sync.ensure_project_schema(ctx, value)

        self.assertEqual(
            first["created_fields"],
            list(sync.DATE_FIELDS),
        )
        self.assertEqual(
            first["created_views"],
            list(sync.ROADMAP_VIEWS),
        )
        self.assertEqual(
            second,
            {"created_fields": [], "created_views": []},
        )

    def test_wrong_existing_field_type_fails_without_mutation(self):
        ctx = context(operation="ensure_schema")
        value = project()
        value["fields"]["nodes"].append(
            {
                "id": "wrong",
                "name": "Actual start",
                "dataType": "TEXT",
            }
        )

        with patch.object(sync, "graphql") as mocked:
            with self.assertRaisesRegex(RuntimeError, "expected DATE"):
                sync.ensure_project_schema(ctx, deepcopy(value))
        mocked.assert_not_called()

    def test_ready_status_is_supported_case_insensitively(self):
        ctx = context(dry_run=True, manual_status="Ready")
        value = project()

        self.assertEqual(sync.choose_status(ctx, "Backlog"), "Ready")
        sync.update_status(ctx, value, "item", "ready")


if __name__ == "__main__":
    unittest.main()
