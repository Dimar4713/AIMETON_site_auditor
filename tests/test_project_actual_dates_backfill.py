from scripts.project_actual_dates_backfill import build_plan, plan_item


def project_item(content, dates=None):
    values = [
        {"date": value, "field": {"name": name}}
        for name, value in (dates or {}).items()
    ]
    return {
        "id": "PVTI_test",
        "content": content,
        "fieldValues": {"nodes": values},
    }


def test_pull_request_uses_created_and_merged_timestamps():
    item = project_item({
        "__typename": "PullRequest",
        "number": 120,
        "title": "targeted crawl",
        "state": "MERGED",
        "createdAt": "2026-07-31T08:10:00Z",
        "mergedAt": "2026-07-31T10:20:00Z",
        "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
    })
    proposal, conflict = plan_item(item)
    assert conflict is None
    assert proposal is not None
    assert proposal.updates == {
        "Actual start": "2026-07-31",
        "Actual finish": "2026-07-31",
    }
    assert "createdAt" in proposal.evidence["Actual start"]
    assert "mergedAt" in proposal.evidence["Actual finish"]


def test_issue_uses_earliest_cross_referenced_pr_and_closed_at():
    item = project_item({
        "__typename": "Issue",
        "number": 84,
        "title": "Entity Resolution",
        "state": "CLOSED",
        "createdAt": "2026-07-20T00:00:00Z",
        "closedAt": "2026-07-31T12:00:00Z",
        "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
        "timelineItems": {"nodes": [
            {"source": {
                "__typename": "PullRequest",
                "createdAt": "2026-07-29T09:00:00Z",
                "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
            }},
            {"source": {
                "__typename": "PullRequest",
                "createdAt": "2026-07-28T11:00:00Z",
                "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
            }},
        ]},
    })
    proposal, conflict = plan_item(item)
    assert conflict is None
    assert proposal is not None
    assert proposal.updates["Actual start"] == "2026-07-28"
    assert proposal.updates["Actual finish"] == "2026-07-31"


def test_issue_creation_date_is_not_used_as_execution_start():
    item = project_item({
        "__typename": "Issue",
        "number": 10,
        "title": "legacy issue",
        "state": "CLOSED",
        "createdAt": "2026-07-01T00:00:00Z",
        "closedAt": "2026-07-02T00:00:00Z",
        "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
        "timelineItems": {"nodes": []},
    })
    proposal, conflict = plan_item(item)
    assert proposal is None
    assert conflict is not None
    assert conflict["code"] == "finish_without_provable_start"


def test_existing_dates_are_not_overwritten_and_repeat_is_zero_delta():
    item = project_item({
        "__typename": "PullRequest",
        "number": 123,
        "title": "governance audit",
        "state": "MERGED",
        "createdAt": "2026-07-31T08:00:00Z",
        "mergedAt": "2026-07-31T09:00:00Z",
        "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
    }, {"Actual start": "2026-07-31", "Actual finish": "2026-07-31"})
    plan = build_plan([item])
    assert plan["items_with_proposals"] == 0
    assert plan["field_updates"] == 0
    assert plan["unresolved_count"] == 0
    assert plan["apply_allowed"] is True


def test_any_unresolved_item_blocks_apply():
    issue = project_item({
        "__typename": "Issue",
        "number": 10,
        "title": "legacy issue",
        "state": "CLOSED",
        "createdAt": "2026-07-01T00:00:00Z",
        "closedAt": "2026-07-02T00:00:00Z",
        "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
        "timelineItems": {"nodes": []},
    })
    plan = build_plan([issue])
    assert plan["unresolved_count"] == 1
    assert plan["apply_allowed"] is False
    assert plan["project_mutations"] == 0
