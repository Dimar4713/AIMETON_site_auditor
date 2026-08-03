import pytest
from pydantic import ValidationError

from app.ai_cost_accounting import AiCostAttempt, account_ai_attempt_costs


def test_cost_ledger_accounts_attempted_billed_and_accepted_costs():
    ledger = account_ai_attempt_costs(
        [
            AiCostAttempt(attempt=1, attempted_cost=0.02, billed_cost=0.01, accepted=False, accepted_cost=0),
            AiCostAttempt(attempt=2, attempted_cost=0.03, billed_cost=0.02, accepted=True, accepted_cost=0.02),
        ],
        max_attempts=2,
        budget=0.10,
    )
    assert ledger.status == "within_budget"
    assert ledger.attempted_cost == pytest.approx(0.05)
    assert ledger.billed_cost == pytest.approx(0.03)
    assert ledger.accepted_cost == pytest.approx(0.02)
    assert ledger.remaining_budget == pytest.approx(0.07)
    assert ledger.client_release_eligible is True


def test_cost_ledger_blocks_release_when_actual_billed_cost_exceeds_budget():
    ledger = account_ai_attempt_costs(
        [AiCostAttempt(attempt=1, attempted_cost=0.02, billed_cost=0.03, accepted=False, accepted_cost=0)],
        max_attempts=2,
        budget=0.02,
    )
    assert ledger.status == "budget_exceeded"
    assert ledger.billed_cost == pytest.approx(0.03)
    assert ledger.remaining_budget == 0
    assert ledger.client_release_eligible is False


def test_cost_ledger_rejects_attempts_beyond_retry_bound():
    with pytest.raises(ValueError, match="exceeds max_attempts"):
        account_ai_attempt_costs(
            [
                AiCostAttempt(attempt=1, attempted_cost=0, billed_cost=0, accepted=False, accepted_cost=0),
                AiCostAttempt(attempt=2, attempted_cost=0, billed_cost=0, accepted=False, accepted_cost=0),
                AiCostAttempt(attempt=3, attempted_cost=0, billed_cost=0, accepted=True, accepted_cost=0),
            ],
            max_attempts=2,
            budget=1,
        )


def test_cost_ledger_rejects_non_contiguous_attempt_numbers():
    with pytest.raises(ValueError, match="contiguous"):
        account_ai_attempt_costs(
            [AiCostAttempt(attempt=2, attempted_cost=0, billed_cost=0, accepted=False, accepted_cost=0)],
            max_attempts=2,
            budget=1,
        )


def test_accepted_cost_cannot_hide_or_invent_billed_cost():
    with pytest.raises(ValidationError, match="accepted_cost"):
        AiCostAttempt(attempt=1, attempted_cost=0.02, billed_cost=0.01, accepted=True, accepted_cost=0)
