"""Service contract for validating normalized Record objects before recap export."""

from typing import List, Tuple

from job_cost_tool.core.models.record import Record


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
    raise NotImplementedError("Record validation has not been implemented yet.")
