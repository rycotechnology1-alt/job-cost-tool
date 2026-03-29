"""Canonical normalized record model for job cost line items."""

from dataclasses import dataclass, field
from typing import List, Optional


LABOR = "labor"
EQUIPMENT = "equipment"
MATERIAL = "material"
SUBCONTRACTOR = "subcontractor"
PERMIT = "permit"
OTHER = "other"


@dataclass(slots=True)
class Record:
    """Canonical structured representation of one normalized line item.

    The model is intentionally format-agnostic so different source reports can
    map into the same internal shape before downstream validation and export
    steps.

    Raw traceability fields preserve source-specific context for auditability,
    review, and debugging. Normalized business fields hold the stable values
    that downstream logic should rely on.
    """

    # Normalized business fields used across the application.
    record_type: str
    phase_code: Optional[str]
    cost: Optional[float]
    hours: Optional[float]
    hour_type: Optional[str]
    union_code: Optional[str]
    labor_class_normalized: Optional[str]
    vendor_name: Optional[str]
    equipment_description: Optional[str]
    equipment_category: Optional[str]
    confidence: float

    # Raw source fields retained for traceability.
    raw_description: str
    labor_class_raw: Optional[str]

    # Additional raw source traceability metadata.
    job_number: Optional[str] = None
    job_name: Optional[str] = None
    transaction_type: Optional[str] = None
    phase_name_raw: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    vendor_id_raw: Optional[str] = None
    source_page: Optional[int] = None
    source_line_text: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    # Additional normalized recap-oriented fields derived after parsing.
    record_type_normalized: Optional[str] = None
    recap_labor_slot_id: Optional[str] = None
    recap_labor_classification: Optional[str] = None
    recap_equipment_slot_id: Optional[str] = None
    vendor_name_normalized: Optional[str] = None
    equipment_mapping_key: Optional[str] = None
    is_omitted: bool = False

    def __post_init__(self) -> None:
        """Validate model invariants after initialization."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

    def is_labor(self) -> bool:
        """Return True when the record represents labor."""
        return self.record_type == LABOR

    def is_equipment(self) -> bool:
        """Return True when the record represents equipment."""
        return self.record_type == EQUIPMENT

    def is_material(self) -> bool:
        """Return True when the record represents material."""
        return self.record_type == MATERIAL

    def has_blocking_warning(self) -> bool:
        """Return True when any warning is explicitly marked as blocking."""
        return any(warning.startswith("BLOCKING:") for warning in self.warnings)
