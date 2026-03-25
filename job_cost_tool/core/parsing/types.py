"""Shared types for PDF parsing components."""

from typing import Optional, TypedDict


class PDFPageData(TypedDict):
    """Text extracted from a single PDF page."""

    page_number: int
    text: str


class TokenizationResult(TypedDict):
    """Structured raw fields extracted from a logical detail line."""

    transaction_type: Optional[str]
    raw_description: str
    cost: Optional[float]
    hours: Optional[float]
    hour_type: Optional[str]
    union_code: Optional[str]
    labor_class_raw: Optional[str]
    vendor_id_raw: Optional[str]
    vendor_name: Optional[str]
    employee_id: Optional[str]
    employee_name: Optional[str]
    equipment_description: Optional[str]
    warnings: list[str]
    line_family: str
    has_meaningful_fields: bool
    parsed_field_count: int
