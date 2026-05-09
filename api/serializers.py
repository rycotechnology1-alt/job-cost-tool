"""Response-shaping helpers that keep FastAPI routes thin."""

from __future__ import annotations

from dataclasses import asdict

from api.schemas.common import HistoricalExportStatusResponse, ReviewRecordResponse, RunRecordResponse
from api.schemas.exports import ExportArtifactResponse
from api.schemas.profile_authoring import (
    ClassificationSlotRow,
    DefaultOmitRuleRow,
    DeferredDomainsResponse,
    DraftEditorStateResponse,
    EquipmentMappingRow,
    EquipmentRateRow,
    ExportSettingsResponse,
    LaborMappingRow,
    LaborMinimumHoursRuleResponse,
    LaborRateRow,
    PhaseOptionRow,
    ProfileVersionSummaryResponse,
    PublishedProfileDetailResponse,
    TemplateMetadataResponse,
    TemplateRowDefinitionResponse,
)
from api.schemas.runs import ProcessingRunDetailResponse, ProcessingRunResponse
from api.schemas.review_sessions import ReviewSessionResponse
from api.schemas.trusted_profiles import TrustedProfileResponse
from api.schemas.uploads import SourceUploadResponse
from infrastructure.storage import StoredUpload
from services.lineage_service import build_historical_export_status
from services.profile_authoring_service import DraftEditorState, PublishedProfileDetail
from services.processing_run_service import ProcessingRunResult, ProcessingRunState, ProcessingRunSummary
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
        expires_at=upload.expires_at,
    )


