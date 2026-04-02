"""Material and vendor-oriented normalization helpers for parsed job cost records."""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from typing import Any, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.models.record import MATERIAL, Record
from job_cost_tool.core.phase_codes import canonicalize_phase_code

_EMPLOYEE_EXPENSE_VENDOR = "Employee Expense"
_REIMBURSEMENT_PATTERN = re.compile(r"\bjob\s+reimb(?:urse(?:ment)?)?\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _get_vendor_normalization() -> dict[str, Any]:
    """Return the cached vendor normalization config."""
    return ConfigLoader().get_vendor_normalization()


def normalize_material_record(record: Record) -> Record:
    """Apply vendor/material normalization foundations to a parsed record."""
    warnings = list(record.warnings)

    if _is_employee_reimbursement(record):
        warnings = [warning for warning in warnings if "pr detail line family is ambiguous" not in warning.casefold()]
        return replace(
            record,
            record_type_normalized=MATERIAL,
            vendor_name_normalized=_EMPLOYEE_EXPENSE_VENDOR,
            warnings=_dedupe_warnings(warnings),
            confidence=max(record.confidence, 0.6),
        )

    vendor_name_normalized = _normalize_vendor_name(record.vendor_name)

    if record.vendor_name is None:
        warnings.append("Material-oriented record is missing a vendor name for recap preparation.")
    elif vendor_name_normalized is None:
        warnings.append("Vendor normalization was uncertain and the raw vendor name was preserved.")
        vendor_name_normalized = record.vendor_name

    return replace(
        record,
        record_type_normalized=MATERIAL,
        vendor_name_normalized=vendor_name_normalized,
        warnings=_dedupe_warnings(warnings),
        confidence=_reduce_confidence(record.confidence, record.vendor_name is None),
    )


def _is_employee_reimbursement(record: Record) -> bool:
    """Return True for narrow phase-50 employee reimbursement lines."""
    if canonicalize_phase_code(record.phase_code) != "50":
        return False
    searchable_text = " ".join(
        part for part in (record.raw_description, record.source_line_text) if part
    )
    return bool(_REIMBURSEMENT_PATTERN.search(searchable_text))


def _normalize_vendor_name(vendor_name: Optional[str]) -> Optional[str]:
    """Normalize a vendor name using case-insensitive config-driven mappings."""
    if vendor_name is None:
        return None

    normalized_map = {
        str(key).casefold(): str(value).strip()
        for key, value in _get_vendor_normalization().items()
        if str(key).strip()
    }
    return normalized_map.get(vendor_name.casefold(), vendor_name)


def _reduce_confidence(confidence: float, is_uncertain: bool) -> float:
    """Lower confidence slightly when normalization remains uncertain."""
    if not is_uncertain:
        return confidence
    return min(confidence, 0.6)


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    """Return warnings with duplicates removed while preserving order."""
    unique_warnings: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning not in seen:
            unique_warnings.append(warning)
            seen.add(warning)
    return unique_warnings
