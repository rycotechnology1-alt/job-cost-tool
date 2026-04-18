"""Application service for trusted-profile snapshot resolution and processing-run persistence."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.models.lineage import (
    HistoricalExportStatus,
    Organization,
    ProcessingRun,
    ProfileSnapshot,
    RunRecord,
    SourceDocument,
    TrustedProfile,
)
from infrastructure.persistence import LineageStore
from services.lineage_service import build_profile_snapshot, build_run_records
from services.lineage_service import build_historical_export_status
from services.profile_execution_compatibility_adapter import ProfileExecutionCompatibilityAdapter
from services.profile_authoring_service import ProfileAuthoringService
from services.request_context import RequestContext, is_local_request_context, resolve_request_context
from services.review_workflow_service import load_review_data
from services.trusted_profile_provisioning_service import (
    ResolvedTrustedProfile,
    TrustedProfileProvisioningService,
)


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


class ProcessingRunService:
    """Resolve trusted-profile snapshots and persist immutable processing runs."""

    def __init__(
        self,
        *,
        lineage_store: LineageStore,
        trusted_profile_provisioning_service: TrustedProfileProvisioningService,
        profile_execution_compatibility_adapter: ProfileExecutionCompatibilityAdapter,
        profile_authoring_service: ProfileAuthoringService,
        engine_version: str = "dev-local",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._engine_version = str(engine_version).strip() or "dev-local"
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._trusted_profile_provisioning_service = trusted_profile_provisioning_service
        self._profile_execution_compatibility_adapter = profile_execution_compatibility_adapter
        self._profile_authoring_service = profile_authoring_service

    def resolve_trusted_profile_snapshot(
        self,
        profile_name: str | None = None,
        *,
        request_context: RequestContext | None = None,
    ) -> tuple[Organization, TrustedProfile, ProfileSnapshot]:
        """Resolve the current effective trusted profile to a persisted immutable snapshot."""
        profile_context = self._resolve_profile_context(profile_name, request_context=request_context)
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
        request_context: RequestContext | None = None,
    ) -> ProcessingRunResult:
        """Process one source document against one trusted-profile snapshot and persist immutable run records."""
        created_at = self._now_provider()
        source_path = Path(source_document_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Source document was not found: {source_path}")
        persisted_created_by_user_id = created_by_user_id or self._request_user_id(request_context)

        profile_context = self._resolve_profile_context(profile_name, request_context=request_context)
        snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        with self._profile_execution_compatibility_adapter.materialize_published_version_bundle(
            profile_context.trusted_profile_version
        ) as materialized_profile_bundle:
            review_result = load_review_data(
                str(source_path),
                config_dir=materialized_profile_bundle.config_dir,
                legacy_config_dir=materialized_profile_bundle.legacy_config_dir,
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
                uploaded_by_user_id=persisted_created_by_user_id,
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
                created_by_user_id=persisted_created_by_user_id,
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
            published_version=profile_context.trusted_profile_version,
            request_context=request_context,
        )
        return ProcessingRunResult(
            organization=profile_context.organization,
            trusted_profile=profile_context.trusted_profile,
            profile_snapshot=snapshot,
            source_document=persisted_source_document,
            processing_run=processing_run,
            run_records=run_records,
        )

    def get_processing_run_state(
        self,
        processing_run_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> ProcessingRunState:
        """Fetch immutable run lineage plus emitted run records for one processing run."""
        organization_id = self._request_organization_id(request_context)
        processing_run = self._lineage_store.get_processing_run_for_organization(
            organization_id=organization_id,
            processing_run_id=processing_run_id,
        )
        profile_snapshot = self._lineage_store.get_profile_snapshot_for_organization(
            organization_id=organization_id,
            profile_snapshot_id=processing_run.profile_snapshot_id,
        )
        return self._build_processing_run_state(processing_run, profile_snapshot)

    def _resolve_profile_context(
        self,
        profile_name: str | None,
        *,
        request_context: RequestContext | None = None,
    ) -> ResolvedTrustedProfile:
        """Resolve one selected trusted profile bundle for snapshotting and processing."""
        return self._trusted_profile_provisioning_service.resolve_current_published_profile(
            profile_name,
            request_context=request_context,
        )

    def _build_processing_run_state(
        self,
        processing_run: ProcessingRun,
        profile_snapshot: ProfileSnapshot,
    ) -> ProcessingRunState:
        """Build immutable processing-run state from persisted lineage."""
        organization = self._build_organization(processing_run.organization_id, processing_run.created_at)
        source_document = self._lineage_store.get_source_document_for_organization(
            organization_id=processing_run.organization_id,
            source_document_id=processing_run.source_document_id,
        )
        trusted_profile = (
            self._lineage_store.get_trusted_profile_for_organization(
                organization_id=processing_run.organization_id,
                trusted_profile_id=processing_run.trusted_profile_id,
            )
            if processing_run.trusted_profile_id
            else None
        )
        run_records = self._lineage_store.list_run_records_for_processing_run(
            organization_id=processing_run.organization_id,
            processing_run_id=processing_run.processing_run_id,
        )
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
        profile_context: ResolvedTrustedProfile,
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

    def _build_source_document_id(self, *, file_hash: str, storage_ref: str) -> str:
        """Build a stable source-document identity from file hash and storage location."""
        storage_value = storage_ref.encode("utf-8")
        storage_hash = hashlib.sha256(storage_value).hexdigest()[:12]
        return f"source-document:{file_hash}:{storage_hash}"

    def _request_organization_id(self, request_context: RequestContext | None) -> str:
        """Return the current request organization id for hosted reads."""
        return resolve_request_context(request_context).organization_id

    def _request_user_id(self, request_context: RequestContext | None) -> str | None:
        """Return the current request user id for audit fields."""
        if is_local_request_context(request_context):
            return None
        return resolve_request_context(request_context).user_id

    def _build_organization(self, organization_id: str, created_at: datetime) -> Organization:
        """Build a stable organization view for one persisted run without mutating persistence on reads."""
        return Organization(
            organization_id=organization_id,
            slug=self._organization_slug(organization_id),
            display_name=self._organization_display_name(organization_id),
            created_at=created_at,
            is_seeded=organization_id == "org-default",
        )

    def _organization_slug(self, organization_id: str) -> str:
        """Build a stable organization slug from one organization id."""
        if organization_id == "org-default":
            return "default-org"
        normalized = str(organization_id or "").strip().lower().replace("_", "-").replace(":", "-")
        return normalized or "organization"

    def _organization_display_name(self, organization_id: str) -> str:
        """Build a human-readable organization display name from one organization id."""
        if organization_id == "org-default":
            return "Default Organization"
        return str(organization_id or "").strip() or "Organization"