def to_processing_run_response(result: ProcessingRunResult) -> ProcessingRunResponse:
    """Build the API response returned immediately after processing run creation."""
    historical_export_status = build_historical_export_status(result.profile_snapshot)
    return ProcessingRunResponse(
        processing_run_id=result.processing_run.processing_run_id,
        source_document_id=result.source_document.source_document_id,
        source_document_filename=result.source_document.original_filename,
        profile_snapshot_id=result.profile_snapshot.profile_snapshot_id,
        trusted_profile_id=result.trusted_profile.trusted_profile_id,
        trusted_profile_name=result.trusted_profile.profile_name,
        status=result.processing_run.status,
        aggregate_blockers=list(result.processing_run.aggregate_blockers),
        record_count=len(result.run_records),
        created_at=result.processing_run.created_at,
        is_archived=result.processing_run.archived_at is not None,
        archived_at=result.processing_run.archived_at,
        origin_profile_display_name=result.trusted_profile.display_name,
        origin_profile_source_kind=result.trusted_profile.source_kind,
        current_revision=0,
        export_count=0,
        last_exported_at=None,
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
        source_document_filename=state.source_document.original_filename,
        profile_snapshot_id=state.profile_snapshot.profile_snapshot_id,
        trusted_profile_id=state.trusted_profile.trusted_profile_id if state.trusted_profile else None,
        trusted_profile_name=state.trusted_profile.profile_name if state.trusted_profile else None,
        status=state.processing_run.status,
        aggregate_blockers=list(state.processing_run.aggregate_blockers),
        record_count=len(state.run_records),
        created_at=state.processing_run.created_at,
        is_archived=state.processing_run.archived_at is not None,
        archived_at=state.processing_run.archived_at,
        origin_profile_display_name=state.trusted_profile.display_name if state.trusted_profile else None,
        origin_profile_source_kind=state.trusted_profile.source_kind if state.trusted_profile else None,
        current_revision=state.current_revision,
        export_count=state.export_count,
        last_exported_at=state.last_exported_at,
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


def to_processing_run_summary_response(summary: ProcessingRunSummary) -> ProcessingRunResponse:
    """Build the API response for one run-library summary row."""
    return ProcessingRunResponse(
        processing_run_id=summary.processing_run.processing_run_id,
        source_document_id=summary.source_document.source_document_id,
        source_document_filename=summary.source_document.original_filename,
        profile_snapshot_id=summary.profile_snapshot.profile_snapshot_id,
        trusted_profile_id=summary.trusted_profile.trusted_profile_id if summary.trusted_profile else None,
        trusted_profile_name=summary.trusted_profile.profile_name if summary.trusted_profile else None,
        status=summary.processing_run.status,
        aggregate_blockers=list(summary.processing_run.aggregate_blockers),
        record_count=summary.record_count,
        created_at=summary.processing_run.created_at,
        is_archived=summary.processing_run.archived_at is not None,
        archived_at=summary.processing_run.archived_at,
        origin_profile_display_name=summary.trusted_profile.display_name if summary.trusted_profile else None,
        origin_profile_source_kind=summary.trusted_profile.source_kind if summary.trusted_profile else None,
        current_revision=summary.current_revision,
        export_count=summary.export_count,
        last_exported_at=summary.last_exported_at,
        historical_export_status=HistoricalExportStatusResponse(
            status_code=summary.historical_export_status.status_code,
            is_reproducible=summary.historical_export_status.is_reproducible,
            detail=summary.historical_export_status.detail,
        ),
    )


def to_review_session_response(state: ReviewSessionState) -> ReviewSessionResponse:
    """Build the API response for review-session open/fetch/edit operations."""
    return ReviewSessionResponse(
        review_session_id=state.review_session.review_session_id,
        processing_run_id=state.processing_run.processing_run_id,
        current_revision=state.review_session.current_revision,
        session_revision=state.session_revision,
        blocking_issues=list(state.blocking_issues),
        labor_classification_options=list(state.labor_classification_options),
        labor_hour_type_options=list(state.labor_hour_type_options),
        equipment_classification_options=list(state.equipment_classification_options),
        historical_export_status=HistoricalExportStatusResponse(
            status_code=state.historical_export_status.status_code,
            is_reproducible=state.historical_export_status.is_reproducible,
            detail=state.historical_export_status.detail,
        ),
        effective_source_mode=state.effective_source_mode,
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
        source_kind=profile.source_kind,
        current_published_version_number=profile.current_published_version_number,
        has_open_draft=profile.has_open_draft,
        is_active_profile=profile.is_active_profile,
        archived_at=profile.archived_at,
    )


def to_published_profile_detail_response(detail: PublishedProfileDetail) -> PublishedProfileDetailResponse:
    """Build the API response for one read-only published profile detail view."""
    return PublishedProfileDetailResponse(
        trusted_profile_id=detail.trusted_profile_id,
        profile_name=detail.profile_name,
        display_name=detail.display_name,
        description=detail.description,
        version_label=detail.version_label,
        current_published_version=ProfileVersionSummaryResponse(
            trusted_profile_version_id=detail.current_published_version_id,
            version_number=detail.current_published_version_number,
            content_hash=detail.current_published_content_hash,
            template_artifact_ref=detail.template_artifact_ref,
            template_file_hash=detail.template_file_hash,
            template_filename=detail.template_filename,
        ),
        template_metadata=_to_template_metadata_response(detail.template_metadata),
        labor_active_slot_count=detail.labor_active_slot_count,
        labor_inactive_slot_count=detail.labor_inactive_slot_count,
        equipment_active_slot_count=detail.equipment_active_slot_count,
        equipment_inactive_slot_count=detail.equipment_inactive_slot_count,
        open_draft_id=detail.open_draft_id,
        deferred_domains=_to_deferred_domains_response(detail.deferred_domains),
    )


def to_draft_editor_state_response(state: DraftEditorState) -> DraftEditorStateResponse:
    """Build the API response for one trusted-profile draft editor state."""
    return DraftEditorStateResponse(
        trusted_profile_draft_id=state.trusted_profile_draft_id,
        trusted_profile_id=state.trusted_profile_id,
        profile_name=state.profile_name,
        display_name=state.display_name,
        description=state.description,
        version_label=state.version_label,
        current_published_version=ProfileVersionSummaryResponse(
            trusted_profile_version_id=state.current_published_version_id,
            version_number=state.current_published_version_number,
            content_hash=state.current_published_content_hash,
            template_artifact_ref=state.template_artifact_ref,
            template_file_hash=state.template_file_hash,
            template_filename=state.template_filename,
        ),
        base_trusted_profile_version_id=state.base_trusted_profile_version_id,
        draft_revision=state.draft_revision,
        draft_content_hash=state.draft_content_hash,
        template_metadata=_to_template_metadata_response(state.template_metadata),
        labor_active_slot_count=state.labor_active_slot_count,
        labor_inactive_slot_count=state.labor_inactive_slot_count,
        equipment_active_slot_count=state.equipment_active_slot_count,
        equipment_inactive_slot_count=state.equipment_inactive_slot_count,
        default_omit_rules=[DefaultOmitRuleRow(**row) for row in state.default_omit_rules],
        default_omit_phase_options=[PhaseOptionRow(**row) for row in state.default_omit_phase_options],
        labor_mappings=[LaborMappingRow(**row) for row in state.labor_mappings],
        equipment_mappings=[EquipmentMappingRow(**row) for row in state.equipment_mappings],
        labor_slots=[ClassificationSlotRow(**row) for row in state.labor_slots],
        equipment_slots=[ClassificationSlotRow(**row) for row in state.equipment_slots],
        export_settings=_to_export_settings_response(state.export_settings),
        labor_rates=[LaborRateRow(**row) for row in state.labor_rates],
        equipment_rates=[EquipmentRateRow(**row) for row in state.equipment_rates],
        deferred_domains=_to_deferred_domains_response(state.deferred_domains),
        validation_errors=list(state.validation_errors),
    )


def _to_deferred_domains_response(payload: dict) -> DeferredDomainsResponse:
    """Build the read-only deferred-domain payload."""
    return DeferredDomainsResponse(
        vendor_normalization=dict(payload.get("vendor_normalization", {})),
        phase_mapping=dict(payload.get("phase_mapping", {})),
        input_model=dict(payload.get("input_model", {})),
        recap_template_map=dict(payload.get("recap_template_map", {})),
    )


def _to_template_metadata_response(payload: dict) -> TemplateMetadataResponse:
    """Build the read-only template metadata payload."""
    labor_rows = payload.get("labor_rows", []) if isinstance(payload.get("labor_rows"), list) else []
    equipment_rows = payload.get("equipment_rows", []) if isinstance(payload.get("equipment_rows"), list) else []
    return TemplateMetadataResponse(
        template_id=str(payload.get("template_id") or ""),
        display_label=str(payload.get("display_label") or ""),
        template_filename=str(payload.get("template_filename") or "") or None,
        template_artifact_ref=str(payload.get("template_artifact_ref") or "") or None,
        template_file_hash=str(payload.get("template_file_hash") or "") or None,
        labor_active_slot_capacity=int(payload.get("labor_active_slot_capacity") or 0),
        equipment_active_slot_capacity=int(payload.get("equipment_active_slot_capacity") or 0),
        labor_rows=[
            TemplateRowDefinitionResponse(
                row_id=str(row.get("row_id") or ""),
                template_label=str(row.get("template_label") or ""),
                mapping=dict(row.get("mapping", {})) if isinstance(row.get("mapping"), dict) else {},
            )
            for row in labor_rows
            if isinstance(row, dict)
        ],
        equipment_rows=[
            TemplateRowDefinitionResponse(
                row_id=str(row.get("row_id") or ""),
                template_label=str(row.get("template_label") or ""),
                mapping=dict(row.get("mapping", {})) if isinstance(row.get("mapping"), dict) else {},
            )
            for row in equipment_rows
            if isinstance(row, dict)
        ],
        export_behaviors=dict(payload.get("export_behaviors", {})) if isinstance(payload.get("export_behaviors"), dict) else {},
    )


def _to_export_settings_response(payload: dict) -> ExportSettingsResponse:
    """Build the export-settings payload."""
    labor_minimum_hours = payload.get("labor_minimum_hours", {}) if isinstance(payload.get("labor_minimum_hours"), dict) else {}
    return ExportSettingsResponse(
        labor_minimum_hours=LaborMinimumHoursRuleResponse(
            enabled=bool(labor_minimum_hours.get("enabled")),
            threshold_hours=str(labor_minimum_hours.get("threshold_hours") or ""),
            minimum_hours=str(labor_minimum_hours.get("minimum_hours") or ""),
        )
    )
