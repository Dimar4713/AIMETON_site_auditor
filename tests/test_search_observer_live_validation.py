import pytest
from pydantic import ValidationError

from app.search_observer_live_validation import LiveSecondWaveValidationContract


def test_default_contract_is_zero_cost_and_fail_closed():
    contract = LiveSecondWaveValidationContract()
    assert contract.wave_count == 2
    assert contract.max_incremental_queries == 4
    assert contract.zero_cost_only is True
    assert contract.spend_gate_open is False
    assert contract.routing_changed is False
    assert contract.allow_premium_escalation is False


def test_paid_calls_require_explicit_owner_authorization():
    with pytest.raises(ValidationError, match="paid_calls_require_owner_spend_authorization"):
        LiveSecondWaveValidationContract(
            allow_paid_calls=True,
            max_incremental_cost_rub=0.02,
            owner_spend_authorized=False,
        )


def test_positive_cost_requires_paid_calls_enabled():
    with pytest.raises(ValidationError, match="positive_cost_requires_paid_calls_enabled"):
        LiveSecondWaveValidationContract(
            max_incremental_cost_rub=0.02,
            owner_spend_authorized=True,
        )


def test_explicitly_authorized_bounded_spend_only_opens_gate():
    contract = LiveSecondWaveValidationContract(
        allow_paid_calls=True,
        max_incremental_cost_rub=0.02,
        owner_spend_authorized=True,
    )
    assert contract.spend_gate_open is True
    assert contract.zero_cost_only is False


def test_routing_change_is_rejected():
    with pytest.raises(ValidationError, match="live_validation_requires_routing_unchanged"):
        LiveSecondWaveValidationContract(routing_changed=True)


def test_provider_policy_and_runtime_safety_authority_are_required():
    with pytest.raises(ValidationError, match="live_validation_requires_provider_policy_authority"):
        LiveSecondWaveValidationContract(preserve_provider_policy=False)
    with pytest.raises(ValidationError, match="live_validation_requires_concurrency_limits"):
        LiveSecondWaveValidationContract(preserve_concurrency_limits=False)
    with pytest.raises(ValidationError, match="live_validation_requires_cooldown_and_circuits"):
        LiveSecondWaveValidationContract(preserve_cooldown_and_circuits=False)


def test_premium_escalation_is_not_authorized():
    with pytest.raises(ValidationError, match="premium_escalation_not_authorized"):
        LiveSecondWaveValidationContract(allow_premium_escalation=True)
