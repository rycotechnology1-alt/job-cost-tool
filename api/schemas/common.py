"""Shared request/response schema pieces for the phase-1 API slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base API schema with strict extra-field rejection."""

    model_config = ConfigDict(extra="forbid")


class HistoricalExportStatusResponse(ApiModel):
    """Explicit historical-export posture for one processing run/session."""

    status_code: str
    is_reproducible: bool
    detail: str


class RunRecordResponse(ApiModel):
    """Immutable run-record payload returned by the processing-run API."""

    run_record_id: str
    record_key: str
    record_index: int
    canonical_record: dict[str, Any]
    source_page: int | None = None
    source_line_text: str | None = None
    created_at: datetime


class ReviewRecordResponse(ApiModel):
    """Effective review-record payload returned by review-session APIs."""

    record_type: str
    phase_code: str | None = None
    cost: float | None = None
    hours: float | None = None
    hour_type: str | None = None
    union_code: str | None = None
    labor_class_normalized: str | None = None
    vendor_name: str | None = None
    equipment_description: str | None = None
    equipment_category: str | None = None
    confidence: float
    raw_description: str
    labor_class_raw: str | None = None
    job_number: str | None = None
    job_name: str | None = None
    transaction_type: str | None = None
    phase_name_raw: str | None = None
    employee_id: str | None = None
    employee_name: str | None = None
    vendor_id_raw: str | None = None
    source_page: int | None = None
    source_line_text: str | None = None
    warnings: list[str]
    record_type_normalized: str | None = None
    recap_labor_slot_id: str | None = None
    recap_labor_classification: str | None = None
    recap_equipment_slot_id: str | None = None
    vendor_name_normalized: str | None = None
    equipment_mapping_key: str | None = None
    is_omitted: bool = False
