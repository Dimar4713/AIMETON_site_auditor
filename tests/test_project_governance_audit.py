from scripts.project_governance_audit import (
    audit_item,
    checkbox_counts,
    debt_transfer_target,
)


def _item(*, status, state="OPEN", merged=False, body="", dates=None, kind="Issue"):
    values = [
        {
            "name": status,
            "field": {"name": "Status"},
        }
    ]
    for name, date in (dates or {}).items():
        values.append({"date": date, "field": {"name": name}})
    return {
        "content": {
            "__typename": kind,
            "number": 84,
            "title": "Example",
            "body": body,
            "state": state,
            "merged": merged,
            "repository": {"nameWithOwner": "Dimar4713/AIMETON_site_auditor"},
        },
        "fieldValues": {"nodes": values},
    }


def test_checkbox_counts():
    assert checkbox_counts("- [ ] one\n- [x] two\n- [X] three") == (1, 2)


def test_active_item_requires_actual_start():
    findings = audit_item(_item(status="In Progress"))
    assert [item.code for item in findings] == ["active_without_actual_start"]


def test_completed_item_requires_finish_and_closed_checkboxes():
    findings = audit_item(
        _item(
            status="Done",
            state="CLOSED",
            body="## Критерии приёмки\n- [ ] unfinished",
            dates={"Actual start": "2026-07-29"},
        )
    )
    assert {item.code for item in findings} == {
        "completed_without_actual_finish",
        "completed_with_open_checkboxes",
    }


def test_checked_criterion_requires_evidence_section():
    findings = audit_item(
        _item(
            status="In Progress",
            body="## Критерии приёмки\n- [x] done",
            dates={"Actual start": "2026-07-29"},
        )
    )
    assert [item.code for item in findings] == ["checked_without_evidence_section"]


def test_consistent_item_is_clean():
    findings = audit_item(
        _item(
            status="Done",
            state="CLOSED",
            body="## Критерии приёмки\n- [x] done\n\n## Evidence of Done\nPR #1",
            dates={
                "Actual start": "2026-07-29",
                "Actual finish": "2026-07-30",
            },
        )
    )
    assert findings == []


def test_finish_before_start_is_reported():
    findings = audit_item(
        _item(
            status="Done",
            state="CLOSED",
            body="## Evidence of Done\nPR #1",
            dates={
                "Actual start": "2026-07-30",
                "Actual finish": "2026-07-29",
            },
        )
    )
    assert "actual_finish_before_start" in {item.code for item in findings}


def test_valid_debt_transfer_suppresses_only_checklist_evidence_findings():
    body = (
        "## Критерии приёмки\n- [ ] unfinished\n- [x] historical\n\n"
        "## Debt transfer\nHistorical debt is tracked in #138.\n"
    )
    assert debt_transfer_target(body) == 138
    findings = audit_item(
        _item(
            status="Done",
            state="CLOSED",
            body=body,
            dates={
                "Actual start": "2026-07-29",
                "Actual finish": "2026-07-30",
            },
        )
    )
    assert findings == []


def test_debt_transfer_without_issue_reference_does_not_suppress_findings():
    body = (
        "## Критерии приёмки\n- [ ] unfinished\n\n"
        "## Debt transfer\nWill be handled later.\n"
    )
    assert debt_transfer_target(body) is None
    findings = audit_item(
        _item(
            status="Done",
            state="CLOSED",
            body=body,
            dates={
                "Actual start": "2026-07-29",
                "Actual finish": "2026-07-30",
            },
        )
    )
    assert [item.code for item in findings] == ["completed_with_open_checkboxes"]
