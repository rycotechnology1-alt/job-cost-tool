"""Dependency helpers and runtime container for the phase-1 FastAPI slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import Request

from core.config import ProfileManager
from infrastructure.persistence import SqliteLineageStore
from infrastructure.storage import LocalRuntimeFileStore, RuntimeStorage
from services.processing_run_service import ProcessingRunService
from services.review_session_service import ReviewSessionService
from services.trusted_profile_service import TrustedProfileService


@dataclass(slots=True)
class ApiRuntime:
    """Service container for the minimal phase-1 FastAPI app."""

    lineage_store: SqliteLineageStore
    file_store: RuntimeStorage
    processing_run_service: ProcessingRunService
    review_session_service: ReviewSessionService
    trusted_profile_service: TrustedProfileService


def build_runtime(
    *,
    lineage_store: SqliteLineageStore | None = None,
    database_path: str | Path = ":memory:",
    profile_manager: ProfileManager | None = None,
    upload_root: str | Path = "runtime/api/uploads",
    export_root: str | Path = "runtime/api/exports",
    engine_version: str = "dev-local",
    now_provider: Callable | None = None,
) -> tuple[ApiRuntime, bool]:
    """Build the API runtime and return whether the app owns the lineage store."""
    owns_lineage_store = lineage_store is None
    if lineage_store is None and str(database_path) != ":memory:":
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    persisted_store = lineage_store or SqliteLineageStore(database_path)
    persisted_profile_manager = profile_manager or ProfileManager()
    file_store = LocalRuntimeFileStore(
        upload_root=upload_root,
        export_root=export_root,
    )
    runtime = ApiRuntime(
        lineage_store=persisted_store,
        file_store=file_store,
        processing_run_service=ProcessingRunService(
            lineage_store=persisted_store,
            profile_manager=persisted_profile_manager,
            engine_version=engine_version,
            now_provider=now_provider,
        ),
        review_session_service=ReviewSessionService(
            lineage_store=persisted_store,
            artifact_store=file_store,
            now_provider=now_provider,
        ),
        trusted_profile_service=TrustedProfileService(
            profile_manager=persisted_profile_manager,
        ),
    )
    return runtime, owns_lineage_store


def get_runtime(request: Request) -> ApiRuntime:
    """Return the service container stored on the FastAPI application."""
    return request.app.state.runtime
