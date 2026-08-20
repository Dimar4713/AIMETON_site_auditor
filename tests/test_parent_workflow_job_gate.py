from scripts.require_successful_parent_job import parent_job_succeeded


def test_parent_job_gate_requires_named_completed_success():
    jobs = [
        {"name": "deployment-gate", "status": "completed", "conclusion": "success"},
        {"name": "deploy", "status": "completed", "conclusion": "success"},
    ]
    assert parent_job_succeeded(jobs, "deploy") is True
    assert parent_job_succeeded(jobs, "reconcile") is False


def test_parent_job_gate_rejects_skipped_failed_or_incomplete_job():
    for item in (
        {"name": "deploy", "status": "completed", "conclusion": "skipped"},
        {"name": "deploy", "status": "completed", "conclusion": "failure"},
        {"name": "deploy", "status": "in_progress", "conclusion": None},
    ):
        assert parent_job_succeeded([item], "deploy") is False
