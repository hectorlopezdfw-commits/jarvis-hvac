from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.services.firstring import FIRSTRING_CORS_ORIGINS

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-powered lead conversion engine for HVAC businesses",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(FIRSTRING_CORS_ORIGINS),
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    max_age=600,
)

app.include_router(router)

static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health_check() -> dict:
    payload = {"status": "ok", "app": settings.app_name, "environment": settings.app_env}
    commit = os.getenv("RENDER_GIT_COMMIT", "").strip()
    if commit:
        payload["commit"] = commit
    return payload


@app.get("/")
def serve_demo() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/sales")
def serve_sales_page() -> FileResponse:
    return FileResponse(static_dir / "landing.html")
