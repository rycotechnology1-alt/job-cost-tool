"""Service contract for validating normalized Record objects before recap export."""

from typing import List, Tuple

from core.models.record import Record
from core.validation.validator import validate_records as validate_record_list
from core.validation.validator import validate_review_records as validate_review_record_list


def validate_records(records: List[Record]) -> Tuple[List[Record], List[str]]:
    """
    Validates normalized records and identifies blocking issues before export.

    Returns:
    - updated records (including warnings where applicable)
    - blocking issues as a list of human-readable strings

    Responsibilities of this layer:
    - Identify missing required normalized values
    - Flag unknown or low-confidence records
    - Detect unresolved items that must block export

    This layer does NOT:
    - Parse PDF files
    - Perform user interaction
    - Export to Excel
    """
    return validate_record_list(records)


def validate_review_records(
    base_records: List[Record],
    records: List[Record],
) -> Tuple[List[Record], List[str]]:
    """Validate review records after resolving warnings superseded by manual edits."""
    return validate_review_record_list(base_records, records)
