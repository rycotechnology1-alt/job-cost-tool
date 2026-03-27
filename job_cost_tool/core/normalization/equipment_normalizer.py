"""Equipment-specific normalization helpers for parsed job cost records."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.config.classification_slots import build_slot_lookup, get_active_slots
from job_cost_tool.core.models.record import EQUIPMENT, Record


@lru_cache(maxsize=1)
def _get_equipment_mapping() -> dict[str, Any]:
    """Return the cached equipment normalization config."""
    return ConfigLoader().get_equipment_mapping()


@lru_cache(maxsize=1)
def _get_target_equipment_classifications() -> set[str]:
    """Return the configured target equipment recap classifications."""
    config = ConfigLoader().get_target_equipment_classifications()
    classifications = config.get("classifications", [])
    return {str(item) for item in classifications if str(item).strip()}


@lru_cache(maxsize=1)
def _get_active_equipment_slot_lookup() -> dict[str, dict[str, Any]]:
    """Return the active equipment slot lookup keyed by current display label."""
    config = ConfigLoader().get_target_equipment_classifications()
    return build_slot_lookup(get_active_slots(config, slot_prefix="equipment"))


def normalize_equipment_record(record: Record) -> Record:
    """Apply config-driven equipment normalization to a parsed record."""
    warnings = list(record.warnings)
    equipment_target_label = _map_equipment_description(record.equipment_description)
    slot_id, equipment_category = _resolve_equipment_slot(equipment_target_label)

    if record.equipment_description is None:
        warnings.append("Equipment record is missing a raw equipment description for recap mapping.")
    elif equipment_target_label is None:
        warnings.append("Equipment description did not match a configured target equipment category.")
    elif slot_id is None:
        warnings.append("Equipment record mapped to a category that is not active for the current profile.")

    return replace(
        record,
        record_type_normalized=EQUIPMENT,
        recap_equipment_slot_id=slot_id,
        equipment_category=equipment_category,
        warnings=_dedupe_warnings(warnings),
        confidence=_reduce_confidence(record.confidence, slot_id is None),
    )


def _map_equipment_description(equipment_description: Optional[str]) -> Optional[str]:
    """Map a raw equipment description to a configured recap target."""
    if equipment_description is None:
        return None

    mapping = _get_equipment_mapping()
    keyword_mappings = mapping.get("keyword_mappings", {})
    if not isinstance(keyword_mappings, dict):
        return None

    description = equipment_description.casefold()
    matches: list[tuple[int, str]] = []
    for keyword, target in keyword_mappings.items():
        normalized_keyword = str(keyword).casefold()
        if normalized_keyword in description:
            matches.append((len(normalized_keyword), str(target).strip()))

    if not matches:
        return None

    matches.sort(key=lambda item: item[0], reverse=True)
    target = matches[0][1]
    if target not in _get_target_equipment_classifications():
        return None
    return target


def _resolve_equipment_slot(target_label: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Resolve the stable equipment slot identity for a mapped target label."""
    if not target_label:
        return None, None

    slot_lookup = _get_active_equipment_slot_lookup()
    slot = slot_lookup.get(target_label.casefold())
    if not slot:
        return None, None
    return str(slot.get("slot_id") or "").strip() or None, str(slot.get("label") or "").strip() or None


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
