from pathlib import Path


def test_stage_deploy_uses_only_self_hosted_stage_runner() -> None:
    text = Path(".github/workflows/deploy-stage.yml").read_text(encoding="utf-8")

    assert "ubuntu-latest" not in text
    assert "deployment-gate:" not in text
    assert "needs: deployment-gate" not in text
    assert "- self-hosted" in text
    assert "- stage" in text
    assert "- auditor" in text
    assert "github.event_name == 'workflow_dispatch'" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.head_branch == 'main'" in text
