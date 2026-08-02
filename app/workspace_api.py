from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.auth import User
from app.auth_api import current_user


router = APIRouter(tags=["user-workspace"])


def _no_cache_file(path: str) -> FileResponse:
    return FileResponse(
        Path(path),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/login", include_in_schema=False)
def login_page():
    return _no_cache_file("static/login.html")


@router.get("/workspace", include_in_schema=False)
def user_workspace(_user: User = Depends(current_user)):
    return _no_cache_file("static/workspace.html")


@router.get("/workspace/missions/{mission_id}", include_in_schema=False)
def user_mission_detail(mission_id: str, _user: User = Depends(current_user)):
    # The HTML shell never resolves ownership itself. The browser must fetch the
    # owner-scoped API endpoint, which returns the same 404 for absent/foreign IDs.
    return _no_cache_file("static/mission-detail.html")
