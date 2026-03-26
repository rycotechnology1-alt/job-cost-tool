"""Service contract for exporting reviewed records into the recap workbook."""

from __future__ import annotations

from typing import List

from job_cost_tool.core.export.excel_exporter import export_to_excel
from job_cost_tool.core.export.recap_mapper import build_recap_payload
from job_cost_tool.core.models.record import Record
from job_cost_tool.services.validation_service import validate_records


def export_records_to_recap(records: List[Record], template_path: str, output_path: str) -> None:
    """Validate export readiness, build a recap payload, and write the recap workbook."""
    validated_records, blocking_issues = validate_records(records)
    if blocking_issues:
        issue_list = "\n".join(f"- {issue}" for issue in blocking_issues)
        raise ValueError(f"Export blocked until all blocking issues are resolved:\n{issue_list}")

    recap_payload = build_recap_payload(validated_records)
    export_to_excel(template_path=template_path, output_path=output_path, recap_payload=recap_payload)
