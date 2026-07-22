from __future__ import annotations

from app.runtime_core.models import TaskState
from app.runtime_core.storage import RuntimeStore
from app.site_auditor_runtime_adapter import SiteAuditorRuntimeAdapter


def test_runtime_state_survives_store_restart(tmp_path):
    db_path = tmp_path / "runtime.sqlite3"
    first_store = RuntimeStore(db_path)
    adapter = SiteAuditorRuntimeAdapter(first_store)

    task = adapter.start_task(
        title="Audit example company",
        commitment="Produce a source-traceable company profile",
        completion_criteria=["Evidence attached", "Execution recorded"],
        correlation_id="corr-persistence",
        external_refs={"github_issue": "40"},
    )
    assert task.state == TaskState.IN_PROGRESS

    second_store = RuntimeStore(db_path)
    restored = second_store.get_task(task.id)
    assert restored is not None
    assert restored.id == task.id
    assert restored.state == TaskState.IN_PROGRESS
    assert restored.external_refs == {"github_issue": "40"}


def test_site_auditor_end_to_end_trace(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    adapter = SiteAuditorRuntimeAdapter(store)
    correlation_id = "corr-e2e"

    task = adapter.start_task(
        title="Analyze example.org",
        commitment="Return a bounded economic-intelligence result",
        completion_criteria=["Sanitized evidence exists", "Task completed"],
        correlation_id=correlation_id,
    )
    result = adapter.record_result(
        task_id=task.id,
        operation="analyze_site",
        source_ref="https://example.org",
        summary="Sanitized result summary",
        result_status="success",
        correlation_id=correlation_id,
        digest="sha256:test",
    )
    completed = adapter.complete_task(
        task_id=task.id,
        reason="Completion criteria satisfied",
        correlation_id=correlation_id,
    )

    assert completed.state == TaskState.COMPLETED
    assert result["tool_execution"].evidence_ids == [result["evidence"].id]

    records = store.records(task.id)
    kinds = [item["kind"] for item in records]
    assert kinds.count("event") == 3
    assert "evidence" in kinds
    assert "tool_execution" in kinds
    assert all(item["record"]["actor_ref"] for item in records)
    assert all(item["record"]["mandate_ref"] for item in records)
    assert all(item["record"]["correlation_id"] == correlation_id for item in records)


def test_runtime_audit_does_not_require_sensitive_payload(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    adapter = SiteAuditorRuntimeAdapter(store)
    task = adapter.start_task(
        title="Safe audit",
        commitment="Record only sanitized metadata",
        completion_criteria=["No secret persisted"],
        correlation_id="corr-safe",
    )
    adapter.record_result(
        task_id=task.id,
        operation="company_intelligence",
        source_ref="source:public",
        summary="No API key, token, raw prompt or environment value",
        result_status="partial",
        correlation_id="corr-safe",
    )

    serialized = str(store.records(task.id)).lower()
    assert "authorization: bearer" not in serialized
    assert "routerai_api_key" not in serialized
    assert "aimeton_mcp_admin_token" not in serialized
