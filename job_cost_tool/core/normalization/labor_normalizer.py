"""Labor-specific normalization helpers for parsed job cost records."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.config.classification_slots import build_slot_lookup, get_active_slots
from job_cost_tool.core.models.record import LABOR, Record

_FALLBACK_LABOR_MAPPING_GROUP = "*"


@lru_cache(maxsize=1)
def _get_labor_mapping() -> dict[str, Any]:
    """Return the cached labor normalization config."""
    return ConfigLoader().get_labor_mapping()


@lru_cache(maxsize=1)
def _get_target_labor_classifications() -> set[str]:
    """Return the configured target labor recap classifications."""
    config = ConfigLoader().get_target_labor_classifications()
    classifications = config.get("classifications", [])
    return {str(item) for item in classifications if str(item).strip()}


@lru_cache(maxsize=1)
def _get_active_labor_slot_lookup() -> dict[str, dict[str, Any]]:
    """Return the active labor slot lookup keyed by current display label."""
    config = ConfigLoader().get_target_labor_classifications()
    return build_slot_lookup(get_active_slots(config, slot_prefix="labor"))


def normalize_labor_record(record: Record) -> Record:
    """Apply config-driven labor normalization to a parsed record."""
    warnings = list(record.warnings)
    labor_mapping = _get_labor_mapping()
    target_classifications = _get_target_labor_classifications()

    labor_group = _resolve_labor_group(record, labor_mapping)
    labor_class_normalized = _normalize_labor_class(record.labor_class_raw, labor_mapping)
    recap_target_label = _map_to_target_classification(
        labor_group=labor_group,
        labor_class_normalized=labor_class_normalized,
        labor_mapping=labor_mapping,
        target_classifications=target_classifications,
    )
    slot_id, recap_labor_classification = _resolve_labor_slot(recap_target_label)

    if labor_group is None:
        warnings.append("Labor record could not be aligned to a configured labor group.")
    if record.labor_class_raw is None:
        warnings.append("Labor record is missing a raw labor class for recap mapping.")
    elif labor_class_normalized is None:
        warnings.append("Labor acronym did not match any configured labor alias.")
    if recap_target_label is None:
        warnings.append("Labor record could not be mapped to a target recap labor classification.")
    elif slot_id is None:
        warnings.append("Labor record mapped to a classification that is not active for the current profile.")

    return replace(
        record,
        record_type_normalized=LABOR,
        labor_class_normalized=labor_class_normalized,
        recap_labor_slot_id=slot_id,
        recap_labor_classification=recap_labor_classification,
        warnings=_dedupe_warnings(warnings),
        confidence=_reduce_confidence(record.confidence, slot_id is None),
    )


def _resolve_labor_group(record: Record, labor_mapping: dict[str, Any]) -> Optional[str]:
    """Resolve the labor mapping group using union code first, then phase defaults."""
    if record.union_code:
        return record.union_code.strip()

    phase_defaults = labor_mapping.get("phase_defaults", {})
    if not isinstance(phase_defaults, dict) or record.phase_code is None:
        return None
    phase_default = phase_defaults.get(record.phase_code)
    return str(phase_default).strip() if phase_default else None


def _normalize_labor_class(raw_labor_class: Optional[str], labor_mapping: dict[str, Any]) -> Optional[str]:
    """Normalize a raw labor class token to a configured canonical alias."""
    if raw_labor_class is None:
        return None

    canonical_key = _canonicalize_token(raw_labor_class)
    aliases = labor_mapping.get("aliases", {})
    if not isinstance(aliases, dict):
        return canonical_key or None

    normalized_value = aliases.get(canonical_key)
    if normalized_value is not None:
        return str(normalized_value).strip() or None

    return canonical_key or None


def _map_to_target_classification(
    labor_group: Optional[str],
    labor_class_normalized: Optional[str],
    labor_mapping: dict[str, Any],
    target_classifications: set[str],
) -> Optional[str]:
    """Map a canonical labor class to a configured recap target label."""
    if labor_group is None or labor_class_normalized is None:
        return None

    class_mappings = labor_mapping.get("class_mappings", {})
    if not isinstance(class_mappings, dict):
        return None

    group_mappings = class_mappings.get(labor_group, {})
    if not isinstance(group_mappings, dict):
        group_mappings = {}

    target = group_mappings.get(labor_class_normalized)
    if target is None:
        apprentice_aliases = labor_mapping.get("apprentice_aliases", [])
        apprentice_alias_set = {str(item).strip() for item in apprentice_aliases if str(item).strip()}
        if labor_class_normalized in apprentice_alias_set:
            target = group_mappings.get("APP")

    if target is None:
        fallback_mappings = class_mappings.get(_FALLBACK_LABOR_MAPPING_GROUP, {})
        if isinstance(fallback_mappings, dict):
            target = fallback_mappings.get(labor_class_normalized)
            if target is None:
                apprentice_aliases = labor_mapping.get("apprentice_aliases", [])
                apprentice_alias_set = {str(item).strip() for item in apprentice_aliases if str(item).strip()}
                if labor_class_normalized in apprentice_alias_set:
                    target = fallback_mappings.get("APP")

    if target is None:
        return None

    target_value = str(target).strip()
    if target_value not in target_classifications:
        return None
    return target_value


def _resolve_labor_slot(target_label: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Resolve the stable labor slot identity for a mapped target label."""
    if not target_label:
        return None, None

    slot_lookup = _get_active_labor_slot_lookup()
    slot = slot_lookup.get(target_label.casefold())
    if not slot:
        return None, None
    return str(slot.get("slot_id") or "").strip() or None, str(slot.get("label") or "").strip() or None


def _canonicalize_token(value: str) -> str:
    """Convert a raw token into a lookup-friendly canonical form."""
    collapsed = " ".join(value.strip().upper().split())
    return collapsed.replace("APPRENTICESHIP", "APP")


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
