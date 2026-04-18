"""FastAPI application factory for the phase-1 immutable-run workflow API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI

from api.dependencies import ApiRuntime, build_runtime
from api.request_context import build_request_context_provider
from api.routes.exports import router as exports_router
from api.routes.profiles import (
    profile_drafts_router,
    profile_sync_exports_router,
    profile_versions_router,
    profiles_router,
)
from api.routes.review_sessions import router as review_sessions_router
from api.routes.runs import router as runs_router
from api.routes.trusted_profiles import router as trusted_profiles_router
from api.routes.uploads import router as uploads_router
from api.settings import ApiSettings
from core.config import ProfileManager
from infrastructure.persistence import LineageStore
from infrastructure.storage import RuntimeStorage


def create_app(
    *,
    settings: ApiSettings | None = None,
    lineage_store: LineageStore | None = None,
    database_provider: str | None = None,
    database_path: str | Path | None = None,
    postgres_admin_url: str | None = None,
    postgres_pooled_url: str | None = None,
    postgres_schema: str | None = None,
    auth_mode: str | None = None,
    auth_secret: str | None = None,
    storage_provider: str | None = None,
    blob_read_write_token: str | None = None,
    profile_manager: ProfileManager | None = None,
    file_store: RuntimeStorage | None = None,
    upload_root: str | Path | None = None,
    export_root: str | Path | None = None,
    upload_retention_hours: int | None = None,
    engine_version: str | None = None,
    now_provider: Callable | None = None,
) -> FastAPI:
    """Create the minimal FastAPI backend for the accepted phase-1 API slice."""
    resolved_settings = (settings or ApiSettings.from_env()).with_overrides(
        database_provider=database_provider,
        database_path=database_path,
        postgres_admin_url=postgres_admin_url,
        postgres_pooled_url=postgres_pooled_url,
        postgres_schema=postgres_schema,
        auth_mode=auth_mode,
        auth_secret=auth_secret,
        storage_provider=storage_provider,
        blob_read_write_token=blob_read_write_token,
        upload_root=upload_root,
        export_root=export_root,
        upload_retention_hours=upload_retention_hours,
        engine_version=engine_version,
    )
    runtime, owns_lineage_store = build_runtime(
        lineage_store=lineage_store,
        database_provider=resolved_settings.database_provider,
        database_path=resolved_settings.database_path,
        postgres_admin_url=resolved_settings.postgres_admin_url,
        postgres_pooled_url=resolved_settings.postgres_pooled_url,
        postgres_schema=resolved_settings.postgres_schema,
        profile_manager=profile_manager,
        file_store=file_store,
        storage_provider=resolved_settings.storage_provider,
        blob_read_write_token=resolved_settings.blob_read_write_token,
        upload_root=resolved_settings.upload_root,
        export_root=resolved_settings.export_root,
        upload_retention_hours=resolved_settings.upload_retention_hours,
        engine_version=resolved_settings.engine_version,
        now_provider=now_provider,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime
        app.state.request_context_provider = build_request_context_provider(
            resolved_settings,
            hosted_request_context_service=runtime.hosted_request_context_service,
        )
        try:
            yield
        finally:
            if owns_lineage_store:
                runtime.lineage_store.close()

    app = FastAPI(
        title="Job Cost Tool API",
        version="phase1-step7",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.state.request_context_provider = build_request_context_provider(
        resolved_settings,
        hosted_request_context_service=runtime.hosted_request_context_service,
    )
    app.include_router(trusted_profiles_router)
    app.include_router(profiles_router)
    app.include_router(profile_versions_router)
    app.include_router(profile_drafts_router)
    app.include_router(profile_sync_exports_router)
    app.include_router(uploads_router)
    app.include_router(runs_router)
    app.include_router(review_sessions_router)
    app.include_router(exports_router)
    return app
