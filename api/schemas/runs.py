"""Processing-run API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    is_archived: bool
    archived_at: datetime | None = None
    origin_profile_display_name: str | None = None
    origin_profile_source_kind: str | None = None
    current_revision: int
    export_count: int
    last_exported_at: datetime | None = None
    historical_export_status: HistoricalExportStatusResponse


class ProcessingRunDetailResponse(ProcessingRunResponse):
    """Immutable processing-run detail response including ordered run records."""

    run_records: list[RunRecordResponse]


class ProcessingRunListResponse(ApiModel):
    """List response for the run-library workspace."""

    runs: list[ProcessingRunResponse]


class ProcessingRunReopenRequest(ApiModel):
    """Request body for loading a stored run in one of the supported reopen modes."""

    mode: Literal["latest_reviewed", "original_processed"]
    continue_from_original: bool = False
    expected_current_revision: int | None = Field(default=None, ge=0)


class ProcessingRunReprocessRequest(ApiModel):
    """Request body for reprocessing a saved run source with a selected trusted profile."""

    trusted_profile_name: str = Field(min_length=1)
