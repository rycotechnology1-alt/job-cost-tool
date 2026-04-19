"""Default ASGI entrypoint for the phase-1 FastAPI application."""

from __future__ import annotations

import os

from api.app import create_app


if not os.environ.get("JOB_COST_API_POSTGRES_POOLED_URL"):
    os.environ["JOB_COST_API_DATABASE_PROVIDER"] = "sqlite"
    os.environ["JOB_COST_API_STORAGE_PROVIDER"] = "local"

app = create_app()
