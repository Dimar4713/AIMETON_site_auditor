from pathlib import Path


def test_configure_dadata_stage_has_bounded_public_readiness_retry():
    script = Path("scripts/configure_dadata_stage.sh").read_text(encoding="utf-8")
    assert "DADATA_PUBLIC_READY_ATTEMPTS" in script
    assert "DaData public health not ready" in script
    assert "DaData live lookup not ready" in script
    assert "retry_delay" in script


def test_configure_dadata_stage_uses_current_secret_safe_health_contract():
    script = Path("scripts/configure_dadata_stage.sh").read_text(encoding="utf-8")
    assert 'payload.get("state") == "active"' in script
    assert 'payload.get("api_token_configured") is True' in script
    assert 'payload.get("secret_configured") is True' in script
    assert 'payload.get("secrets_exposed") is False' in script
    assert 'record.get("response_digest")' in script


def test_configure_workflow_does_not_patch_smoke_at_runtime():
    workflow = Path(".github/workflows/configure-dadata-stage.yml").read_text(encoding="utf-8")
    assert "Align stage smoke with runtime contracts" not in workflow
    assert "Validate committed stage smoke" in workflow
