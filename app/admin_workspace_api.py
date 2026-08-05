from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import User
from app.auth_api import require_admin
from app.retention_runner import RetentionPeriodicRunner


router = APIRouter(tags=["admin-workspace"])


class RetentionCleanupProjection(BaseModel):
    run_id: str
    started_at: str
    finished_at: str
    batches: int
    deleted: int
    protected: int
    stopped_reason: str


class RetentionStatusProjection(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: float
    latest_cleanup: RetentionCleanupProjection | None = None


@router.get("/admin/workspace", include_in_schema=False)
def admin_workspace(_admin: User = Depends(require_admin)) -> FileResponse:
    return FileResponse(
        Path("static/admin-workspace.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get(
    "/api/admin/retention/status",
    response_model=RetentionStatusProjection,
)
def admin_retention_status(
    request: Request,
    _admin: User = Depends(require_admin),
) -> RetentionStatusProjection:
    runner: Any = getattr(request.app.state, "retention_runner", None)
    if not isinstance(runner, RetentionPeriodicRunner):
        raise HTTPException(
            status_code=503,
            detail={"reason": "retention_runner_unavailable"},
        )
    latest = runner.latest_cleanup()
    return RetentionStatusProjection(
        enabled=runner.enabled,
        running=runner.running,
        interval_seconds=runner.interval_seconds,
        latest_cleanup=(
            RetentionCleanupProjection.model_validate(latest)
            if latest is not None
            else None
        ),
    )
