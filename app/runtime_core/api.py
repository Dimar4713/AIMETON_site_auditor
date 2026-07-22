from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.runtime_core.models import (
    Event,
    EventCreate,
    Evidence,
    EvidenceCreate,
    PlanStep,
    PlanStepCreate,
    Task,
    TaskCreate,
    TaskTransition,
    ToolExecution,
    ToolExecutionCreate,
)
from app.runtime_core.storage import RuntimeStore

router = APIRouter(prefix="/api/runtime", tags=["runtime-core"])
store = RuntimeStore()


@router.get("/health")
def runtime_health() -> dict[str, object]:
    return {"status": "ok", "component": "aimeton-runtime-core", "schema_version": 1}


@router.post("/tasks", response_model=Task, status_code=201)
def create_task(request: TaskCreate) -> Task:
    return store.create_task(request)


@router.get("/tasks", response_model=list[Task])
def list_tasks(limit: int = Query(default=100, ge=1, le=1000)) -> list[Task]:
    return store.list_tasks(limit)


@router.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str) -> Task:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Runtime task not found")
    return task


@router.post("/tasks/{task_id}/transition", response_model=Task)
def transition_task(task_id: str, request: TaskTransition) -> Task:
    try:
        return store.transition_task(task_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime task not found") from exc


@router.post("/tasks/{task_id}/events", response_model=Event, status_code=201)
def append_event(task_id: str, request: EventCreate) -> Event:
    try:
        return store.append_event(task_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime task not found") from exc


@router.post("/tasks/{task_id}/evidence", response_model=Evidence, status_code=201)
def append_evidence(task_id: str, request: EvidenceCreate) -> Evidence:
    try:
        return store.append_evidence(task_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime task not found") from exc


@router.post("/tasks/{task_id}/tool-executions", response_model=ToolExecution, status_code=201)
def append_tool_execution(task_id: str, request: ToolExecutionCreate) -> ToolExecution:
    try:
        return store.append_tool_execution(task_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime task not found") from exc


@router.post("/tasks/{task_id}/plan-steps", response_model=PlanStep, status_code=201)
def append_plan_step(task_id: str, request: PlanStepCreate) -> PlanStep:
    try:
        return store.append_plan_step(task_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime task not found") from exc


@router.get("/tasks/{task_id}/records")
def task_records(task_id: str) -> list[dict[str, object]]:
    try:
        return store.records(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime task not found") from exc
