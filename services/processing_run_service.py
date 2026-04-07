"""Application service for trusted-profile snapshot resolution and processing-run persistence."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.config import ProfileManager
from core.models.lineage import (
    HistoricalExportStatus,
    Organization,
    ProcessingRun,
    ProfileSnapshot,
    RunRecord,
    SourceDocument,
    TrustedProfile,
    TrustedProfileVersion,
)
from infrastructure.persistence.sqlite_lineage_store import SqliteLineageStore
from services.lineage_service import build_profile_snapshot, build_run_records
from services.lineage_service import build_historical_export_status
from services.profile_authoring_service import ProfileAuthoringService
from services.review_workflow_service import load_review_data
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository


@dataclass(frozen=True, slots=True)
class ProcessingRunResult:
    """Persisted lineage created for one processing invocation."""

    organization: Organization
    trusted_profile: TrustedProfile
    profile_snapshot: ProfileSnapshot
    source_document: SourceDocument
    processing_run: ProcessingRun
    run_records: list[RunRecord]


@dataclass(frozen=True, slots=True)
class ProcessingRunState:
    """Immutable processing-run lineage and emitted records for API/read workflows."""

    organization: Organization
    trusted_profile: TrustedProfile | None
    profile_snapshot: ProfileSnapshot
    source_document: SourceDocument
    processing_run: ProcessingRun
    run_records: list[RunRecord]
    historical_export_status: HistoricalExportStatus


@dataclass(frozen=True, slots=True)
class _ResolvedProfileContext:
    """One selected trusted profile bundle resolved for snapshotting and processing."""

    organization: Organization
    trusted_profile: TrustedProfile
    trusted_profile_version: TrustedProfileVersion


class ProcessingRunService:
    """Resolve trusted-profile snapshots and persist immutable processing runs."""

    def __init__(
        self,
        *,
        lineage_store: SqliteLineageStore,
        profile_manager: ProfileManager | None = None,
        engine_version: str = "dev-local",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._profile_manager = profile_manager or ProfileManager()
        self._engine_version = str(engine_version).strip() or "dev-local"
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._trusted_profile_authoring_repository = TrustedProfileAuthoringRepository(
            lineage_store=self._lineage_store,
            profile_manager=self._profile_manager,
            now_provider=self._now_provider,
        )
        self._profile_authoring_service = ProfileAuthoringService(
            repository=self._trusted_profile_authoring_repository,
            profile_manager=self._profile_manager,
            now_provider=self._now_provider,
        )

    def resolve_trusted_profile_snapshot(
        self,
        profile_name: str | None = None,
    ) -> tuple[Organization, TrustedProfile, ProfileSnapshot]:
        """Resolve the current effective trusted profile to a persisted immutable snapshot."""
        profile_context = self._resolve_profile_context(profile_name)
        persisted_snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        return (
            profile_context.organization,
            profile_context.trusted_profile,
            persisted_snapshot,
        )

    def create_processing_run(
        self,
        source_document_path: str | Path,
        *,
        profile_name: str | None = None,
        created_by_user_id: str | None = None,
        storage_ref: str | None = None,
    ) -> ProcessingRunResult:
        """Process one source document against one trusted-profile snapshot and persist immutable run records."""
        created_at = self._now_provider()
        source_path = Path(source_document_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Source document was not found: {source_path}")

        profile_context = self._resolve_profile_context(profile_name)
        snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        with self._trusted_profile_authoring_repository.materialize_published_version_bundle(
            profile_context.trusted_profile_version
        ) as materialized_profile_dir:
            review_result = load_review_data(
                str(source_path),
                config_dir=materialized_profile_dir,
                legacy_config_dir=self._get_legacy_config_dir(),
            )
        source_document_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        persisted_storage_ref = str(storage_ref).strip() if storage_ref else str(source_path)

        persisted_source_document = self._lineage_store.get_or_create_source_document(
            SourceDocument(
                source_document_id=self._build_source_document_id(
                    file_hash=source_document_hash,
                    storage_ref=persisted_storage_ref,
                ),
                organization_id=profile_context.organization.organization_id,
                original_filename=source_path.name,
                file_hash=source_document_hash,
                storage_ref=persisted_storage_ref,
                content_type=mimetypes.guess_type(source_path.name)[0] or "application/pdf",
                file_size_bytes=source_path.stat().st_size,
                uploaded_by_user_id=created_by_user_id,
                created_at=created_at,
            )
        )

        processing_run = self._lineage_store.create_processing_run(
            ProcessingRun(
                processing_run_id=f"processing-run:{uuid4()}",
                organization_id=profile_context.organization.organization_id,
                source_document_id=persisted_source_document.source_document_id,
                profile_snapshot_id=snapshot.profile_snapshot_id,
                trusted_profile_id=profile_context.trusted_profile.trusted_profile_id,
                trusted_profile_version_id=profile_context.trusted_profile_version.trusted_profile_version_id,
                status="completed",
                engine_version=self._engine_version,
                aggregate_blockers=tuple(review_result.blocking_issues),
                created_at=created_at,
                created_by_user_id=created_by_user_id,
            )
        )
        run_records = self._lineage_store.create_run_records(
            build_run_records(
                organization_id=profile_context.organization.organization_id,
                processing_run_id=processing_run.processing_run_id,
                records=review_result.records,
                created_at=created_at,
            )
        )
        self._profile_authoring_service.capture_unmapped_observations(
            profile_context.trusted_profile.trusted_profile_id,
            processing_run_id=processing_run.processing_run_id,
            records=review_result.records,
        )
        return ProcessingRunResult(
            organization=profile_context.organization,
            trusted_profile=profile_context.trusted_profile,
            profile_snapshot=snapshot,
            source_document=persisted_source_document,
            processing_run=processing_run,
            run_records=run_records,
        )

    def get_processing_run_state(self, processing_run_id: str) -> ProcessingRunState:
        """Fetch immutable run lineage plus emitted run records for one processing run."""
        processing_run = self._lineage_store.get_processing_run(processing_run_id)
        profile_snapshot = self._lineage_store.get_profile_snapshot(processing_run.profile_snapshot_id)
        return self._build_processing_run_state(processing_run, profile_snapshot)

    def _resolve_profile_context(self, profile_name: str | None) -> _ResolvedProfileContext:
        """Resolve one selected trusted profile bundle for snapshotting and processing."""
        resolved_profile = self._trusted_profile_authoring_repository.resolve_current_published_profile(
            profile_name
        )
        return _ResolvedProfileContext(
            organization=resolved_profile.organization,
            trusted_profile=resolved_profile.trusted_profile,
            trusted_profile_version=resolved_profile.trusted_profile_version,
        )

    def _build_processing_run_state(
        self,
        processing_run: ProcessingRun,
        profile_snapshot: ProfileSnapshot,
    ) -> ProcessingRunState:
        """Build immutable processing-run state from persisted lineage."""
        organization = self._lineage_store.ensure_organization(
            organization_id=processing_run.organization_id,
            slug="default-org",
            display_name="Default Organization",
            created_at=processing_run.created_at,
            is_seeded=True,
        )
        source_document = self._lineage_store.get_source_document(processing_run.source_document_id)
        trusted_profile = (
            self._lineage_store.get_trusted_profile(processing_run.trusted_profile_id)
            if processing_run.trusted_profile_id
            else None
        )
        run_records = self._lineage_store.list_run_records(processing_run.processing_run_id)
        return ProcessingRunState(
            organization=organization,
            trusted_profile=trusted_profile,
            profile_snapshot=profile_snapshot,
            source_document=source_document,
            processing_run=processing_run,
            run_records=run_records,
            historical_export_status=build_historical_export_status(profile_snapshot),
        )

    def _create_or_reuse_profile_snapshot(
        self,
        profile_context: _ResolvedProfileContext,
    ) -> ProfileSnapshot:
        """Create or reuse the immutable snapshot for one resolved behavioral bundle."""
        full_bundle_payload = profile_context.trusted_profile_version.bundle_payload
        behavioral_hash_payload = dict(full_bundle_payload.get("behavioral_bundle", {}))
        snapshot = build_profile_snapshot(
            profile_snapshot_id=f"profile-snapshot:{profile_context.organization.organization_id}:{uuid4()}",
            organization_id=profile_context.organization.organization_id,
            trusted_profile_id=None,
            trusted_profile_version_id=profile_context.trusted_profile_version.trusted_profile_version_id,
            bundle_payload=full_bundle_payload,
            hash_payload=behavioral_hash_payload,
            engine_version=self._engine_version,
            created_at=self._now_provider(),
            template_artifact_id=profile_context.trusted_profile_version.template_artifact_id,
            template_artifact_ref=profile_context.trusted_profile_version.template_artifact_ref,
            template_file_hash=profile_context.trusted_profile_version.template_file_hash,
        )
        return self._lineage_store.get_or_create_profile_snapshot(snapshot)

    def _get_legacy_config_dir(self) -> Path | None:
        """Reuse the configured shared-config root when a custom profile manager is supplied."""
        legacy_config_dir = getattr(self._profile_manager, "_legacy_config_root", None)
        if isinstance(legacy_config_dir, Path):
            return legacy_config_dir
        return None

    def _build_source_document_id(self, *, file_hash: str, storage_ref: str) -> str:
        """Build a stable source-document identity from file hash and storage location."""
        storage_value = storage_ref.encode("utf-8")
        storage_hash = hashlib.sha256(storage_value).hexdigest()[:12]
        return f"source-document:{file_hash}:{storage_hash}"
