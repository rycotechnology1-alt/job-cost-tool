"""Dependency helpers and runtime container for the phase-1 FastAPI slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import Request

from core.config import ProfileManager
from infrastructure.persistence import LineageStore, PostgresLineageStore, SqliteLineageStore
from infrastructure.storage import LocalRuntimeFileStore, RuntimeStorage, VercelBlobRuntimeStorage
from services.hosted_request_context_service import HostedRequestContextService
from services.profile_execution_compatibility_adapter import ProfileExecutionCompatibilityAdapter
from services.profile_authoring_service import ProfileAuthoringService
from services.processing_run_service import ProcessingRunService
from services.review_session_service import ReviewSessionService
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository
from services.trusted_profile_provisioning_service import TrustedProfileProvisioningService
from services.trusted_profile_service import TrustedProfileService


@dataclass(slots=True)
class ApiRuntime:
    """Service container for the minimal phase-1 FastAPI app."""

    lineage_store: LineageStore
    file_store: RuntimeStorage
    processing_run_service: ProcessingRunService
    review_session_service: ReviewSessionService
    trusted_profile_service: TrustedProfileService
    profile_authoring_service: ProfileAuthoringService
    hosted_request_context_service: HostedRequestContextService


def build_runtime(
    *,
    lineage_store: LineageStore | None = None,
    database_provider: str = "sqlite",
    database_path: str | Path = ":memory:",
    postgres_admin_url: str | None = None,
    postgres_pooled_url: str | None = None,
    postgres_schema: str = "public",
    profile_manager: ProfileManager | None = None,
    file_store: RuntimeStorage | None = None,
    storage_provider: str = "local",
    blob_read_write_token: str | None = None,
    upload_root: str | Path = "runtime/api/uploads",
    export_root: str | Path = "runtime/api/exports",
    upload_retention_hours: int = 24,
    export_retention_hours: int = 24,
    engine_version: str = "dev-local",
    now_provider: Callable | None = None,
) -> tuple[ApiRuntime, bool]:
    """Build the API runtime and return whether the app owns the lineage store."""
    owns_lineage_store = lineage_store is None
    provider = str(database_provider).strip().lower() or "sqlite"
    if lineage_store is None and provider == "sqlite" and str(database_path) != ":memory:":
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    if lineage_store is not None:
        persisted_store = lineage_store
    elif provider == "postgres":
        if not postgres_pooled_url:
            raise ValueError(
                "JOB_COST_API_POSTGRES_POOLED_URL is required when database_provider=postgres. "
                "Set it in the process environment or repo-root .env for local startup."
            )
        persisted_store = PostgresLineageStore(
            connection_string=postgres_pooled_url,
            migration_connection_string=postgres_admin_url,
            schema_name=postgres_schema,
        )
    else:
        persisted_store = SqliteLineageStore(database_path)
    persisted_profile_manager = profile_manager or ProfileManager()
    trusted_profile_authoring_repository = TrustedProfileAuthoringRepository(
        lineage_store=persisted_store,
        now_provider=now_provider,
    )
    trusted_profile_provisioning_service = TrustedProfileProvisioningService(
        lineage_store=persisted_store,
        repository=trusted_profile_authoring_repository,
        profile_manager=persisted_profile_manager,
        now_provider=now_provider,
    )
    profile_execution_compatibility_adapter = ProfileExecutionCompatibilityAdapter(
        lineage_store=persisted_store,
        profile_manager=persisted_profile_manager,
    )
    configured_file_store = file_store or _build_file_store(
        storage_provider=storage_provider,
        blob_read_write_token=blob_read_write_token,
        upload_root=upload_root,
        export_root=export_root,
        upload_retention_hours=upload_retention_hours,
        export_retention_hours=export_retention_hours,
        now_provider=now_provider,
    )
    profile_authoring_service = ProfileAuthoringService(
        repository=trusted_profile_authoring_repository,
        trusted_profile_provisioning_service=trusted_profile_provisioning_service,
        profile_execution_compatibility_adapter=profile_execution_compatibility_adapter,
        profile_manager=persisted_profile_manager,
        artifact_store=configured_file_store,
        now_provider=now_provider,
    )
    runtime = ApiRuntime(
        lineage_store=persisted_store,
        file_store=configured_file_store,
        processing_run_service=ProcessingRunService(
            lineage_store=persisted_store,
            trusted_profile_provisioning_service=trusted_profile_provisioning_service,
            profile_execution_compatibility_adapter=profile_execution_compatibility_adapter,
            profile_authoring_service=profile_authoring_service,
            engine_version=engine_version,
            now_provider=now_provider,
        ),
        review_session_service=ReviewSessionService(
            lineage_store=persisted_store,
            profile_execution_compatibility_adapter=profile_execution_compatibility_adapter,
            artifact_store=configured_file_store,
            now_provider=now_provider,
        ),
        trusted_profile_service=TrustedProfileService(
            repository=trusted_profile_authoring_repository,
            trusted_profile_provisioning_service=trusted_profile_provisioning_service,
        ),
        profile_authoring_service=profile_authoring_service,
        hosted_request_context_service=HostedRequestContextService(
            lineage_store=persisted_store,
            trusted_profile_provisioning_service=trusted_profile_provisioning_service,
            now_provider=now_provider,
        ),
    )
    return runtime, owns_lineage_store


def _build_file_store(
    *,
    storage_provider: str,
    blob_read_write_token: str | None,
    upload_root: str | Path,
    export_root: str | Path,
    upload_retention_hours: int,
    export_retention_hours: int,
    now_provider: Callable | None,
) -> RuntimeStorage:
    resolved_provider = str(storage_provider).strip().lower() or "local"
    if resolved_provider in {"vercel_blob", "blob"}:
        return VercelBlobRuntimeStorage(
            read_write_token=blob_read_write_token,
            upload_root=upload_root,
            export_root=export_root,
            export_retention_hours=export_retention_hours,
            upload_retention_hours=upload_retention_hours,
            now_provider=now_provider,
        )
    return LocalRuntimeFileStore(
        upload_root=upload_root,
        export_root=export_root,
        export_retention_hours=export_retention_hours,
        upload_retention_hours=upload_retention_hours,
        now_provider=now_provider,
    )


def get_runtime(request: Request) -> ApiRuntime:
    """Return the service container stored on the FastAPI application."""
    return request.app.state.runtime
