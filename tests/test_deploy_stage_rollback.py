from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_stage.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_deploy_failure_restores_previous_bundle(tmp_path: Path) -> None:
    """Prove rollback without modifying the real stage stack.

    The test creates an isolated stack, mocks Docker as healthy and forces the
    first external smoke request to fail after the atomic source switch.
    """
    stack_dir = tmp_path / "stack"
    source_dir = tmp_path / "source"
    fake_bin = tmp_path / "bin"
    stack_dir.mkdir()
    source_dir.mkdir()
    fake_bin.mkdir()

    (stack_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    current_dir = stack_dir / "app-source"
    current_dir.mkdir()
    (current_dir / "marker.txt").write_text("previous-bundle\n", encoding="utf-8")
    previous_sha = "1" * 40
    (stack_dir / "app-source-sha.txt").write_text(previous_sha + "\n", encoding="utf-8")

    (source_dir / "app").mkdir()
    (source_dir / "app" / "main.py").write_text(
        'from fastapi.responses import RedirectResponse\n'
        'def redirect():\n'
        '    return RedirectResponse(url="/mcp/", status_code=307)  # Location /mcp/\n',
        encoding="utf-8",
    )
    (source_dir / "app" / "mcp_server.py").write_text(
        'ALLOWED_HOSTS = ["stage-auditor.aimeton.ru"]\n', encoding="utf-8"
    )
    (source_dir / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -e
case "$1" in
  inspect)
    printf 'healthy\\n'
    ;;
  compose)
    exit 0
    ;;
  logs)
    exit 0
    ;;
  ps)
    printf 'container=aimeton-auditor image=test status=Up (healthy)\\n'
    ;;
  *)
    exit 0
    ;;
esac
""",
    )

    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
# Force the external smoke check to fail after the bundle switch.
exit 22
""",
    )

    deploy_sha = "2" * 40
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "STACK_DIR": str(stack_dir),
            "SOURCE_DIR": str(source_dir),
            "DEPLOY_SHA": deploy_sha,
            "STAGE_URL": "https://stage.invalid",
            "HEALTH_TIMEOUT": "5",
            "LOCK_FILE": str(tmp_path / "deploy.lock"),
        }
    )

    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT)],
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ROLLBACK:" in result.stdout
    assert "Rollback restored SHA" in result.stdout
    assert (stack_dir / "app-source-sha.txt").read_text(encoding="utf-8").strip() == previous_sha
    assert (stack_dir / "app-source" / "marker.txt").read_text(encoding="utf-8").strip() == "previous-bundle"

    failed_dirs = list((stack_dir / ".deployments").glob("app-source.failed.*"))
    assert len(failed_dirs) == 1
    assert (failed_dirs[0] / "app" / "main.py").exists()
