from __future__ import annotations

from typing import Any

from app.runtime_core.models import (
    EvidenceCreate,
    TaskCreate,
    TaskTransition,
    TaskState,
    ToolExecutionCreate,
)
from app.runtime_core.storage import RuntimeStore


SITE_AUDITOR_ACTOR = "aimeton.actor.site-auditor"
SITE_AUDITOR_MANDATE = "aimeton.mandate.economic-intelligence.read-only"
SITE_AUDITOR_TOOL = "aimeton.tool.site-auditor"


class SiteAuditorRuntimeAdapter:
    """Thin adapter that records Site Auditor work without moving its logic into Runtime Core."""

    def __init__(self, store: RuntimeStore):
        self.store = store

    def start_task(
        self,
        *,
        title: str,
        commitment: str,
        completion_criteria: list[str],
        correlation_id: str,
        external_refs: dict[str, str] | None = None,
    ):
        task = self.store.create_task(
            TaskCreate(
                title=title,
                actor_ref=SITE_AUDITOR_ACTOR,
                mandate_ref=SITE_AUDITOR_MANDATE,
                commitment=commitment,
                completion_criteria=completion_criteria,
                correlation_id=correlation_id,
                external_refs=external_refs or {},
            )
        )
        return self.store.transition_task(
            task.id,
            TaskTransition(
                actor_ref=SITE_AUDITOR_ACTOR,
                mandate_ref=SITE_AUDITOR_MANDATE,
                target_state=TaskState.IN_PROGRESS,
                reason="Site Auditor accepted the runtime task",
                correlation_id=correlation_id,
            ),
        )

    def record_result(
        self,
        *,
        task_id: str,
        operation: str,
        source_ref: str,
        summary: str,
        result_status: str,
        correlation_id: str,
        digest: str | None = None,
    ) -> dict[str, Any]:
        evidence = self.store.append_evidence(
            task_id,
            EvidenceCreate(
                actor_ref=SITE_AUDITOR_ACTOR,
                mandate_ref=SITE_AUDITOR_MANDATE,
                evidence_type="site-auditor-result",
                source_ref=source_ref,
                reason="Attach sanitized Site Auditor result to runtime task",
                summary=summary,
                digest=digest,
                correlation_id=correlation_id,
            ),
        )
        execution = self.store.append_tool_execution(
            task_id,
            ToolExecutionCreate(
                actor_ref=SITE_AUDITOR_ACTOR,
                mandate_ref=SITE_AUDITOR_MANDATE,
                tool_ref=SITE_AUDITOR_TOOL,
                operation=operation,
                reason="Record Site Auditor execution",
                result_status=result_status,
                evidence_ids=[evidence.id],
                correlation_id=correlation_id,
            ),
        )
        return {"evidence": evidence, "tool_execution": execution}

    def complete_task(self, *, task_id: str, reason: str, correlation_id: str):
        return self.store.transition_task(
            task_id,
            TaskTransition(
                actor_ref=SITE_AUDITOR_ACTOR,
                mandate_ref=SITE_AUDITOR_MANDATE,
                target_state=TaskState.COMPLETED,
                reason=reason,
                correlation_id=correlation_id,
            ),
        )
