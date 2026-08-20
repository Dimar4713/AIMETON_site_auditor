from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "baseline-ci.yml"


def test_baseline_job_env_does_not_use_runner_context() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    jobs = text.split("jobs:", 1)[1]
    env_block = jobs.split("steps:", 1)[0]
    assert "runner.temp" not in env_block
    assert "VENV_DIR: /tmp/aimeton-baseline-${{ github.run_id }}" in env_block
