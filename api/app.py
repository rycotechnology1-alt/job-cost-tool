"""FastAPI application factory for the phase-1 immutable-run workflow API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI

from api.dependencies import ApiRuntime, build_runtime
from api.routes.exports import router as exports_router
from api.routes.review_sessions import router as review_sessions_router
from api.routes.runs import router as runs_router
from api.routes.trusted_profiles import router as trusted_profiles_router
from api.routes.uploads import router as uploads_router
from api.settings import ApiSettings
from core.config import ProfileManager
from infrastructure.persistence import SqliteLineageStore


def create_app(
    *,
    settings: ApiSettings | None = None,
    lineage_store: SqliteLineageStore | None = None,
    database_path: str | Path | None = None,
    profile_manager: ProfileManager | None = None,
    upload_root: str | Path | None = None,
    export_root: str | Path | None = None,
    engine_version: str | None = None,
    now_provider: Callable | None = None,
) -> FastAPI:
    """Create the minimal FastAPI backend for the accepted phase-1 API slice."""
    resolved_settings = (settings or ApiSettings.from_env()).with_overrides(
        database_path=database_path,
        upload_root=upload_root,
        export_root=export_root,
        engine_version=engine_version,
    )
    runtime, owns_lineage_store = build_runtime(
        lineage_store=lineage_store,
        database_path=resolved_settings.database_path,
        profile_manager=profile_manager,
        upload_root=resolved_settings.upload_root,
        export_root=resolved_settings.export_root,
        engine_version=resolved_settings.engine_version,
        now_provider=now_provider,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime
        try:
            yield
        finally:
            if owns_lineage_store:
                runtime.lineage_store.close()

    app = FastAPI(
        title="Job Cost Tool API",
        version="phase1-step6",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.include_router(trusted_profiles_router)
    app.include_router(uploads_router)
    app.include_router(runs_router)
    app.include_router(review_sessions_router)
    app.include_router(exports_router)
    return app
