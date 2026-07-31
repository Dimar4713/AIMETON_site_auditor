from scripts.project_legacy_debt_transfer import desired_body


def test_appends_debt_transfer_without_touching_checkboxes() -> None:
    before = "## Criteria\n- [ ] pending\n- [x] done\n"
    after = desired_body(before, 138)
    assert "- [ ] pending" in after
    assert "- [x] done" in after
    assert "## Debt transfer" in after
    assert "#138" in after


def test_is_idempotent() -> None:
    once = desired_body("body", 138)
    assert desired_body(once, 138) == once
