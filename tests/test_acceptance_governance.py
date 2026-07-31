from scripts.acceptance_governance import (
    open_checkboxes,
    validate_issue_closure,
    validate_pr_body,
)


def test_pr_requires_acceptance_section_and_issue_reference() -> None:
    result = validate_pr_body("## Summary\nDone")
    assert not result.ok
    assert len(result.errors) == 2


def test_valid_pr_body() -> None:
    body = """## Acceptance criteria affected
- exact criterion text

Part of #129.
"""
    assert validate_pr_body(body).ok


def test_issue_with_open_checkboxes_is_blocked() -> None:
    result = validate_issue_closure("## Criteria\n- [ ] pending\n")
    assert not result.ok
    assert open_checkboxes("- [ ] pending\n- [x] done") == ("pending",)


def test_issue_with_explicit_debt_transfer_is_allowed() -> None:
    body = """## Criteria
- [ ] pending

## Debt transfer
Remaining criterion transferred to #140.
"""
    assert validate_issue_closure(body).ok


def test_completed_issue_is_allowed() -> None:
    assert validate_issue_closure("- [x] done").ok
