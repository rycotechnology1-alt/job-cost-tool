"""Pure profile-bundle editing helpers shared by desktop and future web authoring flows."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from core.config.classification_slots import build_slot_config_from_rows
from core.equipment_keys import derive_equipment_mapping_key
from core.phase_codes import canonicalize_phase_code, phase_code_sort_key

__all__ = [
    "ClassificationBundleEditResult",
    "active_labels_from_slots",
    "canonicalize_equipment_mapping_key",
    "canonicalize_labor_mapping_key",
    "build_classification_bundle_edit_result",
    "build_default_omit_phase_options",
    "build_default_omit_rule_rows",
    "build_default_omit_rules_config",
    "build_equipment_mapping_config",
    "build_equipment_mapping_rows",
    "build_equipment_rate_rows",
    "build_labor_mapping_config",
    "build_labor_mapping_rows",
    "build_labor_rate_rows",
    "build_rates_config",
    "derive_labor_mapping_key",
    "build_slot_label_rename_map",
    "dedupe_casefold_preserving_order",
    "merge_observed_equipment_raw_values",
    "merge_observed_labor_raw_values",
    "normalize_phase_option_rows",
    "rename_equipment_mapping_config_targets",
    "rename_labor_mapping_config_targets",
    "rename_rates_config_targets",
    "rename_recap_template_map_targets",
    "validate_equipment_classification_references",
    "validate_labor_classification_references",
    "validate_slot_rows",
]


@dataclass(frozen=True, slots=True)
class ClassificationBundleEditResult:
    """Updated bundle payloads plus rename details from one slot-edit operation."""

    labor_slots_config: dict[str, Any]
    equipment_slots_config: dict[str, Any]
    labor_mapping_config: dict[str, Any]
    equipment_mapping_config: dict[str, Any]
    rates_config: dict[str, Any]
    recap_template_map: dict[str, Any]
    labor_rename_map: dict[str, str]
    equipment_rename_map: dict[str, str]


def build_default_omit_rules_config(
    existing_config: dict[str, Any],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Validate and build the persisted default-omit config payload."""
    saved_rules: list[dict[str, str]] = []
    seen_phase_codes: set[str] = set()
    for row in rows:
        phase_code = canonicalize_phase_code(row.get("phase_code"))
        if not phase_code:
            continue
        normalized_phase_code = phase_code.casefold()
        if normalized_phase_code in seen_phase_codes:
            raise ValueError(f"Duplicate default omit phase code '{phase_code}' is not allowed.")
        seen_phase_codes.add(normalized_phase_code)
        saved_rules.append({"phase_code": phase_code})

    new_config = dict(existing_config)
    new_config["default_omit_rules"] = saved_rules
    return new_config


def build_labor_mapping_config(
    existing_config: dict[str, Any],
    rows: list[dict[str, str]],
    *,
    valid_targets: list[str],
) -> dict[str, Any]:
    """Validate and build the raw-first labor mapping config payload."""
    valid_target_set = set(valid_targets)
    saved_mappings: list[dict[str, str]] = []
    seen_raw_keys: set[str] = set()

    for row in rows:
        raw_value = str(row.get("raw_value", "")).strip()
        target_classification = str(row.get("target_classification", "")).strip()
        note = str(row.get("notes", "")).strip()
        is_observed = _normalize_observed_flag(row.get("is_observed"))
        if not raw_value:
            raise ValueError("Labor mapping rows must include a raw value.")

        raw_key = _canonicalize_labor_token(raw_value)
        if raw_key in seen_raw_keys:
            raise ValueError(f"Duplicate labor mapping raw value '{raw_value}' is not allowed.")
        seen_raw_keys.add(raw_key)

        if target_classification and target_classification not in valid_target_set:
            raise ValueError(
                f"Labor mapping '{raw_value}' references unknown target classification '{target_classification}'."
            )

        saved_mappings.append(
            {
                "raw_value": raw_key,
                "target_classification": target_classification,
                "notes": note,
                "is_observed": is_observed and not target_classification,
            }
        )

    new_config = {
        key: value
        for key, value in dict(existing_config).items()
        if key != "mapping_notes"
    }
    new_config["raw_mappings"] = _build_raw_mappings_from_rows(saved_mappings)
    new_config["saved_mappings"] = _normalize_saved_labor_mapping_rows(saved_mappings)
    return new_config


def build_equipment_mapping_config(
    existing_config: dict[str, Any],
    rows: list[dict[str, str]],
    *,
    valid_targets: list[str],
) -> dict[str, Any]:
    """Validate and build the raw-first equipment mapping config payload."""
    valid_target_set = set(valid_targets)
    saved_mappings: list[dict[str, str]] = []
    seen_raw_descriptions: set[str] = set()

    for row in rows:
        raw_description = str(row.get("raw_description") or row.get("raw_pattern") or "").strip()
        target_category = str(row.get("target_category", "")).strip()
        is_observed = _normalize_observed_flag(row.get("is_observed"))
        if not raw_description:
            raise ValueError("Equipment mapping rows must include a raw description.")
        if target_category and target_category not in valid_target_set:
            raise ValueError(
                f"Equipment mapping '{raw_description}' references unknown target category '{target_category}'."
            )

        canonical_raw_description = _canonicalize_equipment_mapping_key(raw_description)
        normalized_raw_description = canonical_raw_description.casefold()
        if normalized_raw_description in seen_raw_descriptions:
            raise ValueError(
                f"Duplicate equipment mapping raw description '{raw_description}' is not allowed."
            )
        seen_raw_descriptions.add(normalized_raw_description)
        saved_mappings.append(
            {
                "raw_description": canonical_raw_description,
                "target_category": target_category,
                "is_observed": is_observed and not target_category,
            }
        )

    new_config = dict(existing_config)
    new_config["raw_mappings"] = _build_raw_equipment_mappings_from_rows(saved_mappings)
    new_config["saved_mappings"] = _normalize_saved_equipment_mapping_rows(saved_mappings)
    return new_config


