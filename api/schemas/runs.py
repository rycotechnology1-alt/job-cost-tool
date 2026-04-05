"""Processing-run API contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.schemas.common import ApiModel, HistoricalExportStatusResponse, RunRecordResponse


class ProcessingRunCreateRequest(ApiModel):
    """Request body for starting one processing run from an uploaded source document."""

    upload_id: str = Field(min_length=1)
    trusted_profile_name: str = Field(min_length=1)


class ProcessingRunResponse(ApiModel):
    """Summary response returned after processing-run creation."""

    processing_run_id: str
    source_document_id: str
    source_document_filename: str
    profile_snapshot_id: str
    trusted_profile_id: str | None = None
    trusted_profile_name: str | None = None
    status: str
    aggregate_blockers: list[str]
    record_count: int
    created_at: datetime
    historical_export_status: HistoricalExportStatusResponse


class ProcessingRunDetailResponse(ProcessingRunResponse):
    """Immutable processing-run detail response including ordered run records."""

    run_records: list[RunRecordResponse]
