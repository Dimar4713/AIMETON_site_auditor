from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_stage_chain_uses_direct_workflow_dispatch_handoffs() -> None:
    deploy = _text("deploy-stage.yml")
    dadata = _text("configure-dadata-stage.yml")
    persistence = _text("runtime-persistence-reconcile.yml")
    auth = _text("stage-auth-persistence-guard.yml")

    assert "actions: write" in deploy
    assert "configure-dadata-stage.yml/dispatches" in deploy
    assert "actions: write" in dadata
    assert "runtime-persistence-reconcile.yml/dispatches" in dadata
    assert "actions: write" in persistence
    assert "stage-auth-persistence-guard.yml/dispatches" in persistence
    assert "actions: write" in auth
    assert "stage-convergence.yml/dispatches" in auth


def test_direct_chain_stays_marketplace_free() -> None:
    for name in (
        "deploy-stage.yml",
        "configure-dadata-stage.yml",
        "runtime-persistence-reconcile.yml",
        "stage-auth-persistence-guard.yml",
    ):
        text = _text(name)
        assert "ubuntu-latest" not in text
        assert "actions/github-script" not in text
        assert "actions/checkout" not in text
