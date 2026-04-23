"""Validation orchestration for normalized job cost records."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, List, Sequence, Tuple

from core.models.record import Record
from core.validation.rules import get_record_blocking_issues, get_record_warnings

_MEDIUM_CONFIDENCE_WARNING = "Medium-confidence record should be reviewed before export."
_UNRESOLVED_WARNING_PHRASES = (
    "ambiguous",
    "not yet confidently classified",
    "did not begin with a recognized transaction marker",
)


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


def validate_review_records(
    base_records: Sequence[Record],
    records: Sequence[Record],
) -> Tuple[List[Record], List[str]]:
    """Validate review records after clearing warnings superseded by manual review overrides."""
    if len(base_records) != len(records):
        raise ValueError("base_records and records must have the same length for review validation.")

    review_ready_records = [
        _prepare_review_record_for_validation(base_record, record)
        for base_record, record in zip(base_records, records)
    ]
    return validate_records(list(review_ready_records))


def _format_record_reference(record: Record) -> str:
    """Build a human-readable reference for workflow-level blocking issues."""
    page_label = f"page {record.source_page}" if record.source_page is not None else "unknown page"
    phase_label = f"phase {record.phase_code}" if record.phase_code else "unknown phase"
    type_label = record.record_type_normalized or record.record_type or "unknown type"
    return f"Record on {page_label} ({phase_label}, {type_label})"


def _prepare_review_record_for_validation(base_record: Record, record: Record) -> Record:
    """Return one review record with superseded warnings removed before validation runs."""
    if record.is_omitted:
        return replace(record, warnings=[])

    warnings = [
        warning
        for warning in _strip_existing_blocking_warnings(record.warnings)
        if warning != _MEDIUM_CONFIDENCE_WARNING
    ]
    removed_resolved_warning = False

    if _has_manual_equipment_override(base_record, record) or _is_effectively_equipment_resolved(record):
        warnings, removed = _remove_matching_warnings(warnings, _is_equipment_resolution_warning)
        removed_resolved_warning = removed_resolved_warning or removed

    if _has_manual_labor_override(base_record, record) or _is_effectively_labor_resolved(record):
        warnings, removed = _remove_matching_warnings(warnings, _is_labor_resolution_warning)
        removed_resolved_warning = removed_resolved_warning or removed

    if _has_manual_vendor_override(base_record, record) or _is_effectively_vendor_resolved(record):
        warnings, removed = _remove_matching_warnings(warnings, _is_vendor_resolution_warning)
        removed_resolved_warning = removed_resolved_warning or removed

    adjusted_confidence = record.confidence
    if (
        removed_resolved_warning
        and 0.3 < adjusted_confidence < 0.9
        and not any(_warning_supports_reduced_confidence(warning) for warning in warnings)
    ):
        adjusted_confidence = 0.9

    return replace(record, warnings=warnings, confidence=adjusted_confidence)


def _strip_existing_blocking_warnings(warnings: List[str]) -> List[str]:
    """Remove prior blocking markers so validation can be safely re-run."""
    return [warning for warning in warnings if not warning.startswith("BLOCKING:")]


def _has_manual_equipment_override(base_record: Record, record: Record) -> bool:
    """Return True when review edited the equipment classification away from the canonical run value."""
    return bool(
        record.equipment_category
        and (
            record.equipment_category != base_record.equipment_category
            or record.recap_equipment_slot_id != base_record.recap_equipment_slot_id
        )
    )


def _has_manual_labor_override(base_record: Record, record: Record) -> bool:
    """Return True when review edited the labor classification away from the canonical run value."""
    return bool(
        record.recap_labor_classification
        and (
            record.recap_labor_classification != base_record.recap_labor_classification
            or record.recap_labor_slot_id != base_record.recap_labor_slot_id
        )
    )


def _has_manual_vendor_override(base_record: Record, record: Record) -> bool:
    """Return True when review edited the effective vendor away from the canonical run value."""
    return bool(
        record.vendor_name_normalized
        and record.vendor_name_normalized != base_record.vendor_name_normalized
    )


def _is_effectively_equipment_resolved(record: Record) -> bool:
    """Return True when the effective record already has a resolved equipment outcome."""
    return bool(record.equipment_category and str(record.equipment_category).strip())


def _is_effectively_labor_resolved(record: Record) -> bool:
    """Return True when the effective record already has a resolved labor outcome."""
    return bool(record.recap_labor_classification and str(record.recap_labor_classification).strip())


def _is_effectively_vendor_resolved(record: Record) -> bool:
    """Return True when the effective record already has a resolved vendor outcome."""
    normalized_vendor_name = str(record.vendor_name_normalized or "").strip()
    raw_vendor_name = str(record.vendor_name or "").strip()
    return bool(normalized_vendor_name and normalized_vendor_name.casefold() != raw_vendor_name.casefold())


def _remove_matching_warnings(
    warnings: List[str],
    predicate: Callable[[str], bool],
) -> tuple[List[str], bool]:
    """Return warnings with predicate matches removed plus whether anything changed."""
    filtered = [warning for warning in warnings if not predicate(warning)]
    return filtered, len(filtered) != len(warnings)


def _is_equipment_resolution_warning(warning: str) -> bool:
    """Return True when a warning is superseded by a manual equipment-category edit."""
    normalized_warning = warning.casefold()
    return (
        "pr equipment detail line was recognized but equipment description was not parsed cleanly." in normalized_warning
        or
        "equipment record is missing a raw equipment description for recap mapping." in normalized_warning
        or "equipment description did not match a configured target equipment category." in normalized_warning
        or "equipment record mapped to a category that is not active for the current profile." in normalized_warning
        or "equipment raw mapping '" in normalized_warning
        or "equipment raw value is not mapped." in normalized_warning
    )


def _is_labor_resolution_warning(warning: str) -> bool:
    """Return True when a warning is superseded by a manual labor-classification edit."""
    normalized_warning = warning.casefold()
    return (
        "pr labor detail line was recognized but labor class was not parsed cleanly." in normalized_warning
        or
        "labor record is missing a raw labor class for recap mapping." in normalized_warning
        or (
            "labor raw value" in normalized_warning
            and (
                "target recap labor classification" in normalized_warning
                or "current profile" in normalized_warning
                or "not valid for the active profile" in normalized_warning
                or "is not mapped." in normalized_warning
            )
        )
    )


def _is_vendor_resolution_warning(warning: str) -> bool:
    """Return True when a warning is superseded by a manual vendor correction."""
    normalized_warning = warning.casefold()
    return (
        "material-oriented record is missing a vendor name for recap preparation." in normalized_warning
        or "vendor normalization was uncertain and the raw vendor name was preserved." in normalized_warning
    )


def _warning_supports_reduced_confidence(warning: str) -> bool:
    """Return True when a remaining warning still justifies medium-confidence treatment."""
    normalized_warning = warning.casefold()
    return (
        any(phrase in normalized_warning for phrase in _UNRESOLVED_WARNING_PHRASES)
        or _is_equipment_resolution_warning(warning)
        or _is_labor_resolution_warning(warning)
        or _is_vendor_resolution_warning(warning)
    )


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