def build_classification_bundle_edit_result(
    *,
    existing_labor_slots: list[dict[str, Any]],
    updated_labor_slots: list[dict[str, Any]],
    existing_equipment_slots: list[dict[str, Any]],
    updated_equipment_slots: list[dict[str, Any]],
    labor_mapping_rows: list[dict[str, str]],
    equipment_mapping_rows: list[dict[str, str]],
    labor_rate_rows: list[dict[str, str]],
    equipment_rate_rows: list[dict[str, str]],
    labor_mapping_config: dict[str, Any],
    equipment_mapping_config: dict[str, Any],
    rates_config: dict[str, Any],
    recap_template_map: dict[str, Any],
) -> ClassificationBundleEditResult:
    """Validate slot edits and return the updated dependent bundle payloads."""
    validated_labor_slots = _validate_slot_rows(
        updated_labor_slots,
        existing_slots=existing_labor_slots,
        slot_label="Labor",
    )
    validated_equipment_slots = _validate_slot_rows(
        updated_equipment_slots,
        existing_slots=existing_equipment_slots,
        slot_label="Equipment",
    )

    validated_labor = _active_labels_from_slots(validated_labor_slots)
    validated_equipment = _active_labels_from_slots(validated_equipment_slots)

    labor_rename_map = _build_slot_label_rename_map(existing_labor_slots, validated_labor_slots)
    equipment_rename_map = _build_slot_label_rename_map(existing_equipment_slots, validated_equipment_slots)

    remapped_labor_rows = _apply_label_renames_to_rows(
        labor_mapping_rows,
        "target_classification",
        labor_rename_map,
    )
    remapped_equipment_rows = _apply_label_renames_to_rows(
        equipment_mapping_rows,
        "target_category",
        equipment_rename_map,
    )
    remapped_labor_rate_rows = _apply_label_renames_to_rows(
        labor_rate_rows,
        "classification",
        labor_rename_map,
    )
    remapped_equipment_rate_rows = _apply_label_renames_to_rows(
        equipment_rate_rows,
        "category",
        equipment_rename_map,
    )

    _validate_labor_classification_references(
        rows=remapped_labor_rows,
        rate_rows=remapped_labor_rate_rows,
        valid_classifications=validated_labor,
    )
    _validate_equipment_classification_references(
        rows=remapped_equipment_rows,
        rate_rows=remapped_equipment_rate_rows,
        valid_classifications=validated_equipment,
    )

    return ClassificationBundleEditResult(
        labor_slots_config=build_slot_config_from_rows(validated_labor_slots),
        equipment_slots_config=build_slot_config_from_rows(validated_equipment_slots),
        labor_mapping_config=_rename_labor_mapping_config_targets(
            labor_mapping_config,
            labor_rename_map,
        ),
        equipment_mapping_config=_rename_equipment_mapping_config_targets(
            equipment_mapping_config,
            equipment_rename_map,
        ),
        rates_config=_rename_rates_config_targets(
            rates_config,
            labor_rename_map,
            equipment_rename_map,
        ),
        recap_template_map=_rename_recap_template_map_targets(
            recap_template_map,
            labor_rename_map,
            equipment_rename_map,
        ),
        labor_rename_map=labor_rename_map,
        equipment_rename_map=equipment_rename_map,
    )


def build_rates_config(
    existing_rates: dict[str, Any],
    labor_rows: list[dict[str, str]],
    equipment_rows: list[dict[str, str]],
    *,
    valid_labor_targets: list[str],
    valid_equipment_targets: list[str],
) -> dict[str, Any]:
    """Validate and build the persisted rates payload."""
    valid_labor_target_set = set(valid_labor_targets)
    valid_equipment_target_set = set(valid_equipment_targets)

    labor_rates: dict[str, dict[str, float]] = {}
    for row in labor_rows:
        classification = str(row.get("classification", "")).strip()
        if not classification:
            continue
        if classification not in valid_labor_target_set:
            raise ValueError(f"Unknown labor rate classification '{classification}'.")
        standard_rate = _parse_optional_rate(row.get("standard_rate"), f"{classification} standard rate")
        overtime_rate = _parse_optional_rate(row.get("overtime_rate"), f"{classification} overtime rate")
        double_time_rate = _parse_optional_rate(row.get("double_time_rate"), f"{classification} double time rate")
        if standard_rate is None and overtime_rate is None and double_time_rate is None:
            continue
        labor_rates[classification] = {}
        if standard_rate is not None:
            labor_rates[classification]["standard_rate"] = standard_rate
        if overtime_rate is not None:
            labor_rates[classification]["overtime_rate"] = overtime_rate
        if double_time_rate is not None:
            labor_rates[classification]["double_time_rate"] = double_time_rate

    equipment_rates: dict[str, dict[str, float]] = {}
    for row in equipment_rows:
        category = str(row.get("category", "")).strip()
        if not category:
            continue
        if category not in valid_equipment_target_set:
            raise ValueError(f"Unknown equipment rate category '{category}'.")
        rate = _parse_optional_rate(row.get("rate"), f"{category} equipment rate")
        if rate is None:
            continue
        equipment_rates[category] = {"rate": rate}

    new_rates = dict(existing_rates)
    new_rates["labor_rates"] = labor_rates
    new_rates["equipment_rates"] = equipment_rates
    return new_rates


