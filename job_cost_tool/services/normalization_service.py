"""Service contract for applying config-driven normalization to parsed Record objects."""

from typing import List

from job_cost_tool.core.models.record import Record


def normalize_records(records: List[Record]) -> List[Record]:
    """
    Applies business rules and config-driven mappings to parsed records.

    Responsibilities of this layer:
    - Normalize labor classes
    - Normalize equipment categories
    - Normalize vendor names
    - Interpret phase mappings
    - Prepare records for recap-oriented validation

    This layer does NOT:
    - Parse PDF files
    - Ask users for corrections
    - Write to Excel
    """
    raise NotImplementedError("Record normalization has not been implemented yet.")
