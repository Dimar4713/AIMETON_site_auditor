from pathlib import Path


WORKFLOW = Path(".github/workflows/accept-hunter-runtime-stage.yml")
ROUTER = Path(".github/workflows/aimeton-command-router.yml")


def test_hunter_runtime_acceptance_is_dispatch_only_and_no_cost() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_block = text.split("permissions:", 1)[0]

    assert "workflow_dispatch:" in trigger_block
    assert "issue_comment:" not in trigger_block
    assert "inputs.expected_sha" in text
    assert "expected_tariff" in text
    assert "expected_strategy" in text
    assert "expected_provider_order" in text
    assert "get_search_strategy_settings_repository" in text
    assert "_execution_policy_observation" in text
    assert "actual_gateway_policy" in text
    assert "projected_admin_gateway_policy" in text
    assert "selected_gateway_policy" in text
    assert "selected_policy_fingerprint" in text
    assert "gateway_effective_policy" in text
    assert "gateway_effective_policy_fingerprint" in text
    assert "legacy_hunter_admin_projection_applied" in text
    assert "gateway_policy_changed_after_authority_resolution" in text
    assert "admin_candidate_gateway_policy" in text
    assert "admin_candidate_policy_fingerprint" in text
    assert "admin_candidate_matches_projection" in text
    assert "provider_lifecycle" in text
    assert "runtime_authority" in text
    assert "policy_equivalent" in text
    assert "runtime_callsite_uses_admin_projection" in text
    assert "routing_changed_by_observation" in text
    assert "apply_hunt_request(" in text
    assert "httpx" not in text
    assert "/api/hunt" not in text
    assert "provider calls: `0`" in text


def test_hunter_runtime_acceptance_exposes_hidden_post_resolver_projection() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "observation['runtime_authority'] == 'env'" in text
    assert "selected == actual" in text
    assert "observation['selected_policy_fingerprint'] == actual['fingerprint']" in text
    assert "observation['legacy_hunter_admin_projection_applied'] is True" in text
    assert "observation['gateway_policy_changed_after_authority_resolution'] is True" in text
    assert "gateway_effective == projected" in text
    assert "observation['gateway_effective_policy_fingerprint'] == projected['fingerprint']" in text
    assert "observation['gateway_effective_policy_fingerprint'] != observation['selected_policy_fingerprint']" in text
    assert "legacy TracedSearchGateway admin projection applied after resolver" in text
    assert "gateway-effective policy equals persisted admin projection" in text


def test_hunter_runtime_acceptance_proves_admin_candidate_without_activation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "observation['admin_candidate_available'] is True" in text
    assert "observation['admin_candidate_matches_projection'] is True" in text
    assert "admin_candidate == projected" in text
    assert "observation['admin_candidate_policy_fingerprint'] == projected['fingerprint']" in text


def test_hunter_runtime_acceptance_proves_tavily_registration_without_activation_assumption() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "set(by_provider) == {'searxng', 'yandex', 'tavily'}" in text
    assert "all(item['registered'] is True for item in lifecycle)" in text
    assert "all(item['availability'] == 'unknown' for item in lifecycle)" in text
    assert "by_provider['tavily']['admin_enabled'] is False" in text
    assert "by_provider['tavily']['enabled'] is False" in text
    assert "expected_admin_position" in text
    assert "profile.provider_order.index('tavily') + 1" in text
    assert "by_provider['tavily']['admin_position'] == expected_admin_position" in text
    assert "gateway_effective['provider_order'].index('tavily') + 1" in text
    assert "by_provider['tavily']['active'] is True" not in text
    assert "by_provider['tavily']['configured'] is True" not in text
    assert "all canonical providers remain registered" in text
    assert "network availability not guessed without evidence" in text


def test_hunter_runtime_acceptance_does_not_reimplement_policy_resolvers() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "resolve_hunter_search_policy" not in text
    assert "resolve_traced_gateway_policy" not in text
    assert "search_policy_from_env" not in text
    assert "authority_resolution =" not in text
    assert "observation = _execution_policy_observation(record)" in text


def test_hunter_runtime_command_is_authorized_only_on_p1_501() -> None:
    text = ROUTER.read_text(encoding="utf-8")

    assert "accept-hunter-runtime-stage" in text
    assert "workflow_id: 'accept-hunter-runtime-stage.yml'" in text
    route = text.split("'accept-hunter-runtime-stage': {", 1)[1].split("'accept-logging-pressure-stage': {", 1)[0]
    assert "issue_number: 501" in route
    assert "inputs: {expected_sha: sha}" in route