def merge_observed_labor_raw_values(
    labor_mapping: dict[str, Any],
    observed_raw_values: list[str],
) -> tuple[dict[str, Any], bool]:
    """Merge newly observed labor raw values into saved mappings as blank placeholders."""
    observed_values = _dedupe_casefold_preserving_order(observed_raw_values)
    if not observed_values:
        return dict(labor_mapping), False

    base_rows = _normalize_saved_labor_mapping_rows(labor_mapping.get("saved_mappings", []))
    if not base_rows:
        base_rows = _build_saved_rows_from_raw_mappings(
            _normalize_raw_labor_mappings(labor_mapping.get("raw_mappings", {}))
        )

    seen_raw_values = {
        str(row.get("raw_value", "")).strip().casefold()
        for row in base_rows
        if str(row.get("raw_value", "")).strip()
    }

    did_update = False
    for raw_value in observed_values:
        raw_key = _canonicalize_labor_token(raw_value)
        if not raw_key or raw_key.casefold() in seen_raw_values:
            continue
        seen_raw_values.add(raw_key.casefold())
        base_rows.append(
            {
                "raw_value": raw_key,
                "target_classification": "",
                "notes": "",
                "is_observed": True,
            }
        )
        did_update = True

    if not did_update:
        return dict(labor_mapping), False

    updated_mapping = dict(labor_mapping)
    updated_mapping["saved_mappings"] = _normalize_saved_labor_mapping_rows(base_rows)
    return updated_mapping, True


def merge_observed_equipment_raw_values(
    equipment_mapping: dict[str, Any],
    observed_raw_descriptions: list[str],
) -> tuple[dict[str, Any], bool]:
    """Merge newly observed equipment keys into saved mappings as blank placeholders."""
    observed_values = _dedupe_casefold_preserving_order(observed_raw_descriptions)
    if not observed_values:
        return dict(equipment_mapping), False

    base_rows = _normalize_saved_equipment_mapping_rows(equipment_mapping.get("saved_mappings", []))
    if not base_rows:
        base_rows = _build_saved_equipment_rows_from_raw_mappings(
            _normalize_raw_equipment_mappings(equipment_mapping.get("raw_mappings", {}))
        )

    seen_raw_descriptions = {
        str(row.get("raw_description", "")).strip().casefold()
        for row in base_rows
        if str(row.get("raw_description", "")).strip()
    }

    did_update = False
    for raw_description in observed_values:
        canonical_raw_description = _canonicalize_equipment_mapping_key(raw_description)
        if not canonical_raw_description or canonical_raw_description.casefold() in seen_raw_descriptions:
            continue
        seen_raw_descriptions.add(canonical_raw_description.casefold())
        base_rows.append(
            {
                "raw_description": canonical_raw_description,
                "target_category": "",
                "is_observed": True,
            }
        )
        did_update = True

    if not did_update:
        return dict(equipment_mapping), False

    updated_mapping = dict(equipment_mapping)
    updated_mapping["saved_mappings"] = _normalize_saved_equipment_mapping_rows(base_rows)
    updated_mapping["raw_mappings"] = _build_raw_equipment_mappings_from_rows(updated_mapping["saved_mappings"])
    return updated_mapping, True


