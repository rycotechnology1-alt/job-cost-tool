"""Labor-specific normalization helpers for parsed job cost records."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any, Optional

from core.config import ConfigLoader
from core.config.classification_slots import build_slot_lookup, get_active_slots
from core.models.record import LABOR, Record


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
    """Apply raw-first labor normalization to a parsed labor record."""
    warnings = list(record.warnings)
    labor_mapping = _get_labor_mapping()
    target_classifications = _get_target_labor_classifications()

    labor_class_raw_value, used_raw_description_fallback = _resolve_labor_class_source(record)
    labor_raw_key = _derive_labor_raw_key(
        record,
        labor_class_raw_value,
        allow_union_prefix=not used_raw_description_fallback,
    )
    labor_class_normalized = _canonicalize_raw_labor_class(labor_class_raw_value)
    raw_target_label, raw_mapping_state = _map_raw_key_to_target_classification(
        labor_raw_key=labor_raw_key,
        labor_mapping=labor_mapping,
        target_classifications=target_classifications,
    )

    slot_id: Optional[str] = None
    recap_labor_classification: Optional[str] = None

    if raw_target_label is not None:
        slot_id, recap_labor_classification = _resolve_labor_slot(raw_target_label)
        if slot_id is None:
            raw_mapping_state = "inactive"

    if labor_class_raw_value is None or not str(labor_class_raw_value).strip():
        warnings.append("Labor record is missing a raw labor class for recap mapping.")
    elif raw_mapping_state == "missing" and labor_raw_key:
        warnings.append(
            f"Labor raw value '{labor_raw_key}' is not mapped to a target recap labor classification."
        )
    elif raw_mapping_state == "invalid" and labor_raw_key:
        warnings.append(
            f"Labor raw value '{labor_raw_key}' maps to a target recap labor classification that is not valid for the active profile."
        )
    elif raw_mapping_state == "inactive" and labor_raw_key:
        warnings.append(
            f"Labor raw value '{labor_raw_key}' maps to a classification that is not active for the current profile."
        )

    return replace(
        record,
        record_type_normalized=LABOR,
        labor_class_raw=labor_class_raw_value,
        labor_class_normalized=labor_class_normalized,
        recap_labor_slot_id=slot_id,
        recap_labor_classification=recap_labor_classification,
        warnings=_dedupe_warnings(warnings),
        confidence=_reduce_confidence(record.confidence, slot_id is None),
    )


def _derive_labor_raw_key(
    record: Record,
    labor_class_raw_value: Optional[str],
    *,
    allow_union_prefix: bool = True,
) -> Optional[str]:
    """Build the exact labor raw key used for direct raw-mapping lookups."""
    raw_labor_class = str(labor_class_raw_value or "").strip()
    if not raw_labor_class:
        return None

    canonical_labor_class = _canonicalize_token(raw_labor_class)
    union_code = str(record.union_code or "").strip()
    if allow_union_prefix and union_code:
        return f"{_canonicalize_token(union_code)}/{canonical_labor_class}"
    return canonical_labor_class or None



def _resolve_labor_class_source(record: Record) -> tuple[Optional[str], bool]:
    """Return the best available raw labor mapping source for a labor record."""
    parsed_labor_class = str(record.labor_class_raw or "").strip()
    if parsed_labor_class:
        return parsed_labor_class, False

    has_meaningful_labor_detail = bool(
        str(record.employee_id or "").strip() or str(record.employee_name or "").strip()
    )
    fallback_raw_description = str(record.raw_description or "").strip()
    if has_meaningful_labor_detail and fallback_raw_description:
        return fallback_raw_description, True

    return None, False



def _canonicalize_raw_labor_class(raw_labor_class: Optional[str]) -> Optional[str]:
    """Return the canonical raw labor class token for traceable display/use."""
    if raw_labor_class is None:
        return None
    canonical_value = _canonicalize_token(raw_labor_class)
    return canonical_value or None



def _map_raw_key_to_target_classification(
    labor_raw_key: Optional[str],
    labor_mapping: dict[str, Any],
    target_classifications: set[str],
) -> tuple[Optional[str], str]:
    """Map an exact labor raw key to a target recap classification when configured."""
    if not labor_raw_key:
        return None, "missing"

    raw_mappings = labor_mapping.get("raw_mappings", {})
    if not isinstance(raw_mappings, dict):
        return None, "missing"

    target = raw_mappings.get(labor_raw_key)
    if target is None:
        return None, "missing"

    target_value = str(target).strip()
    if not target_value or target_value not in target_classifications:
        return None, "invalid"
    return target_value, "matched"



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
