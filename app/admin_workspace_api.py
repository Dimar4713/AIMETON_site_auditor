from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.auth import User
from app.auth_api import require_admin


router = APIRouter(tags=["admin-workspace"])


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
