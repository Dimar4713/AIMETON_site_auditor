from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "stage-convergence.yml"
WRITER = ROOT / "scripts" / "write_stage_convergence_marker.py"
MCP_SERVER = ROOT / "app" / "mcp_server.py"


def test_convergence_workflow_reprobes_on_each_required_gate_completion() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger_prefix = text.split("permissions:", 1)[0]
    assert "workflow_run:" in trigger_prefix
    for workflow_name in (
        "Deploy Stage",
        "Configure DaData Stage",
        "Runtime Persistence Reconcile",
        "Stage Auth Persistence Guard",
    ):
        assert f"- {workflow_name}" in trigger_prefix
    assert "resolve_stage_convergence_gates.py" in text
    assert "timeout-minutes: 3" in text
    assert "--timeout-seconds" not in text
    assert "--poll-seconds" not in text
    assert "if: needs.resolve-gates.outputs.ready == 'true'" in text


def test_convergence_publication_verifies_live_runtime_invariants() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'test "$(cat app-source-sha.txt)" = "$EXPECTED_SHA"' in text
    assert "/api/health" in text
    assert "/api/runtime/convergence" in text
    assert "/api/missions/registry-mirror/dadata/health" in text
    assert "PRAGMA integrity_check" in text
    assert "active_admins" not in text  # no user/admin counts are emitted
    assert "role='admin' AND is_active=1" in text
    assert "runtime_instance_id" in text


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
