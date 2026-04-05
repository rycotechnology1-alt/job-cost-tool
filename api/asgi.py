"""Default ASGI entrypoint for the phase-1 FastAPI application."""

from __future__ import annotations

from api.app import create_app


app = create_app()
