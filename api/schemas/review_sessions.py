"""Review-session and overlay-edit API contracts."""

from __future__ import annotations

from pydantic import Field

from api.schemas.common import ApiModel, HistoricalExportStatusResponse, ReviewRecordResponse


class ReviewEditFields(ApiModel):
    """Allowed record-level review edit fields for one overlay delta."""

    recap_labor_classification: str | None = None
    equipment_category: str | None = None
    vendor_name_normalized: str | None = None
    is_omitted: bool | None = None


class ReviewEditDelta(ApiModel):
    """One append-only overlay delta addressed by run-scoped record key."""

    record_key: str = Field(min_length=1)
    changed_fields: ReviewEditFields


class AppendReviewEditsRequest(ApiModel):
    """Request body for appending one accepted review-edit batch."""

    expected_current_revision: int | None = Field(default=None, ge=0)
    edits: list[ReviewEditDelta] = Field(min_length=1)


class ReviewSessionResponse(ApiModel):
    """Effective review-session response at one exact revision."""

    review_session_id: str
    processing_run_id: str
    current_revision: int
    session_revision: int
    blocking_issues: list[str]
    labor_classification_options: list[str]
    equipment_classification_options: list[str]
    historical_export_status: HistoricalExportStatusResponse
    records: list[ReviewRecordResponse]
