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
from core.models.record import Record
from infrastructure.persistence import LineageStore
from services import review_workflow_service
from services.lineage_service import (
    build_processing_run_input_snapshot,
    build_profile_snapshot,
    build_run_records,
    load_processing_run_input_records,
    normalize_payload,
)
from services.lineage_service import build_historical_export_status
from services.profile_execution_compatibility_adapter import ProfileExecutionCompatibilityAdapter
from services.profile_authoring_service import ProfileAuthoringService
from services.request_context import RequestContext, is_local_request_context, resolve_request_context
from services.review_workflow_service import ReviewLoadResult
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
    current_revision: int
    export_count: int
    last_exported_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProcessingRunSummary:
    """Summary view for one stored run in the run-library workspace."""

    trusted_profile: TrustedProfile | None
    source_document: SourceDocument
    profile_snapshot: ProfileSnapshot
    processing_run: ProcessingRun
    record_count: int
    historical_export_status: HistoricalExportStatus
    current_revision: int
    export_count: int
    last_exported_at: datetime | None


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
        with self._profile_execution_compatibility_adapter.materialize_published_version_bundle(
            profile_context.trusted_profile_version
        ) as materialized_profile_bundle:
            review_result = review_workflow_service.load_review_data(
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
        snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        return self._persist_processing_result(
            profile_context=profile_context,
            profile_snapshot=snapshot,
            source_document=persisted_source_document,
            review_result=review_result,
            parsed_records=review_result.parsed_records,
            created_at=created_at,
            created_by_user_id=persisted_created_by_user_id,
            request_context=request_context,
        )

    def reprocess_processing_run_from_saved_run(
        self,
        processing_run_id: str,
        *,
        profile_name: str | None = None,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> ProcessingRunResult:
        """Create a new immutable run from stored parsed input, without requiring the source PDF."""
        created_at = self._now_provider()
        organization_id = self._request_organization_id(request_context)
        persisted_created_by_user_id = created_by_user_id or self._request_user_id(request_context)
        source_processing_run = self._lineage_store.get_processing_run_for_organization(
            organization_id=organization_id,
            processing_run_id=processing_run_id,
        )
        source_document = self._lineage_store.get_source_document_for_organization(
            organization_id=organization_id,
            source_document_id=source_processing_run.source_document_id,
        )
        parsed_records = self._load_reprocess_input_records(source_processing_run)
        profile_context = self._resolve_profile_context(profile_name, request_context=request_context)
        profile_snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        with self._profile_execution_compatibility_adapter.materialize_published_version_bundle(
            profile_context.trusted_profile_version
        ) as materialized_profile_bundle:
            review_result = review_workflow_service.process_parsed_records(
                parsed_records,
                source_label=source_document.original_filename,
                config_dir=materialized_profile_bundle.config_dir,
                legacy_config_dir=materialized_profile_bundle.legacy_config_dir,
            )
        return self._persist_processing_result(
            profile_context=profile_context,
            profile_snapshot=profile_snapshot,
            source_document=source_document,
            review_result=review_result,
            parsed_records=parsed_records,
            created_at=created_at,
            created_by_user_id=persisted_created_by_user_id,
            request_context=request_context,
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

    def list_processing_runs(
        self,
        *,
        archived: bool = False,
        request_context: RequestContext | None = None,
    ) -> list[ProcessingRunSummary]:
        """List persisted processing runs for one organization and archive state."""
        organization_id = self._request_organization_id(request_context)
        processing_runs = self._lineage_store.list_processing_runs_for_organization(
            organization_id=organization_id,
            archived=archived,
        )
        summaries: list[ProcessingRunSummary] = []
        for processing_run in processing_runs:
            profile_snapshot = self._lineage_store.get_profile_snapshot_for_organization(
                organization_id=organization_id,
                profile_snapshot_id=processing_run.profile_snapshot_id,
            )
            source_document = self._lineage_store.get_source_document_for_organization(
                organization_id=organization_id,
                source_document_id=processing_run.source_document_id,
            )
            review_session = self._get_review_session_for_run(
                organization_id=organization_id,
                processing_run_id=processing_run.processing_run_id,
            )
            export_count = 0
            last_exported_at = None
            current_revision = 0
            if review_session is not None:
                current_revision = review_session.current_revision
                export_artifacts = self._lineage_store.list_export_artifacts(review_session.review_session_id)
                export_count = len(export_artifacts)
                if export_artifacts:
                    last_exported_at = export_artifacts[-1].created_at
            run_records = self._lineage_store.list_run_records_for_processing_run(
                organization_id=organization_id,
                processing_run_id=processing_run.processing_run_id,
            )
            summaries.append(
                ProcessingRunSummary(
                    trusted_profile=self._resolve_origin_trusted_profile(processing_run, profile_snapshot),
                    source_document=source_document,
                    profile_snapshot=profile_snapshot,
                    processing_run=processing_run,
                    record_count=len(run_records),
                    historical_export_status=build_historical_export_status(profile_snapshot),
                    current_revision=current_revision,
                    export_count=export_count,
                    last_exported_at=last_exported_at,
                )
            )
        return summaries

    def archive_processing_run(
        self,
        processing_run_id: str,
        *,
        archived_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> ProcessingRunState:
        """Detach one run from live trusted-profile drift rules without deleting its history."""
        organization_id = self._request_organization_id(request_context)
        persisted_archived_by_user_id = archived_by_user_id or self._request_user_id(request_context)
        processing_run = self._lineage_store.archive_processing_run(
            organization_id=organization_id,
            processing_run_id=processing_run_id,
            archived_at=self._now_provider(),
            archived_by_user_id=persisted_archived_by_user_id,
        )
        profile_snapshot = self._lineage_store.get_profile_snapshot_for_organization(
            organization_id=organization_id,
            profile_snapshot_id=processing_run.profile_snapshot_id,
        )
        return self._build_processing_run_state(processing_run, profile_snapshot)

    def _persist_processing_result(
        self,
        *,
        profile_context: ResolvedTrustedProfile,
        profile_snapshot: ProfileSnapshot,
        source_document: SourceDocument,
        review_result: ReviewLoadResult,
        parsed_records: list[Record],
        created_at: datetime,
        created_by_user_id: str | None,
        request_context: RequestContext | None,
    ) -> ProcessingRunResult:
        """Persist one completed processing run plus input snapshot and emitted rows."""
        processing_run = self._lineage_store.create_processing_run(
            ProcessingRun(
                processing_run_id=f"processing-run:{uuid4()}",
                organization_id=profile_context.organization.organization_id,
                source_document_id=source_document.source_document_id,
                profile_snapshot_id=profile_snapshot.profile_snapshot_id,
                trusted_profile_id=profile_context.trusted_profile.trusted_profile_id,
                trusted_profile_version_id=profile_context.trusted_profile_version.trusted_profile_version_id,
                status="completed",
                engine_version=self._engine_version,
                aggregate_blockers=tuple(review_result.blocking_issues),
                created_at=created_at,
                created_by_user_id=created_by_user_id,
            )
        )
        self._lineage_store.create_processing_run_input_snapshot(
            build_processing_run_input_snapshot(
                input_snapshot_id=f"{processing_run.processing_run_id}:input-snapshot",
                organization_id=profile_context.organization.organization_id,
                processing_run_id=processing_run.processing_run_id,
                records=parsed_records,
                created_at=created_at,
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
            profile_snapshot=profile_snapshot,
            source_document=source_document,
            processing_run=processing_run,
            run_records=run_records,
        )

    def _load_reprocess_input_records(self, source_processing_run: ProcessingRun) -> list[Record]:
        """Load parser-output records for a saved run, with legacy canonical-row fallback."""
        try:
            snapshot = self._lineage_store.get_processing_run_input_snapshot_for_processing_run(
                organization_id=source_processing_run.organization_id,
                processing_run_id=source_processing_run.processing_run_id,
            )
            return load_processing_run_input_records(snapshot)
        except KeyError:
            run_records = self._lineage_store.list_run_records_for_processing_run(
                organization_id=source_processing_run.organization_id,
                processing_run_id=source_processing_run.processing_run_id,
            )
            if not run_records:
                raise FileNotFoundError(
                    "The saved run has no parsed input snapshot or legacy run records available for reprocessing."
                )
            return [
                Record(**self._sanitize_legacy_canonical_record_for_reprocess(run_record.canonical_record))
                for run_record in run_records
            ]

    def _sanitize_legacy_canonical_record_for_reprocess(self, canonical_record: dict[str, object]) -> dict[str, object]:
        """Strip profile-derived values from legacy run rows before re-normalizing them."""
        payload = normalize_payload(canonical_record)
        payload.update(
            {
                "record_type_normalized": None,
                "labor_class_normalized": None,
                "recap_labor_slot_id": None,
                "recap_labor_classification": None,
                "recap_equipment_slot_id": None,
                "vendor_name_normalized": None,
                "equipment_category": None,
                "equipment_mapping_key": None,
                "is_omitted": False,
                "warnings": [],
            }
        )
        return payload

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
        trusted_profile = self._resolve_origin_trusted_profile(processing_run, profile_snapshot)
        run_records = self._lineage_store.list_run_records_for_processing_run(
            organization_id=processing_run.organization_id,
            processing_run_id=processing_run.processing_run_id,
        )
        review_session = self._get_review_session_for_run(
            organization_id=processing_run.organization_id,
            processing_run_id=processing_run.processing_run_id,
        )
        export_count = 0
        last_exported_at = None
        current_revision = 0
        if review_session is not None:
            current_revision = review_session.current_revision
            export_artifacts = self._lineage_store.list_export_artifacts(review_session.review_session_id)
            export_count = len(export_artifacts)
            if export_artifacts:
                last_exported_at = export_artifacts[-1].created_at
        return ProcessingRunState(
            organization=organization,
            trusted_profile=trusted_profile,
            profile_snapshot=profile_snapshot,
            source_document=source_document,
            processing_run=processing_run,
            run_records=run_records,
            historical_export_status=build_historical_export_status(profile_snapshot),
            current_revision=current_revision,
            export_count=export_count,
            last_exported_at=last_exported_at,
        )

    def _resolve_origin_trusted_profile(
        self,
        processing_run: ProcessingRun,
        profile_snapshot: ProfileSnapshot,
    ) -> TrustedProfile | None:
        """Resolve one run's origin profile even after live linkage has been archived away."""
        if profile_snapshot.trusted_profile_version_id:
            trusted_profile_version = self._lineage_store.get_trusted_profile_version_for_organization(
                organization_id=processing_run.organization_id,
                trusted_profile_version_id=profile_snapshot.trusted_profile_version_id,
            )
            return self._lineage_store.get_trusted_profile_for_organization(
                organization_id=processing_run.organization_id,
                trusted_profile_id=trusted_profile_version.trusted_profile_id,
            )
        if processing_run.trusted_profile_id:
            return self._lineage_store.get_trusted_profile_for_organization(
                organization_id=processing_run.organization_id,
                trusted_profile_id=processing_run.trusted_profile_id,
            )
        return None

    def _get_review_session_for_run(
        self,
        *,
        organization_id: str,
        processing_run_id: str,
    ):
        """Return one existing review session for a run when present."""
        try:
            return self._lineage_store.get_review_session_for_run_for_organization(
                organization_id=organization_id,
                processing_run_id=processing_run_id,
            )
        except KeyError:
            return None

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
