from __future__ import annotations

from fastapi import FastAPI

from app.runtime_core.api import router

app = FastAPI(
    title="AIMETON Runtime Core",
    version="0.1.0",
    description="Portable task, evidence and execution state for AIMETON tools.",
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "component": "aimeton-runtime-core",
        "version": app.version,
        "runtime_api": "/api/runtime",
    }
