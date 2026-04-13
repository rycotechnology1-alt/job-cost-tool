"""Service contract for converting job cost report PDFs into raw Record objects."""

from __future__ import annotations

from typing import List

from core.models.record import Record


def parse_pdf(file_path: str) -> List[Record]:
    """
    Parse a text-based PDF job cost report into raw structured records.

    Responsibilities of this layer:
    - Read the PDF input
    - Detect report sections and detail lines
    - Convert raw report lines into Record objects
    - Preserve traceability fields such as raw description, source page,
      source line text, transaction type, employee/vendor raw fields when available

    This layer does NOT:
    - Apply business-rule normalization
    - Resolve unknown mappings
    - Validate recap readiness
    - Export to Excel
    """
    from core.parsing.pdf_reader import extract_pdf_pages
    from core.parsing.report_parser import parse_report_pages

    pages = extract_pdf_pages(file_path)
    return parse_report_pages(pages)
