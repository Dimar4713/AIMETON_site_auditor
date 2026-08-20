from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "stage-convergence.yml"
DADATA = ROOT / ".github" / "workflows" / "configure-dadata-stage.yml"
PERSISTENCE = ROOT / ".github" / "workflows" / "runtime-persistence-reconcile.yml"
AUTH_GUARD = ROOT / ".github" / "workflows" / "stage-auth-persistence-guard.yml"
WRITER = ROOT / "scripts" / "write_stage_convergence_marker.py"
MCP_SERVER = ROOT / "app" / "mcp_server.py"


def test_convergence_chain_is_serialized_on_self_hosted_stage_runner() -> None:
    convergence = WORKFLOW.read_text(encoding="utf-8")
    dadata = DADATA.read_text(encoding="utf-8")
    persistence = PERSISTENCE.read_text(encoding="utf-8")
    auth = AUTH_GUARD.read_text(encoding="utf-8")

    assert "- Deploy Stage" in dadata.split("permissions:", 1)[0]
    assert "- Configure DaData Stage" in persistence.split("permissions:", 1)[0]
    assert "- Runtime Persistence Reconcile" in auth.split("permissions:", 1)[0]
    assert "- Stage Auth Persistence Guard" in convergence.split("permissions:", 1)[0]

    for text in (convergence, dadata, persistence, auth):
        assert "self-hosted" in text
        assert "stage" in text
        assert "auditor" in text
        assert "ubuntu-latest" not in text
        assert "actions/github-script" not in text

    assert "Timed out waiting for required Stage convergence gates" not in convergence
    assert "missing_successful_gate" in convergence
    assert "actions/runs?" in convergence


def test_convergence_publication_verifies_live_runtime_invariants() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "app-source-sha.txt" in text
    assert "/api/health" in text
    assert "/api/runtime/convergence" in text
    assert "/api/missions/registry-mirror/dadata/health" in text
    assert "PRAGMA integrity_check" in text
    assert "role='admin' AND is_active=1" in text
    assert "runtime_instance_id" in text
    assert "marketplace_actions=disabled" in text
    assert "hosted_runner=disabled" in text


def test_marker_writer_is_syntax_valid_and_atomic() -> None:
    subprocess.run(["python3", "-m", "py_compile", str(WRITER)], check=True)
    text = WRITER.read_text(encoding="utf-8")
    assert "os.replace(tmp, path)" in text
    assert "os.fsync" in text
    assert '"secret_values_exposed": False' in text
    assert "/opt/aimeton/auditor-stack/data/runtime-core/stage-convergence.json" in text


def test_deepseek_visible_mcp_convergence_tool_is_registered() -> None:
    text = MCP_SERVER.read_text(encoding="utf-8")
    assert '@mcp.tool(name="runtime.convergence")' in text
    assert '"runtime.convergence"' in text
    assert "Check runtime.convergence before a long mission" in text
