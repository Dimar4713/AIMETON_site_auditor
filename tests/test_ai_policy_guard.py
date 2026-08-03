import pytest

from app.ai_policy_guard import AiNextAction, PolicyContext, evaluate_ai_next_action


def base_policy(**overrides):
    values = dict(
        allowed_action_types={"crawl_url", "stop"},
        remaining_budget=1.0,
        deadline_remaining_ms=5000,
        rate_limit_available=True,
        robots_allowed=True,
        domain_allowed=True,
        ssrf_safe=True,
        authorized=True,
    )
    values.update(overrides)
    return PolicyContext(**values)


def test_ai_action_is_not_executable_without_policy_allowance():
    decision = evaluate_ai_next_action(
        AiNextAction(action_type="query_provider", estimated_cost=0.1, estimated_latency_ms=100),
        base_policy(),
    )
    assert decision.status == "blocked"
    assert decision.reason_code == "action_type_forbidden"
    assert decision.executable is False


@pytest.mark.parametrize(
    ("policy", "action", "reason"),
    [
        (base_policy(remaining_budget=0.05), AiNextAction(action_type="crawl_url", estimated_cost=0.1, estimated_latency_ms=100), "budget_exceeded"),
        (base_policy(deadline_remaining_ms=50), AiNextAction(action_type="crawl_url", estimated_cost=0, estimated_latency_ms=100), "deadline_exceeded"),
        (base_policy(rate_limit_available=False), AiNextAction(action_type="crawl_url", estimated_cost=0, estimated_latency_ms=100), "rate_limit_exhausted"),
        (base_policy(robots_allowed=False), AiNextAction(action_type="crawl_url", estimated_cost=0, estimated_latency_ms=100), "robots_forbidden"),
        (base_policy(domain_allowed=False), AiNextAction(action_type="crawl_url", estimated_cost=0, estimated_latency_ms=100), "domain_forbidden"),
        (base_policy(ssrf_safe=False), AiNextAction(action_type="crawl_url", estimated_cost=0, estimated_latency_ms=100), "ssrf_blocked"),
        (base_policy(authorized=False), AiNextAction(action_type="crawl_url", estimated_cost=0, estimated_latency_ms=100), "authorization_denied"),
    ],
)
def test_policy_guard_blocks_each_deterministic_boundary(policy, action, reason):
    decision = evaluate_ai_next_action(action, policy)
    assert decision.reason_code == reason
    assert decision.executable is False


def test_same_action_and_policy_produce_same_decision():
    action = AiNextAction(action_type="crawl_url", estimated_cost=0.1, estimated_latency_ms=100)
    policy = base_policy()
    first = evaluate_ai_next_action(action, policy)
    second = evaluate_ai_next_action(action, policy)
    assert first == second
    assert first.status == "allowed"
    assert first.executable is True
