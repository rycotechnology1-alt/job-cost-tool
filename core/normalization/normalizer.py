"""Orchestration layer for config-driven record normalization."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import List, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER, SUBCONTRACTOR, Record
from job_cost_tool.core.normalization.equipment_normalizer import normalize_equipment_record
from job_cost_tool.core.normalization.labor_normalizer import normalize_labor_record
from job_cost_tool.core.normalization.material_normalizer import normalize_material_record
from job_cost_tool.core.phase_codes import canonicalize_phase_code


@lru_cache(maxsize=1)
def _get_phase_mapping() -> dict[str, str]:
    """Return the configured phase-to-record-family mapping."""
    phase_mapping = ConfigLoader().get_phase_mapping()
    return {
        canonical_phase_code: str(value)
        for key, value in phase_mapping.items()
        if (canonical_phase_code := canonicalize_phase_code(key))
    }


def normalize_records(records: List[Record]) -> List[Record]:
    """Apply config-driven normalization and business rules to parsed records."""
    return [_normalize_record(record) for record in records]


def _normalize_record(record: Record) -> Record:
    """Normalize a single parsed record according to its business family."""
    warnings = list(record.warnings)
    normalized_family = _determine_normalized_family(record)

    if normalized_family != record.record_type and record.record_type != OTHER:
        warnings.append(
            f"Phase-based normalization treated this record as '{normalized_family}' instead of raw type '{record.record_type}'."
        )

    prepared_record = replace(
        record,
        record_type_normalized=normalized_family,
        warnings=_dedupe_warnings(warnings),
    )

    if normalized_family == LABOR:
        return normalize_labor_record(prepared_record)
    if normalized_family == EQUIPMENT:
        return normalize_equipment_record(prepared_record)
    if normalized_family == MATERIAL:
        return normalize_material_record(prepared_record)
    return prepared_record


def _determine_normalized_family(record: Record) -> str:
    """Determine the business family to use during normalization."""
    phase_mapping = _get_phase_mapping()
    canonical_phase_code = canonicalize_phase_code(record.phase_code)
    if canonical_phase_code:
        mapped_family = _normalize_family_label(phase_mapping.get(canonical_phase_code))
        if mapped_family is not None:
            return mapped_family
    return record.record_type or OTHER


def _normalize_family_label(value: Optional[str]) -> Optional[str]:
    """Normalize a config family label to the canonical record-type form."""
    if value is None:
        return None
    normalized_value = value.strip().casefold()
    if normalized_value in {LABOR, EQUIPMENT, MATERIAL, SUBCONTRACTOR, OTHER}:
        return normalized_value
    return None


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    """Return warnings with duplicates removed while preserving order."""
    unique_warnings: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning not in seen:
            unique_warnings.append(warning)
            seen.add(warning)
    return unique_warnings
