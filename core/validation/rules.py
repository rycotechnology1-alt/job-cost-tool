"""Reusable validation rules for normalized job cost records."""

from __future__ import annotations

from typing import List

from core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER, PROJECT_MANAGEMENT, Record

_BLOCKING_WARNING_PHRASES = (
    "ambiguous",
    "not yet confidently classified",
    "did not begin with a recognized transaction marker",
)
_ALLOWED_LABOR_HOUR_TYPES = {"ST", "OT", "DT"}


def get_record_warnings(record: Record) -> List[str]:
    """Return additional non-blocking validation warnings for a normalized record."""
    warnings: List[str] = []

    if record.is_omitted:
        return warnings

    if not get_record_blocking_issues(record) and 0.3 < record.confidence < 0.9:
        warnings.append("Medium-confidence record should be reviewed before export.")

    return _dedupe_messages(warnings)


def get_record_blocking_issues(record: Record) -> List[str]:
    """Return blocking issues for a normalized record."""
    if record.is_omitted:
        return []

    issues: List[str] = []
    normalized_family = record.record_type_normalized or record.record_type

    issues.extend(_get_existing_blocking_warnings(record))

    if normalized_family in {None, "", OTHER}:
        issues.append("Normalized record family is missing or unresolved.")

    if record.confidence <= 0.3:
        issues.append("Record confidence is too low for safe export.")

    if _has_unresolved_state_warning(record):
        issues.append("Record still contains unresolved parsing or normalization ambiguity.")

    if normalized_family == LABOR:
        if not record.recap_labor_classification:
            issues.append("Recap labor classification is missing.")
        if record.hours is None:
            issues.append("Labor hours are missing for export.")
        hour_type = (record.hour_type or "").strip().upper()
        if not hour_type:
            issues.append("Labor hour type is missing for export.")
        elif hour_type not in _ALLOWED_LABOR_HOUR_TYPES:
            issues.append(f"Unsupported labor hour type '{record.hour_type}'.")
    elif normalized_family == EQUIPMENT:
        if not record.equipment_category:
            issues.append("Equipment recap category is missing.")
    elif normalized_family == MATERIAL:
        if not (record.vendor_name_normalized or record.vendor_name):
            issues.append("Material/vendor identity is missing for recap preparation.")
    elif normalized_family == PROJECT_MANAGEMENT:
        if record.cost is None:
            issues.append("Project management amount is missing for export.")

    return _dedupe_messages(issues)


def _get_existing_blocking_warnings(record: Record) -> List[str]:
    """Extract blocking issues already recorded on the record."""
    issues: List[str] = []
    for warning in record.warnings:
        if warning.startswith("BLOCKING:"):
            trimmed_warning = warning[len("BLOCKING:") :].strip()
            issues.append(trimmed_warning or warning)
    return issues


def _has_unresolved_state_warning(record: Record) -> bool:
    """Return True when existing warnings indicate unresolved state."""
    normalized_warnings = [warning.casefold() for warning in record.warnings]
    return any(phrase in warning for warning in normalized_warnings for phrase in _BLOCKING_WARNING_PHRASES)


def _dedupe_messages(messages: List[str]) -> List[str]:
    """Return messages with duplicates removed while preserving order."""
    unique_messages: List[str] = []
    seen: set[str] = set()
    for message in messages:
        if message not in seen:
            unique_messages.append(message)
            seen.add(message)
    return unique_messages