def _build_labor_mapping_rows(
    labor_mapping: dict[str, Any],
    *,
    observed_raw_values: list[str] | None = None,
    required_raw_values: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten raw-first labor mapping rows and observed values into editor rows."""
    saved_rows = _normalize_saved_labor_mapping_rows(labor_mapping.get("saved_mappings", []))

    if saved_rows:
        rows = saved_rows
    else:
        rows = _build_saved_rows_from_raw_mappings(
            _normalize_raw_labor_mappings(labor_mapping.get("raw_mappings", {}))
        )

    seen_raw_values = {
        str(row.get("raw_value", "")).strip().casefold()
        for row in rows
        if str(row.get("raw_value", "")).strip()
    }

    for raw_value in observed_raw_values or []:
        raw_value_text = _canonicalize_labor_token(str(raw_value).strip())
        if not raw_value_text or raw_value_text.casefold() in seen_raw_values:
            continue
        seen_raw_values.add(raw_value_text.casefold())
        rows.append(
            {
                "raw_value": raw_value_text,
                "target_classification": "",
                "notes": "",
                "is_observed": True,
            }
        )

    required_raw_key_set = {
        _canonicalize_labor_token(str(raw_value).strip()).casefold()
        for raw_value in (required_raw_values or [])
        if _canonicalize_labor_token(str(raw_value).strip())
    }

    rows.sort(
        key=lambda row: (
            _mapping_priority(
                raw_key=str(row.get("raw_value", "")),
                target_value=str(row.get("target_classification", "")),
                is_observed=_normalize_observed_flag(row.get("is_observed")),
                required_raw_key_set=required_raw_key_set,
            ),
            row["target_classification"].casefold(),
            row["raw_value"].casefold(),
        )
    )
    response_rows: list[dict[str, Any]] = []
    for row in rows:
        response_row: dict[str, Any] = {
            "raw_value": row["raw_value"],
            "target_classification": row["target_classification"],
            "notes": row["notes"],
        }
        is_unmapped_observed = _normalize_observed_flag(row.get("is_observed")) and not str(
            row.get("target_classification", "")
        ).strip()
        if is_unmapped_observed:
            response_row["is_observed"] = True
            if str(row.get("raw_value", "")).strip().casefold() in required_raw_key_set:
                response_row["is_required_for_recent_processing"] = True
        response_rows.append(response_row)
    return response_rows


def _normalize_saved_labor_mapping_rows(saved_mappings: Any) -> list[dict[str, Any]]:
    """Normalize saved labor editor rows while preserving blank unmapped placeholders."""
    if not isinstance(saved_mappings, list):
        return []

    rows: list[dict[str, Any]] = []
    seen_raw_values: set[str] = set()
    for item in saved_mappings:
        if not isinstance(item, dict):
            continue
        raw_value = _canonicalize_labor_token(str(item.get("raw_value", "")).strip())
        if not raw_value or raw_value.casefold() in seen_raw_values:
            continue
        seen_raw_values.add(raw_value.casefold())
        rows.append(
            _build_labor_saved_row(
                raw_value=raw_value,
                target_classification=str(item.get("target_classification", "")).strip(),
                notes=str(item.get("notes", "")).strip(),
                is_observed=_normalize_observed_flag(item.get("is_observed")),
            )
        )

    return rows


def _normalize_raw_labor_mappings(raw_mappings: Any) -> dict[str, str]:
    """Normalize raw-first labor mapping entries to canonical admin/edit keys."""
    if not isinstance(raw_mappings, dict):
        return {}

    normalized: dict[str, str] = {}
    for raw_value, target_classification in raw_mappings.items():
        canonical_raw_value = _canonicalize_labor_token(raw_value)
        target = str(target_classification).strip()
        if canonical_raw_value and target:
            normalized[canonical_raw_value] = target
    return normalized


def _build_saved_rows_from_raw_mappings(raw_mappings: dict[str, str]) -> list[dict[str, Any]]:
    """Materialize editable saved rows from direct raw labor mappings."""
    return [
        _build_labor_saved_row(
            raw_value=raw_value,
            target_classification=target_classification,
            notes="",
        )
        for raw_value, target_classification in raw_mappings.items()
    ]


def _build_raw_mappings_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Build direct raw labor mappings from admin rows, excluding blanks."""
    raw_mappings: dict[str, str] = {}
    for row in rows:
        raw_value = str(row.get("raw_value", "")).strip()
        target_classification = str(row.get("target_classification", "")).strip()
        if raw_value and target_classification:
            raw_mappings[raw_value] = target_classification
    return raw_mappings


def _normalize_saved_equipment_mapping_rows(saved_mappings: Any) -> list[dict[str, Any]]:
    """Normalize saved equipment editor rows while preserving blank unmapped placeholders."""
    if not isinstance(saved_mappings, list):
        return []

    rows: list[dict[str, Any]] = []
    seen_raw_descriptions: set[str] = set()
    for item in saved_mappings:
        if not isinstance(item, dict):
            continue
        raw_description = _canonicalize_equipment_mapping_key(str(item.get("raw_description", "")).strip())
        if not raw_description or raw_description.casefold() in seen_raw_descriptions:
            continue
        seen_raw_descriptions.add(raw_description.casefold())
        rows.append(
            _build_equipment_saved_row(
                raw_description=raw_description,
                target_category=str(item.get("target_category", "")).strip(),
                is_observed=_normalize_observed_flag(item.get("is_observed")),
            )
        )

    return rows


def _normalize_raw_equipment_mappings(raw_mappings: Any) -> dict[str, str]:
    """Normalize raw-first equipment mappings to canonical reusable keys."""
    if not isinstance(raw_mappings, dict):
        return {}

    normalized: dict[str, str] = {}
    for raw_description, target_category in raw_mappings.items():
        canonical_raw_description = _canonicalize_equipment_mapping_key(raw_description)
        target = str(target_category).strip()
        if canonical_raw_description and target:
            normalized[canonical_raw_description] = target
    return normalized


def _build_saved_equipment_rows_from_raw_mappings(raw_mappings: dict[str, str]) -> list[dict[str, Any]]:
    """Materialize editable saved rows from direct raw equipment mappings."""
    rows = [
        _build_equipment_saved_row(
            raw_description=raw_description,
            target_category=target_category,
        )
        for raw_description, target_category in raw_mappings.items()
    ]
    return rows


def _build_raw_equipment_mappings_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Build direct raw equipment mappings from admin rows, excluding blanks."""
    raw_mappings: dict[str, str] = {}
    for row in rows:
        raw_description = str(row.get("raw_description", "")).strip()
        target_category = str(row.get("target_category", "")).strip()
        if raw_description and target_category:
            raw_mappings[raw_description] = target_category
    return raw_mappings


def _build_equipment_mapping_rows(
    equipment_mapping: dict[str, Any],
    *,
    observed_raw_descriptions: list[str] | None = None,
    required_raw_descriptions: list[str] | None = None,
    active_targets: list[str] | None = None,
) -> list[dict[str, str]]:
    """Flatten raw-first equipment mappings and observed values into editor rows."""
    saved_rows = _normalize_saved_equipment_mapping_rows(equipment_mapping.get("saved_mappings", []))

    if saved_rows:
        rows = saved_rows
    else:
        rows = _build_saved_equipment_rows_from_raw_mappings(
            _normalize_raw_equipment_mappings(equipment_mapping.get("raw_mappings", {}))
        )

    seen_raw_descriptions = {
        str(row.get("raw_description", "")).strip().casefold()
        for row in rows
        if str(row.get("raw_description", "")).strip()
    }

    for raw_description in observed_raw_descriptions or []:
        raw_text = _canonicalize_equipment_mapping_key(str(raw_description).strip())
        if not raw_text or raw_text.casefold() in seen_raw_descriptions:
            continue
        seen_raw_descriptions.add(raw_text.casefold())
        rows.append(
            {
                "raw_description": raw_text,
                "target_category": "",
                "is_observed": True,
            }
        )

    required_raw_key_set = {
        _canonicalize_equipment_mapping_key(str(raw_description).strip()).casefold()
        for raw_description in (required_raw_descriptions or [])
        if _canonicalize_equipment_mapping_key(str(raw_description).strip())
    }
    prediction_map = _build_equipment_prediction_map(rows, active_targets=active_targets or [])

    rows.sort(
        key=lambda row: (
            _mapping_priority(
                raw_key=str(row.get("raw_description", "")),
                target_value=str(row.get("target_category", "")),
                is_observed=_normalize_observed_flag(row.get("is_observed")),
                required_raw_key_set=required_raw_key_set,
            ),
            row["target_category"].casefold(),
            row["raw_description"].casefold(),
        )
    )
    response_rows: list[dict[str, str | bool]] = []
    for row in rows:
        response_row: dict[str, str | bool] = {
            "raw_description": row["raw_description"],
            "raw_pattern": row["raw_description"],
            "target_category": row["target_category"],
        }
        is_unmapped_observed = _normalize_observed_flag(row.get("is_observed")) and not str(
            row.get("target_category", "")
        ).strip()
        if is_unmapped_observed:
            response_row["is_observed"] = True
            if str(row.get("raw_description", "")).strip().casefold() in required_raw_key_set:
                response_row["is_required_for_recent_processing"] = True
        if not str(row.get("target_category", "")).strip():
            prediction = prediction_map.get(str(row.get("raw_description", "")).strip().casefold())
            if prediction is not None:
                response_row["prediction_target"] = prediction["prediction_target"]
                response_row["prediction_confidence_label"] = prediction["prediction_confidence_label"]
        response_rows.append(response_row)
    return response_rows


def _build_labor_rate_rows(rates: dict[str, Any], classifications: list[str]) -> list[dict[str, str]]:
    """Build labor rate editor rows from configured classifications and saved rates."""
    labor_rates = rates.get("labor_rates", {}) if isinstance(rates.get("labor_rates"), dict) else {}
    ordered_classifications = _merge_ordered_labels(classifications, labor_rates.keys())
    rows: list[dict[str, str]] = []
    for classification in ordered_classifications:
        raw_entry = labor_rates.get(classification, {})
        if isinstance(raw_entry, dict):
            standard_rate = raw_entry.get("standard_rate")
            overtime_rate = raw_entry.get("overtime_rate")
            double_time_rate = raw_entry.get("double_time_rate")
        else:
            standard_rate = raw_entry
            overtime_rate = None
            double_time_rate = None
        rows.append(
            {
                "classification": classification,
                "standard_rate": _stringify_rate(standard_rate),
                "overtime_rate": _stringify_rate(overtime_rate),
                "double_time_rate": _stringify_rate(double_time_rate),
            }
        )
    return rows


def _build_equipment_rate_rows(rates: dict[str, Any], categories: list[str]) -> list[dict[str, str]]:
    """Build equipment rate editor rows from configured categories and saved rates."""
    equipment_rates = rates.get("equipment_rates", {}) if isinstance(rates.get("equipment_rates"), dict) else {}
    ordered_categories = _merge_ordered_labels(categories, equipment_rates.keys())
    rows: list[dict[str, str]] = []
    for category in ordered_categories:
        raw_entry = equipment_rates.get(category, {})
        if isinstance(raw_entry, dict):
            rate = raw_entry.get("rate")
        else:
            rate = raw_entry
        rows.append({"category": category, "rate": _stringify_rate(rate)})
    return rows


def _build_default_omit_phase_options(
    *,
    catalog_phase_rows: list[dict[str, Any]],
    saved_rule_rows: list[dict[str, Any]],
    observed_phase_options: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build deterministic default-omit phase choices from the shared catalog and safe fallback sources."""
    phase_rows: list[dict[str, str]] = list(catalog_phase_rows or [])
    phase_rows.extend(observed_phase_options or [])
    phase_rows.extend(
        {
            "phase_code": str(row.get("phase_code", "")).strip(),
            "phase_name": "",
        }
        for row in saved_rule_rows
        if isinstance(row, dict)
    )
    return sorted(_normalize_phase_option_rows(phase_rows), key=lambda row: phase_code_sort_key(row["phase_code"]))


def _build_default_omit_rule_rows(
    review_rules: dict[str, Any],
    *,
    phase_options: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build admin-facing default-omit rule rows with resolved phase names."""
    rows: list[dict[str, str]] = []
    phase_name_lookup = {
        str(row.get("phase_code", "")).strip().casefold(): str(row.get("phase_name", "")).strip()
        for row in phase_options
        if str(row.get("phase_code", "")).strip()
    }

    for rule in review_rules.get("default_omit_rules", []):
        if not isinstance(rule, dict):
            continue
        phase_code = canonicalize_phase_code(rule.get("phase_code"))
        if not phase_code:
            continue
        rows.append(
            {
                "phase_code": phase_code,
                "phase_name": phase_name_lookup.get(phase_code.casefold(), ""),
            }
        )
    return rows


def _normalize_phase_option_rows(values: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Canonicalize and dedupe phase options while preserving first-seen order."""
    normalized_rows: list[dict[str, str]] = []
    index_by_key: dict[str, int] = {}

    for row in values:
        if not isinstance(row, dict):
            continue
        phase_code = canonicalize_phase_code(row.get("phase_code"))
        if not phase_code:
            continue
        phase_name = " ".join(str(row.get("phase_name", "")).strip().split())
        normalized_key = phase_code.casefold()
        if normalized_key in index_by_key:
            existing_row = normalized_rows[index_by_key[normalized_key]]
            if not existing_row["phase_name"] and phase_name:
                existing_row["phase_name"] = phase_name
            continue
        index_by_key[normalized_key] = len(normalized_rows)
        normalized_rows.append({"phase_code": phase_code, "phase_name": phase_name})

    return normalized_rows


def _dedupe_casefold_preserving_order(values: list[str]) -> list[str]:
    """Return unique non-empty strings while preserving first-seen order."""
    deduped_values: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            continue
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped_values.append(value)
    return deduped_values


def _merge_ordered_labels(primary: list[str], secondary: Any) -> list[str]:
    """Merge configured labels and saved-rate keys while preserving order."""
    ordered_values: list[str] = []
    seen: set[str] = set()
    for value in list(primary) + [str(item).strip() for item in secondary if str(item).strip()]:
        if value and value not in seen:
            ordered_values.append(value)
            seen.add(value)
    return ordered_values


def _validate_slot_rows(
    slot_rows: list[dict[str, Any]],
    *,
    existing_slots: list[dict[str, Any]],
    slot_label: str,
) -> list[dict[str, Any]]:
    """Validate edited slot rows for a fixed-capacity classification table."""
    if len(slot_rows) != len(existing_slots):
        raise ValueError(
            f"{slot_label} slot count does not match fixed template capacity ({len(existing_slots)} slots expected)."
        )

    validated_rows: list[dict[str, Any]] = []
    seen_active_labels: set[str] = set()
    for index, (row, existing_slot) in enumerate(zip(slot_rows, existing_slots), start=1):
        slot_id = str(row.get("slot_id") or existing_slot.get("slot_id") or "").strip()
        expected_slot_id = str(existing_slot.get("slot_id") or "").strip()
        if not slot_id or slot_id != expected_slot_id:
            raise ValueError(f"{slot_label} slot {index} has an invalid slot identifier.")

        active = bool(row.get("active"))
        label = str(row.get("label", "")).strip()
        if active and not label:
            raise ValueError(f"{slot_label} slot {index} is active and requires a label.")
        if active:
            label_key = label.casefold()
            if label_key in seen_active_labels:
                raise ValueError(f"Duplicate active {slot_label.casefold()} classification '{label}' is not allowed.")
            seen_active_labels.add(label_key)

        validated_rows.append(
            {
                "slot_id": slot_id,
                "label": label,
                "active": active,
            }
        )
    return validated_rows


def _active_labels_from_slots(slot_rows: list[dict[str, Any]]) -> list[str]:
    """Return active labels from edited slot rows in table order."""
    return [
        str(slot.get("label", "")).strip()
        for slot in slot_rows
        if slot.get("active") and str(slot.get("label", "")).strip()
    ]


def _build_slot_label_rename_map(
    previous_slots: list[dict[str, Any]],
    updated_slots: list[dict[str, Any]],
) -> dict[str, str]:
    """Build a rename map by comparing slot labels with stable slot identities."""
    updated_by_slot_id = {
        str(slot.get("slot_id", "")).strip(): slot
        for slot in updated_slots
        if str(slot.get("slot_id", "")).strip()
    }

    rename_map: dict[str, str] = {}
    for previous_slot in previous_slots:
        slot_id = str(previous_slot.get("slot_id", "")).strip()
        if not slot_id or slot_id not in updated_by_slot_id:
            continue
        updated_slot = updated_by_slot_id[slot_id]
        previous_label = str(previous_slot.get("label", "")).strip() if previous_slot.get("active") else ""
        updated_label = str(updated_slot.get("label", "")).strip() if updated_slot.get("active") else ""
        if previous_label and updated_label and previous_label != updated_label:
            rename_map[previous_label] = updated_label
    return rename_map


def _merge_active_labels_into_slots(
    existing_slots: list[dict[str, Any]],
    active_labels: list[str],
) -> list[dict[str, Any]]:
    """Project a simple active-label list back onto the current fixed slot order."""
    slot_rows: list[dict[str, Any]] = []
    for index, existing_slot in enumerate(existing_slots):
        label = active_labels[index] if index < len(active_labels) else ""
        slot_rows.append(
            {
                "slot_id": str(existing_slot.get("slot_id") or "").strip(),
                "label": label,
                "active": bool(label),
            }
        )
    return slot_rows


def _apply_label_renames_to_rows(
    rows: list[dict[str, str]],
    key: str,
    rename_map: dict[str, str],
) -> list[dict[str, str]]:
    """Apply classification renames to a simple list of editor rows."""
    remapped_rows: list[dict[str, str]] = []
    for row in rows:
        updated_row = dict(row)
        value = str(updated_row.get(key, "")).strip()
        if value in rename_map:
            updated_row[key] = rename_map[value]
        remapped_rows.append(updated_row)
    return remapped_rows


def _rename_labor_mapping_config_targets(
    labor_mapping: dict[str, Any],
    rename_map: dict[str, str],
) -> dict[str, Any]:
    """Rename labor target classifications inside the raw-first labor mapping config."""
    updated_config = {
        key: value
        for key, value in dict(labor_mapping).items()
        if key != "mapping_notes"
    }

    raw_mappings = _normalize_raw_labor_mappings(labor_mapping.get("raw_mappings", {}))
    if raw_mappings or "raw_mappings" in labor_mapping:
        updated_config["raw_mappings"] = {
            raw_key: rename_map.get(target_classification, target_classification)
            for raw_key, target_classification in raw_mappings.items()
        }

    saved_rows = _normalize_saved_labor_mapping_rows(labor_mapping.get("saved_mappings", []))
    if saved_rows or "saved_mappings" in labor_mapping:
        updated_config["saved_mappings"] = [
            _build_labor_saved_row(
                raw_value=str(row.get("raw_value", "")).strip(),
                target_classification=rename_map.get(
                    str(row.get("target_classification", "")).strip(),
                    str(row.get("target_classification", "")).strip(),
                ),
                notes=str(row.get("notes", "")).strip(),
                is_observed=_normalize_observed_flag(row.get("is_observed")),
            )
            for row in saved_rows
        ]

    return updated_config


def _rename_equipment_mapping_config_targets(
    equipment_mapping: dict[str, Any],
    rename_map: dict[str, str],
) -> dict[str, Any]:
    """Rename equipment target classifications inside the raw-first equipment mapping config."""
    updated_config = dict(equipment_mapping)

    raw_mappings = _normalize_raw_equipment_mappings(equipment_mapping.get("raw_mappings", {}))
    if raw_mappings or "raw_mappings" in equipment_mapping:
        updated_config["raw_mappings"] = {
            raw_description: rename_map.get(target_category, target_category)
            for raw_description, target_category in raw_mappings.items()
        }

    saved_rows = _normalize_saved_equipment_mapping_rows(equipment_mapping.get("saved_mappings", []))
    if saved_rows or "saved_mappings" in equipment_mapping:
        updated_config["saved_mappings"] = [
            _build_equipment_saved_row(
                raw_description=str(row.get("raw_description", "")).strip(),
                target_category=rename_map.get(
                    str(row.get("target_category", "")).strip(),
                    str(row.get("target_category", "")).strip(),
                ),
                is_observed=_normalize_observed_flag(row.get("is_observed")),
            )
            for row in saved_rows
        ]
    return updated_config


def _rename_rates_config_targets(
    rates_config: dict[str, Any],
    labor_rename_map: dict[str, str],
    equipment_rename_map: dict[str, str],
) -> dict[str, Any]:
    """Rename labor and equipment rate keys to follow updated classifications."""
    updated_config = dict(rates_config)

    labor_rates = rates_config.get("labor_rates", {})
    updated_labor_rates: dict[str, Any] = {}
    if isinstance(labor_rates, dict):
        for classification, rate_values in labor_rates.items():
            key = labor_rename_map.get(str(classification).strip(), str(classification).strip())
            if key in updated_labor_rates:
                raise ValueError(f"Labor rate collision detected while renaming '{key}'.")
            updated_labor_rates[key] = rate_values
    updated_config["labor_rates"] = updated_labor_rates

    equipment_rates = rates_config.get("equipment_rates", {})
    updated_equipment_rates: dict[str, Any] = {}
    if isinstance(equipment_rates, dict):
        for category, rate_values in equipment_rates.items():
            key = equipment_rename_map.get(str(category).strip(), str(category).strip())
            if key in updated_equipment_rates:
                raise ValueError(f"Equipment rate collision detected while renaming '{key}'.")
            updated_equipment_rates[key] = rate_values
    updated_config["equipment_rates"] = updated_equipment_rates

    return updated_config


def _rename_recap_template_map_targets(
    recap_template_map: dict[str, Any],
    labor_rename_map: dict[str, str],
    equipment_rename_map: dict[str, str],
) -> dict[str, Any]:
    """Rename recap template row keys so export continues to align with updated classifications."""
    updated_map = dict(recap_template_map)
    updated_map["labor_rows"] = _rename_mapping_keys(
        recap_template_map.get("labor_rows", {}),
        labor_rename_map,
        "labor recap row",
    )
    updated_map["equipment_rows"] = _rename_mapping_keys(
        recap_template_map.get("equipment_rows", {}),
        equipment_rename_map,
        "equipment recap row",
    )
    return updated_map


def _rename_mapping_keys(
    mapping: Any,
    rename_map: dict[str, str],
    label: str,
) -> dict[str, Any]:
    """Rename dictionary keys while detecting collisions."""
    if not isinstance(mapping, dict):
        return {}
    if not rename_map:
        return dict(mapping)

    updated_mapping: dict[str, Any] = {}
    for key, value in mapping.items():
        key_text = str(key).strip()
        updated_key = rename_map.get(key_text, key_text)
        if updated_key in updated_mapping:
            raise ValueError(f"{label.capitalize()} collision detected while renaming '{updated_key}'.")
        updated_mapping[updated_key] = value
    return updated_mapping


def _validate_labor_classification_references(
    rows: list[dict[str, str]],
    rate_rows: list[dict[str, str]],
    valid_classifications: list[str],
) -> None:
    """Ensure proposed labor classifications still cover saved mappings and rates."""
    valid_targets = {value.casefold(): value for value in valid_classifications}

    for row in rows:
        raw_value = str(row.get("raw_value", "")).strip()
        target_classification = str(row.get("target_classification", "")).strip()
        if target_classification and target_classification.casefold() not in valid_targets:
            raise ValueError(
                f"Labor classification '{target_classification}' is still referenced by labor mapping '{raw_value}'. "
                "Update mappings first."
            )

    for row in rate_rows:
        classification = str(row.get("classification", "")).strip()
        has_rate = any(str(row.get(key, "")).strip() for key in ("standard_rate", "overtime_rate", "double_time_rate"))
        if classification and has_rate and classification.casefold() not in valid_targets:
            raise ValueError(
                f"Labor classification '{classification}' is still referenced by configured labor rates. "
                "Update rates first."
            )


def _validate_equipment_classification_references(
    rows: list[dict[str, str]],
    rate_rows: list[dict[str, str]],
    valid_classifications: list[str],
) -> None:
    """Ensure proposed equipment classifications still cover saved mappings and rates."""
    valid_targets = {value.casefold(): value for value in valid_classifications}

    for row in rows:
        raw_description = str(row.get("raw_description") or row.get("raw_pattern") or "").strip()
        target_category = str(row.get("target_category", "")).strip()
        if target_category and target_category.casefold() not in valid_targets:
            raise ValueError(
                f"Equipment classification '{target_category}' is still referenced by equipment mapping '{raw_description}'. "
                "Update mappings first."
            )

    for row in rate_rows:
        category = str(row.get("category", "")).strip()
        has_rate = bool(str(row.get("rate", "")).strip())
        if category and has_rate and category.casefold() not in valid_targets:
            raise ValueError(
                f"Equipment classification '{category}' is still referenced by configured equipment rates. "
                "Update rates first."
            )


def _parse_optional_rate(value: Any, label: str) -> float | None:
    """Parse a possibly-empty rate cell to a non-negative float."""
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        numeric_value = float(text_value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if numeric_value < 0:
        raise ValueError(f"{label} must be greater than or equal to 0.")
    return numeric_value


def derive_labor_mapping_key(
    raw_value: str | None,
    *,
    union_code: str | None = None,
    allow_union_prefix: bool = True,
) -> str | None:
    """Build the canonical labor mapping key used for raw-first lookup/persistence."""
    canonical_raw_value = _canonicalize_labor_token(str(raw_value or "").strip())
    if not canonical_raw_value:
        return None
    canonical_union_code = _canonicalize_labor_token(str(union_code or "").strip())
    if allow_union_prefix and canonical_union_code:
        return f"{canonical_union_code}/{canonical_raw_value}"
    return canonical_raw_value


def _canonicalize_labor_token(value: str) -> str:
    """Canonicalize labor mapping tokens consistently with labor normalization."""
    collapsed = " ".join(str(value).strip().upper().split())
    return collapsed.replace("APPRENTICESHIP", "APP")


def _canonicalize_equipment_mapping_key(value: str) -> str:
    """Derive the Phase 1 reusable equipment mapping key for settings and persistence."""
    return derive_equipment_mapping_key(value) or ""


def _stringify_rate(value: Any) -> str:
    """Convert a saved rate value to a user-editable string."""
    if value in {None, ""}:
        return ""
    return str(value)


def _normalize_observed_flag(value: Any) -> bool:
    """Return True only when a mapping row should stay flagged as observed and unresolved."""
    if isinstance(value, bool):
        return value
    text_value = str(value or "").strip().casefold()
    return text_value in {"1", "true", "yes", "y"}


def _mapping_priority(
    *,
    raw_key: str,
    target_value: str,
    is_observed: bool,
    required_raw_key_set: set[str],
) -> int:
    """Sort required unresolved observations ahead of the broader mapping list."""
    normalized_raw_key = str(raw_key or "").strip().casefold()
    if not str(target_value or "").strip() and normalized_raw_key in required_raw_key_set:
        return 0
    if not str(target_value or "").strip() and is_observed:
        return 1
    return 2


def _prediction_tokens(value: str) -> set[str]:
    """Tokenize a display label or canonical key for lightweight suggestion scoring."""
    return {token for token in re.split(r"[^A-Z0-9]+", str(value or "").upper()) if len(token) >= 2}


def _score_equipment_prediction_candidate(raw_description: str, candidate_text: str) -> float:
    """Score one equipment prediction candidate using exactness, token overlap, and string similarity."""
    normalized_raw = _canonicalize_equipment_mapping_key(raw_description)
    normalized_candidate = _canonicalize_equipment_mapping_key(candidate_text)
    if not normalized_raw or not normalized_candidate:
        return 0.0
    if normalized_raw == normalized_candidate:
        return 1.0
    if normalized_raw in normalized_candidate or normalized_candidate in normalized_raw:
        return 0.94

    raw_tokens = _prediction_tokens(normalized_raw)
    candidate_tokens = _prediction_tokens(normalized_candidate)
    token_overlap = (
        len(raw_tokens.intersection(candidate_tokens)) / max(len(raw_tokens), len(candidate_tokens))
        if raw_tokens and candidate_tokens
        else 0.0
    )
    similarity = difflib.SequenceMatcher(a=normalized_raw, b=normalized_candidate).ratio()
    return max(similarity, (similarity * 0.55) + (token_overlap * 0.75))


def _build_equipment_prediction_map(
    rows: list[dict[str, Any]],
    *,
    active_targets: list[str],
) -> dict[str, dict[str, str]]:
    """Suggest likely equipment targets for currently unmapped rows from nearby known mapping examples."""
    example_rows = [
        row
        for row in rows
        if str(row.get("target_category", "")).strip()
    ]
    if not example_rows:
        return {}

    allowed_target_set = {target.casefold() for target in active_targets if str(target).strip()}
    target_examples: dict[str, list[str]] = {}
    for row in example_rows:
        target_category = str(row.get("target_category", "")).strip()
        if not target_category:
            continue
        if allowed_target_set and target_category.casefold() not in allowed_target_set:
            continue
        target_examples.setdefault(target_category, []).append(str(row.get("raw_description", "")).strip())
        target_examples[target_category].append(target_category)

    predictions: dict[str, dict[str, str]] = {}
    for row in rows:
        raw_description = str(row.get("raw_description", "")).strip()
        if not raw_description or str(row.get("target_category", "")).strip():
            continue
        ranked_candidates: list[tuple[float, str]] = []
        for target_category, example_texts in target_examples.items():
            score = max(
                (_score_equipment_prediction_candidate(raw_description, candidate_text) for candidate_text in example_texts),
                default=0.0,
            )
            ranked_candidates.append((score, target_category))

        ranked_candidates.sort(key=lambda item: (-item[0], item[1].casefold()))
        if not ranked_candidates or ranked_candidates[0][0] < 0.65:
            continue
        if len(ranked_candidates) > 1 and ranked_candidates[0][0] - ranked_candidates[1][0] < 0.08:
            continue

        confidence_label = "High confidence" if ranked_candidates[0][0] >= 0.9 else "Likely match"
        predictions[raw_description.casefold()] = {
            "prediction_target": ranked_candidates[0][1],
            "prediction_confidence_label": confidence_label,
        }
    return predictions


def _build_labor_saved_row(
    *,
    raw_value: str,
    target_classification: str,
    notes: str,
    is_observed: bool = False,
) -> dict[str, Any]:
    """Build one saved labor mapping row without widening persisted shape unnecessarily."""
    row: dict[str, Any] = {
        "raw_value": raw_value,
        "target_classification": target_classification,
        "notes": notes,
    }
    if is_observed and not target_classification:
        row["is_observed"] = True
    return row


def _build_equipment_saved_row(
    *,
    raw_description: str,
    target_category: str,
    is_observed: bool = False,
) -> dict[str, Any]:
    """Build one saved equipment mapping row without widening persisted shape unnecessarily."""
    row: dict[str, Any] = {
        "raw_description": raw_description,
        "target_category": target_category,
    }
    if is_observed and not target_category:
        row["is_observed"] = True
    return row


# Public helper seam for desktop settings and later web profile-authoring work.
active_labels_from_slots = _active_labels_from_slots
canonicalize_equipment_mapping_key = _canonicalize_equipment_mapping_key
canonicalize_labor_mapping_key = _canonicalize_labor_token
build_default_omit_phase_options = _build_default_omit_phase_options
build_default_omit_rule_rows = _build_default_omit_rule_rows
build_equipment_mapping_rows = _build_equipment_mapping_rows
build_equipment_rate_rows = _build_equipment_rate_rows
build_labor_mapping_rows = _build_labor_mapping_rows
build_labor_rate_rows = _build_labor_rate_rows
build_slot_label_rename_map = _build_slot_label_rename_map
dedupe_casefold_preserving_order = _dedupe_casefold_preserving_order
normalize_phase_option_rows = _normalize_phase_option_rows
rename_equipment_mapping_config_targets = _rename_equipment_mapping_config_targets
rename_labor_mapping_config_targets = _rename_labor_mapping_config_targets
rename_rates_config_targets = _rename_rates_config_targets
rename_recap_template_map_targets = _rename_recap_template_map_targets
validate_equipment_classification_references = _validate_equipment_classification_references
validate_labor_classification_references = _validate_labor_classification_references
validate_slot_rows = _validate_slot_rows
