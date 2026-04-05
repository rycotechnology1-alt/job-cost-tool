"""Response-shaping helpers that keep FastAPI routes thin."""

from __future__ import annotations

from dataclasses import asdict

from api.schemas.common import HistoricalExportStatusResponse, ReviewRecordResponse, RunRecordResponse
from api.schemas.exports import ExportArtifactResponse
from api.schemas.runs import ProcessingRunDetailResponse, ProcessingRunResponse
from api.schemas.review_sessions import ReviewSessionResponse
from api.schemas.trusted_profiles import TrustedProfileResponse
from api.schemas.uploads import SourceUploadResponse
from infrastructure.storage import StoredUpload
from services.lineage_service import build_historical_export_status
from services.processing_run_service import ProcessingRunResult, ProcessingRunState
from services.review_session_service import ReviewSessionExportResult, ReviewSessionState
from services.trusted_profile_service import TrustedProfileSummary


def to_upload_response(upload: StoredUpload) -> SourceUploadResponse:
    """Build the API response for one uploaded source document."""
    return SourceUploadResponse(
        upload_id=upload.upload_id,
        original_filename=upload.original_filename,
        content_type=upload.content_type,
        file_size_bytes=upload.file_size_bytes,
        storage_ref=upload.storage_ref,
    )


def to_processing_run_response(result: ProcessingRunResult) -> ProcessingRunResponse:
    """Build the API response returned immediately after processing run creation."""
    historical_export_status = build_historical_export_status(result.profile_snapshot)
    return ProcessingRunResponse(
        processing_run_id=result.processing_run.processing_run_id,
        source_document_id=result.source_document.source_document_id,
        profile_snapshot_id=result.profile_snapshot.profile_snapshot_id,
        trusted_profile_id=result.trusted_profile.trusted_profile_id,
        trusted_profile_name=result.trusted_profile.profile_name,
        status=result.processing_run.status,
        aggregate_blockers=list(result.processing_run.aggregate_blockers),
        record_count=len(result.run_records),
        created_at=result.processing_run.created_at,
        historical_export_status=HistoricalExportStatusResponse(
            status_code=historical_export_status.status_code,
            is_reproducible=historical_export_status.is_reproducible,
            detail=historical_export_status.detail,
        ),
    )


def to_processing_run_detail_response(state: ProcessingRunState) -> ProcessingRunDetailResponse:
    """Build the API response for immutable run retrieval."""
    return ProcessingRunDetailResponse(
        processing_run_id=state.processing_run.processing_run_id,
        source_document_id=state.source_document.source_document_id,
        profile_snapshot_id=state.profile_snapshot.profile_snapshot_id,
        trusted_profile_id=state.trusted_profile.trusted_profile_id if state.trusted_profile else None,
        trusted_profile_name=state.trusted_profile.profile_name if state.trusted_profile else None,
        status=state.processing_run.status,
        aggregate_blockers=list(state.processing_run.aggregate_blockers),
        record_count=len(state.run_records),
        created_at=state.processing_run.created_at,
        historical_export_status=HistoricalExportStatusResponse(
            status_code=state.historical_export_status.status_code,
            is_reproducible=state.historical_export_status.is_reproducible,
            detail=state.historical_export_status.detail,
        ),
        run_records=[
            RunRecordResponse(
                run_record_id=run_record.run_record_id,
                record_key=run_record.record_key,
                record_index=run_record.record_index,
                canonical_record=run_record.canonical_record,
                source_page=run_record.source_page,
                source_line_text=run_record.source_line_text,
                created_at=run_record.created_at,
            )
            for run_record in state.run_records
        ],
    )


def to_review_session_response(state: ReviewSessionState) -> ReviewSessionResponse:
    """Build the API response for review-session open/fetch/edit operations."""
    return ReviewSessionResponse(
        review_session_id=state.review_session.review_session_id,
        processing_run_id=state.processing_run.processing_run_id,
        current_revision=state.review_session.current_revision,
        session_revision=state.session_revision,
        blocking_issues=list(state.blocking_issues),
        historical_export_status=HistoricalExportStatusResponse(
            status_code=state.historical_export_status.status_code,
            is_reproducible=state.historical_export_status.is_reproducible,
            detail=state.historical_export_status.detail,
        ),
        records=[ReviewRecordResponse(**asdict(record)) for record in state.records],
    )


def to_export_artifact_response(result: ReviewSessionExportResult) -> ExportArtifactResponse:
    """Build the API response for exact-revision export creation."""
    artifact = result.export_artifact
    return ExportArtifactResponse(
        export_artifact_id=artifact.export_artifact_id,
        processing_run_id=artifact.processing_run_id,
        review_session_id=artifact.review_session_id,
        session_revision=artifact.session_revision,
        artifact_kind=artifact.artifact_kind,
        template_artifact_id=artifact.template_artifact_id,
        file_hash=artifact.file_hash,
        created_at=artifact.created_at,
        download_url=f"/api/exports/{artifact.export_artifact_id}/download",
    )


def to_trusted_profile_response(profile: TrustedProfileSummary) -> TrustedProfileResponse:
    """Build the API response for one read-only trusted profile."""
    return TrustedProfileResponse(
        trusted_profile_id=profile.trusted_profile_id,
        profile_name=profile.profile_name,
        display_name=profile.display_name,
        description=profile.description,
        version_label=profile.version_label,
        template_filename=profile.template_filename,
        is_active_profile=profile.is_active_profile,
    )
