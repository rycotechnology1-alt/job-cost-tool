"""Validation orchestration for normalized job cost records."""

from __future__ import annotations

from dataclasses import replace
from typing import List, Tuple

from core.models.record import Record
from core.validation.rules import get_record_blocking_issues, get_record_warnings


def validate_records(records: List[Record]) -> Tuple[List[Record], List[str]]:
    """Validate normalized records and return updated records plus aggregate blocking issues."""
    validated_records: List[Record] = []
    aggregate_blocking_issues: List[str] = []

    for record in records:
        base_warnings = _strip_existing_blocking_warnings(record.warnings)
        evaluation_record = replace(record, warnings=base_warnings)

        blocking_issues = get_record_blocking_issues(evaluation_record)
        validation_warnings = get_record_warnings(evaluation_record)

        combined_warnings = list(base_warnings)
        for warning in validation_warnings:
            _append_warning(combined_warnings, warning)
        for issue in blocking_issues:
            _append_warning(combined_warnings, f"BLOCKING: {issue}")
            aggregate_blocking_issues.append(f"{_format_record_reference(record)}: {issue}")

        validated_records.append(
            replace(
                record,
                warnings=_dedupe_messages(combined_warnings),
            )
        )

    return validated_records, _dedupe_messages(aggregate_blocking_issues)


def _format_record_reference(record: Record) -> str:
    """Build a human-readable reference for workflow-level blocking issues."""
    page_label = f"page {record.source_page}" if record.source_page is not None else "unknown page"
    phase_label = f"phase {record.phase_code}" if record.phase_code else "unknown phase"
    type_label = record.record_type_normalized or record.record_type or "unknown type"
    return f"Record on {page_label} ({phase_label}, {type_label})"


def _strip_existing_blocking_warnings(warnings: List[str]) -> List[str]:
    """Remove prior blocking markers so validation can be safely re-run."""
    return [warning for warning in warnings if not warning.startswith("BLOCKING:")]


def _append_warning(warnings: List[str], warning: str) -> None:
    """Append a warning only when it is not already present."""
    if warning not in warnings:
        warnings.append(warning)


def _dedupe_messages(messages: List[str]) -> List[str]:
    """Return messages with duplicates removed while preserving order."""
    unique_messages: List[str] = []
    seen: set[str] = set()
    for message in messages:
        if message not in seen:
            unique_messages.append(message)
            seen.add(message)
    return unique_messages
