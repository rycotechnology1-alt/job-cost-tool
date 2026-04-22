"""Application service for review-session overlays and exact-revision export lineage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Sequence
from uuid import uuid4

from core.models import PendingRecordEdit, Record
from core.models.lineage import (
    ExportArtifact,
    HistoricalExportStatus,
    ProcessingRun,
    ProfileSnapshot,
    ReviewSession,
    RunRecord,
    SourceDocument,
    TrustedProfile,
)
from infrastructure.persistence import LineageStore
from infrastructure.storage import RuntimeStorage, StoredArtifact
from services.export_service import export_records_to_recap
from services.lineage_service import (
    append_review_edit_batch,
    build_export_artifact,
    build_historical_export_status,
    create_review_session,
    rebuild_review_records,
)
from services.profile_authoring_errors import ProfileAuthoringPersistenceConflictError
from services.profile_execution_compatibility_adapter import ProfileExecutionCompatibilityAdapter
from services.request_context import RequestContext, is_local_request_context, resolve_request_context
from services.review_workflow_service import load_edit_options, prepare_review_updates
from services.validation_service import validate_review_records


@dataclass(frozen=True, slots=True)
class ReviewSessionState:
    """Effective review state for one immutable run at one session revision."""

    processing_run: ProcessingRun
    profile_snapshot: ProfileSnapshot
    source_document: SourceDocument
    trusted_profile: TrustedProfile | None
    review_session: ReviewSession
    run_records: list[RunRecord]
    records: list[Record]
    blocking_issues: list[str]
    labor_classification_options: list[str]
    equipment_classification_options: list[str]
    session_revision: int
    historical_export_status: HistoricalExportStatus


@dataclass(frozen=True, slots=True)
class ReviewSessionExportResult:
    """Exact-revision export output plus its persisted lineage."""

    review_session_state: ReviewSessionState
    export_artifact: ExportArtifact
    output_path: Path
    stored_artifact: StoredArtifact | None = None


class HistoricalExportUnavailableError(RuntimeError):
    """Raised when exact historical export lineage is unavailable for a processing run."""

    def __init__(self, status: HistoricalExportStatus) -> None:
        self.status = status
        super().__init__(status.detail)


class ReviewSessionService:
    """Persist append-only review overlays and export one exact session revision."""

    def __init__(
        self,
        *,
        lineage_store: LineageStore,
        profile_execution_compatibility_adapter: ProfileExecutionCompatibilityAdapter,
        artifact_store: RuntimeStorage | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._profile_execution_compatibility_adapter = profile_execution_compatibility_adapter
        self._artifact_store = artifact_store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def open_review_session(
        self,
        processing_run_id: str,
        *,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> ReviewSessionState:
        """Open or create the phase-1 review session and resume its latest revision."""
        return self.get_review_session_state(
            processing_run_id,
            created_by_user_id=created_by_user_id,
            request_context=request_context,
        )

    def get_review_session_state(
        self,
        processing_run_id: str,
        *,
        session_revision: int | None = None,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> ReviewSessionState:
        """Return effective review records for one run at one exact session revision."""
        persisted_created_by_user_id = created_by_user_id or self._request_user_id(request_context)
        context = self._load_run_context(
            processing_run_id,
            create_session=True,
            created_by_user_id=persisted_created_by_user_id,
            request_context=request_context,
        )
        target_revision = context.review_session.current_revision if session_revision is None else session_revision
        if target_revision < 0:
            raise ValueError("session_revision must be greater than or equal to 0.")
        if target_revision > context.review_session.current_revision:
            raise ValueError("session_revision cannot be greater than the review session's current revision.")

        reviewed_record_edits = self._lineage_store.list_reviewed_record_edits_for_review_session(
            organization_id=context.processing_run.organization_id,
            review_session_id=context.review_session.review_session_id,
            up_to_revision=target_revision,
        )
        effective_records = rebuild_review_records(
            run_records=context.run_records,
            reviewed_record_edits=reviewed_record_edits,
        )
        base_records = rebuild_review_records(
            run_records=context.run_records,
            reviewed_record_edits=[],
        )
        validated_records, blocking_issues = validate_review_records(base_records, effective_records)
        with self._profile_execution_compatibility_adapter.materialize_snapshot_bundle(
            context.profile_snapshot,
            require_template_artifact=False,
        ) as snapshot_bundle:
            labor_options, equipment_options = load_edit_options(
                config_dir=snapshot_bundle.config_dir,
                legacy_config_dir=snapshot_bundle.legacy_config_dir,
            )
        return ReviewSessionState(
            processing_run=context.processing_run,
            profile_snapshot=context.profile_snapshot,
            source_document=context.source_document,
            trusted_profile=context.trusted_profile,
            review_session=context.review_session,
            run_records=context.run_records,
            records=list(validated_records),
            blocking_issues=list(blocking_issues),
            labor_classification_options=labor_options,
            equipment_classification_options=equipment_options,
            session_revision=target_revision,
            historical_export_status=build_historical_export_status(context.profile_snapshot),
        )

    def apply_review_edits(
        self,
        processing_run_id: str,
        pending_edits: Sequence[PendingRecordEdit],
        *,
        expected_current_revision: int | None = None,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> ReviewSessionState:
        """Append one accepted review-edit batch without mutating immutable run rows."""
        persisted_created_by_user_id = created_by_user_id or self._request_user_id(request_context)
        context = self._load_run_context(
            processing_run_id,
            create_session=True,
            created_by_user_id=persisted_created_by_user_id,
            request_context=request_context,
        )
        resolved_expected_current_revision = self._resolve_expected_current_revision_for_review_edit(
            context.review_session,
            expected_current_revision=expected_current_revision,
            request_context=request_context,
        )
        run_record_keys = {run_record.record_key for run_record in context.run_records}
        prepared_pending_edits: list[PendingRecordEdit] = []

        with self._profile_execution_compatibility_adapter.materialize_snapshot_bundle(
            context.profile_snapshot,
        ) as snapshot_bundle:
            for pending_edit in pending_edits:
                if pending_edit.record_key not in run_record_keys:
                    raise KeyError(
                        f"record_key '{pending_edit.record_key}' does not exist in ProcessingRun "
                        f"'{processing_run_id}'."
                    )
                changed_fields = prepare_review_updates(
                    pending_edit.changed_fields,
                    config_dir=snapshot_bundle.config_dir,
                    legacy_config_dir=snapshot_bundle.legacy_config_dir,
                )
                prepared_pending_edits.append(
                    PendingRecordEdit(
                        record_key=pending_edit.record_key,
                        changed_fields=changed_fields,
                    )
                )

        updated_session, persisted_edits = append_review_edit_batch(
            review_session=context.review_session,
            pending_edits=prepared_pending_edits,
            created_at=self._now_provider(),
            created_by_user_id=persisted_created_by_user_id,
        )
        self._lineage_store.save_review_session_edits(
            updated_session,
            persisted_edits,
            expected_current_revision=resolved_expected_current_revision,
        )
        return self.get_review_session_state(
            processing_run_id,
            session_revision=updated_session.current_revision,
            request_context=request_context,
        )

    def export_session_revision(
        self,
        processing_run_id: str,
        *,
        session_revision: int,
        output_path: str | Path | None = None,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> ReviewSessionExportResult:
        """Generate one workbook from one exact persisted session revision and record its lineage."""
        self.cleanup_expired_export_artifacts()
        persisted_created_by_user_id = created_by_user_id or self._request_user_id(request_context)
        review_session_state = self.get_review_session_state(
            processing_run_id,
            session_revision=session_revision,
            created_by_user_id=persisted_created_by_user_id,
            request_context=request_context,
        )
        if not review_session_state.historical_export_status.is_reproducible:
            raise HistoricalExportUnavailableError(review_session_state.historical_export_status)

        if output_path is not None:
            resolved_output_path = Path(output_path).expanduser().resolve()
            with self._profile_execution_compatibility_adapter.materialize_snapshot_bundle(
                review_session_state.profile_snapshot,
            ) as snapshot_bundle:
                if snapshot_bundle.template_path is None:
                    raise HistoricalExportUnavailableError(review_session_state.historical_export_status)
                export_records_to_recap(
                    review_session_state.records,
                    str(snapshot_bundle.template_path),
                    str(resolved_output_path),
                    config_dir=snapshot_bundle.config_dir,
                    legacy_config_dir=snapshot_bundle.legacy_config_dir,
                )
            stored_artifact = None
        else:
            if self._artifact_store is None:
                raise ValueError("output_path is required when no artifact_store is configured.")
            stored_artifact = self._export_via_artifact_store(
                review_session_state=review_session_state,
            )
            resolved_output_path = stored_artifact.file_path

        file_hash = hashlib.sha256(resolved_output_path.read_bytes()).hexdigest()
        try:
            export_artifact = self._lineage_store.create_export_artifact(
                build_export_artifact(
                    export_artifact_id=f"export-artifact:{review_session_state.review_session.review_session_id}:{uuid4()}",
                    organization_id=review_session_state.processing_run.organization_id,
                    processing_run=review_session_state.processing_run,
                    review_session=review_session_state.review_session,
                    session_revision=session_revision,
                    artifact_kind="recap_workbook",
                    storage_ref=stored_artifact.storage_ref if stored_artifact else str(resolved_output_path),
                    created_at=self._now_provider(),
                    expires_at=stored_artifact.expires_at if stored_artifact else None,
                    created_by_user_id=persisted_created_by_user_id,
                    file_hash=file_hash,
                )
            )
            self._lineage_store.purge_processing_run_workflow(
                processing_run_id=review_session_state.processing_run.processing_run_id,
            )
        except Exception:
            if 'export_artifact' in locals():
                self._cleanup_failed_retained_export_metadata(export_artifact.export_artifact_id)
            if stored_artifact is not None:
                self._cleanup_failed_export_artifact(stored_artifact)
            raise
        return ReviewSessionExportResult(
            review_session_state=review_session_state,
            export_artifact=export_artifact,
            output_path=resolved_output_path,
            stored_artifact=stored_artifact,
        )

    def get_export_artifact(
        self,
        export_artifact_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> ExportArtifact:
        """Fetch one persisted export artifact for API/download workflows."""
        self.cleanup_expired_export_artifacts()
        export_artifact = self._lineage_store.get_export_artifact_for_organization(
            organization_id=self._request_organization_id(request_context),
            export_artifact_id=export_artifact_id,
        )
        if self._export_artifact_is_expired(export_artifact):
            self._delete_retained_export_artifact(export_artifact)
            raise KeyError(f"ExportArtifact '{export_artifact_id}' was not found.")
        return export_artifact

    def resolve_export_artifact_payload(
        self,
        export_artifact_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> StoredArtifact:
        """Resolve one persisted export artifact through the configured storage seam."""
        if self._artifact_store is None:
            raise ValueError("artifact_store is required to resolve persisted export payloads.")
        export_artifact = self.get_export_artifact(
            export_artifact_id,
            request_context=request_context,
        )
        try:
            return self._artifact_store.get_export_artifact(export_artifact.storage_ref)
        except FileNotFoundError:
            self._cleanup_failed_retained_export_metadata(export_artifact.export_artifact_id)
            raise

    def cleanup_expired_export_artifacts(self) -> int:
        """Delete expired retained export metadata and storage payloads."""
        artifact_store = self._artifact_store
        if artifact_store is None:
            return 0
        expired_artifacts = self._lineage_store.list_expired_export_artifacts(
            expires_before=self._now_provider(),
        )
        for export_artifact in expired_artifacts:
            self._delete_retained_export_artifact(export_artifact)
        orphaned_storage_cleanup_count = artifact_store.cleanup_expired_export_artifacts()
        return max(len(expired_artifacts), orphaned_storage_cleanup_count)

    def _load_run_context(
        self,
        processing_run_id: str,
        *,
        create_session: bool,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> _RunContext:
        organization_id = self._request_organization_id(request_context)
        processing_run = self._lineage_store.get_processing_run_for_organization(
            organization_id=organization_id,
            processing_run_id=processing_run_id,
        )
        profile_snapshot = self._lineage_store.get_profile_snapshot_for_organization(
            organization_id=organization_id,
            profile_snapshot_id=processing_run.profile_snapshot_id,
        )
        trusted_profile = None
        if processing_run.trusted_profile_id:
            trusted_profile = self._lineage_store.get_trusted_profile_for_organization(
                organization_id=organization_id,
                trusted_profile_id=processing_run.trusted_profile_id,
            )
        source_document = self._lineage_store.get_source_document_for_organization(
            organization_id=organization_id,
            source_document_id=processing_run.source_document_id,
        )

        if create_session:
            review_session = self._lineage_store.get_or_create_review_session(
                create_review_session(
                    review_session_id=f"review-session:{processing_run.processing_run_id}",
                    organization_id=processing_run.organization_id,
                    processing_run_id=processing_run.processing_run_id,
                    created_at=self._now_provider(),
                    created_by_user_id=created_by_user_id,
                )
            )
        else:
            review_session = self._lineage_store.get_review_session_for_run_for_organization(
                organization_id=organization_id,
                processing_run_id=processing_run.processing_run_id,
            )

        run_records = self._lineage_store.list_run_records_for_processing_run(
            organization_id=organization_id,
            processing_run_id=processing_run.processing_run_id,
        )
        return _RunContext(
            processing_run=processing_run,
            profile_snapshot=profile_snapshot,
            source_document=source_document,
            trusted_profile=trusted_profile,
            review_session=review_session,
            run_records=run_records,
        )

    def _export_via_artifact_store(
        self,
        *,
        review_session_state: ReviewSessionState,
    ) -> StoredArtifact:
        """Generate one workbook into temporary storage, then persist it through the runtime storage seam."""
        with TemporaryDirectory(prefix="job-cost-export-artifact-") as export_tmp:
            temp_output_path = Path(export_tmp).resolve() / "recap-export.xlsx"
            with self._profile_execution_compatibility_adapter.materialize_snapshot_bundle(
                review_session_state.profile_snapshot,
            ) as snapshot_bundle:
                if snapshot_bundle.template_path is None:
                    raise HistoricalExportUnavailableError(review_session_state.historical_export_status)
                export_records_to_recap(
                    review_session_state.records,
                    str(snapshot_bundle.template_path),
                    str(temp_output_path),
                    config_dir=snapshot_bundle.config_dir,
                    legacy_config_dir=snapshot_bundle.legacy_config_dir,
                )
            return self._artifact_store.save_export_artifact(
                processing_run_id=review_session_state.processing_run.processing_run_id,
                session_revision=review_session_state.session_revision,
                original_filename=self._build_export_filename(
                    review_session_state.source_document.original_filename,
                    review_session_state.session_revision,
                ),
                content_bytes=temp_output_path.read_bytes(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    def _build_export_filename(self, source_filename: str, session_revision: int) -> str:
        """Derive a user-facing workbook filename from the source report when practical."""
        source_name = Path(str(source_filename or "").strip()).name
        source_stem = Path(source_name).stem.strip()
        if not source_stem:
            source_stem = "recap-export"
        return f"{source_stem}-recap-rev-{session_revision}.xlsx"

    def _resolve_expected_current_revision_for_review_edit(
        self,
        review_session: ReviewSession,
        *,
        expected_current_revision: int | None,
        request_context: RequestContext | None,
    ) -> int:
        """Require hosted review writes to send CAS state while keeping local callers compatible."""
        if expected_current_revision is None:
            if is_local_request_context(request_context):
                return review_session.current_revision
            raise ValueError("expected_current_revision is required for hosted review edit requests.")
        if expected_current_revision != review_session.current_revision:
            raise ProfileAuthoringPersistenceConflictError(
                f"Review session '{review_session.review_session_id}' is stale.",
                error_code="review_session_persistence_conflict",
                field_errors={
                    "expected_current_revision": [
                        "Refresh the review session and retry with the latest revision before saving edits.",
                    ]
                },
            )
        return expected_current_revision

    def _cleanup_failed_export_artifact(self, stored_artifact: StoredArtifact) -> None:
        """Best-effort cleanup when artifact storage succeeds but lineage persistence fails."""
        artifact_store = self._artifact_store
        if artifact_store is None:
            return
        try:
            artifact_store.delete_export_artifact(stored_artifact.storage_ref)
        except Exception:
            pass

    def _cleanup_failed_retained_export_metadata(self, export_artifact_id: str) -> None:
        """Best-effort cleanup when retained export metadata should not survive a failed export flow."""
        try:
            self._lineage_store.delete_export_artifact(export_artifact_id)
        except Exception:
            pass

    def _delete_retained_export_artifact(self, export_artifact: ExportArtifact) -> None:
        """Delete one retained export artifact from metadata and runtime storage."""
        artifact_store = self._artifact_store
        if artifact_store is not None:
            try:
                artifact_store.delete_export_artifact(export_artifact.storage_ref)
            except Exception:
                pass
        self._cleanup_failed_retained_export_metadata(export_artifact.export_artifact_id)

    def _export_artifact_is_expired(self, export_artifact: ExportArtifact) -> bool:
        """Return whether one retained export artifact is already past its retention window."""
        if export_artifact.expires_at is None:
            return False
        return self._now_provider() >= export_artifact.expires_at

    def _request_organization_id(self, request_context: RequestContext | None) -> str:
        """Return the current request organization id for hosted reads."""
        return resolve_request_context(request_context).organization_id

    def _request_user_id(self, request_context: RequestContext | None) -> str | None:
        """Return the current request user id for audit fields."""
        if is_local_request_context(request_context):
            return None
        return resolve_request_context(request_context).user_id


@dataclass(frozen=True, slots=True)
class _RunContext:
    """Loaded immutable lineage needed to evaluate one review session."""

    processing_run: ProcessingRun
    profile_snapshot: ProfileSnapshot
    source_document: SourceDocument
    trusted_profile: TrustedProfile | None
    review_session: ReviewSession
    run_records: list[RunRecord]
