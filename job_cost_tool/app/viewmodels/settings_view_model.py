"""View-model for profile settings and lightweight admin actions."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from job_cost_tool.core.config import ConfigLoader, ProfileManager
from job_cost_tool.core.config.classification_slots import build_slot_config_from_rows



class SettingsViewModel(QObject):
    """Coordinate profile discovery, switching, duplication, and config editing."""

    state_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._profile_manager = ProfileManager()
        self._profiles: list[dict[str, Any]] = []
        self._active_profile: dict[str, Any] = {}
        self._labor_mapping_rows: list[dict[str, str]] = []
        self._equipment_mapping_rows: list[dict[str, str]] = []
        self._labor_slots: list[dict[str, Any]] = []
        self._equipment_slots: list[dict[str, Any]] = []
        self._labor_classifications: list[str] = []
        self._equipment_classifications: list[str] = []
        self._labor_rate_rows: list[dict[str, str]] = []
        self._equipment_rate_rows: list[dict[str, str]] = []
        self._observed_labor_raw_values: list[str] = []
        self._observed_equipment_raw_values: list[str] = []
        self.reload()

    @property
    def profiles(self) -> list[dict[str, Any]]:
        """Return discovered profile metadata for UI display."""
        return list(self._profiles)

    @property
    def active_profile(self) -> dict[str, Any]:
        """Return metadata for the current active profile."""
        return dict(self._active_profile)

    @property
    def labor_mapping_rows(self) -> list[dict[str, str]]:
        """Return editable labor mapping rows for the active profile."""
        return [dict(row) for row in self._labor_mapping_rows]

    @property
    def equipment_mapping_rows(self) -> list[dict[str, str]]:
        """Return editable equipment mapping rows for the active profile."""
        return [dict(row) for row in self._equipment_mapping_rows]

    @property
    def labor_slots(self) -> list[dict[str, Any]]:
        """Return fixed labor slot rows for the active profile."""
        return [dict(slot) for slot in self._labor_slots]

    @property
    def equipment_slots(self) -> list[dict[str, Any]]:
        """Return fixed equipment slot rows for the active profile."""
        return [dict(slot) for slot in self._equipment_slots]

    @property
    def labor_classifications(self) -> list[str]:
        """Return labor recap classifications for the active profile."""
        return list(self._labor_classifications)

    @property
    def equipment_classifications(self) -> list[str]:
        """Return equipment recap classifications for the active profile."""
        return list(self._equipment_classifications)

    @property
    def is_default_profile(self) -> bool:
        """Return True when the active profile is the built-in default profile."""
        profile_name = str(self._active_profile.get("profile_name", "")).strip().casefold()
        return profile_name == "default"

    @property
    def is_default_profile_locked(self) -> bool:
        """Return True when the default profile is selected and still locked for editing."""
        return self.is_default_profile and not self._profile_manager.is_default_profile_unlocked()

    @property
    def is_active_profile_editable(self) -> bool:
        """Return True when the active profile may be edited in settings."""
        return not self.is_default_profile_locked

    @property
    def is_default_profile_unlocked(self) -> bool:
        """Return True when the built-in default profile has been explicitly unlocked."""
        return self._profile_manager.is_default_profile_unlocked()

    @property
    def read_only_message(self) -> str:
        """Return the standard read-only message for the locked default profile."""
        return "Default profile is locked. Unlock it to make changes."

    @property
    def labor_rate_rows(self) -> list[dict[str, str]]:
        """Return editable labor rate rows for the active profile."""
        return [dict(row) for row in self._labor_rate_rows]

    @property
    def equipment_rate_rows(self) -> list[dict[str, str]]:
        """Return editable equipment rate rows for the active profile."""
        return [dict(row) for row in self._equipment_rate_rows]

    def reload(self) -> None:
        """Reload profile discovery and active profile config data."""
        self._profiles = self._profile_manager.list_profiles()
        self._active_profile = self._build_active_profile_summary()
        self._reload_active_profile_config_data()
        self.state_changed.emit()

    def set_active_profile(self, profile_name: str) -> str:
        """Set the selected profile as active and clear profile-dependent caches."""
        self._profile_manager.set_active_profile(profile_name)
        clear_profile_dependent_caches()
        self.reload()
        active_profile = self.active_profile
        return (
            f"Active profile changed to {active_profile.get('display_name', profile_name)}. "
            "Reload or reprocess the current PDF to apply the new profile bundle to loaded records."
        )

    def duplicate_profile(
        self,
        source_profile_name: str,
        new_profile_name: str,
        display_name: str,
        description: str = "",
    ) -> str:
        """Duplicate an existing profile bundle into a new profile."""
        metadata = self._profile_manager.duplicate_profile(
            source_profile_name=source_profile_name,
            new_profile_name=new_profile_name,
            display_name=display_name,
            description=description,
        )
        self.reload()
        return (
            f"Created profile {metadata.get('display_name', new_profile_name)} "
            f"({metadata.get('profile_name', new_profile_name)})."
        )

    def delete_profile(self, profile_name: str) -> str:
        """Delete a non-default, non-active profile and refresh admin state."""
        metadata = self._profile_manager.get_profile_metadata(profile_name)
        self._profile_manager.delete_profile(profile_name)
        self.reload()
        return f"Deleted profile {metadata.get('display_name', profile_name)} ({metadata.get('profile_name', profile_name)})."

    def unlock_default_profile(self) -> str:
        """Unlock the built-in default profile for editing and persist that state."""
        self._profile_manager.set_default_profile_unlocked(True)
        self.reload()
        return "Default profile is now unlocked for editing."

    def lock_default_profile(self) -> str:
        """Re-lock the built-in default profile for editing and persist that state."""
        self._profile_manager.set_default_profile_unlocked(False)
        self.reload()
        return "Default profile has been locked."

    def set_observed_labor_raw_values(self, values: list[str]) -> None:
        """Update temporary observed labor raw values used as mapping candidates."""
        observed_values = _dedupe_casefold_preserving_order(values)
        if observed_values == self._observed_labor_raw_values:
            return
        self._observed_labor_raw_values = observed_values
        self._reload_active_profile_config_data()
        self.state_changed.emit()

    def set_observed_equipment_raw_values(self, values: list[str]) -> None:
        """Update temporary observed equipment descriptions used as mapping candidates."""
        observed_values = _dedupe_casefold_preserving_order(values)
        if observed_values == self._observed_equipment_raw_values:
            return
        self._observed_equipment_raw_values = observed_values
        self._reload_active_profile_config_data()
        self.state_changed.emit()

    def save_labor_mappings(self, rows: list[dict[str, str]]) -> str:
        """Validate and persist labor mapping rows for the active profile."""
        self._ensure_active_profile_is_editable()
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_config = loader.get_labor_mapping()
        valid_targets = set(self._labor_classifications)

        saved_mappings: list[dict[str, str]] = []
        seen_raw_keys: set[str] = set()

        for row in rows:
            raw_value = str(row.get("raw_value", "")).strip()
            target_classification = str(row.get("target_classification", "")).strip()
            note = str(row.get("notes", "")).strip()
            if not raw_value:
                raise ValueError("Labor mapping rows must include a raw value.")

            raw_key = _canonicalize_labor_token(raw_value)
            if raw_key in seen_raw_keys:
                raise ValueError(f"Duplicate labor mapping raw value '{raw_value}' is not allowed.")
            seen_raw_keys.add(raw_key)

            if target_classification and target_classification not in valid_targets:
                raise ValueError(
                    f"Labor mapping '{raw_value}' references unknown target classification '{target_classification}'."
                )

            saved_mappings.append(
                {
                    "raw_value": raw_key,
                    "target_classification": target_classification,
                    "notes": note,
                }
            )

        # Labor mapping persistence is now raw-first. Save exact admin rows and direct
        # raw lookups only, and stop regenerating legacy alias/group fields here.
        new_config = {
            key: value
            for key, value in dict(existing_config).items()
            if key not in {"aliases", "class_mappings", "mapping_notes"}
        }
        new_config["raw_mappings"] = _build_raw_mappings_from_rows(saved_mappings)
        new_config["saved_mappings"] = _normalize_saved_labor_mapping_rows(saved_mappings)

        _write_json_file(profile_dir / "labor_mapping.json", new_config)
        clear_profile_dependent_caches()
        self.reload()
        return "Labor mappings saved successfully."

    def save_equipment_mappings(self, rows: list[dict[str, str]]) -> str:
        """Validate and persist raw-first equipment mapping rows for the active profile."""
        self._ensure_active_profile_is_editable()
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_config = loader.get_equipment_mapping()
        valid_targets = set(self._equipment_classifications)

        saved_mappings: list[dict[str, str]] = []
        seen_raw_descriptions: set[str] = set()

        for row in rows:
            raw_description = str(row.get("raw_description") or row.get("raw_pattern") or "").strip()
            target_category = str(row.get("target_category", "")).strip()
            if not raw_description:
                raise ValueError("Equipment mapping rows must include a raw description.")
            if target_category and target_category not in valid_targets:
                raise ValueError(
                    f"Equipment mapping '{raw_description}' references unknown target category '{target_category}'."
                )

            canonical_raw_description = _canonicalize_equipment_description(raw_description)
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
                }
            )

        # Equipment mapping persistence is now raw-first. Save exact admin rows
        # and direct raw lookups only; ConfigLoader can still synthesize an
        # in-memory keyword_mappings compatibility view for the current runtime fallback.
        new_config = {
            key: value
            for key, value in dict(existing_config).items()
            if key != "keyword_mappings"
        }
        new_config["raw_mappings"] = _build_raw_equipment_mappings_from_rows(saved_mappings)
        new_config["saved_mappings"] = _normalize_saved_equipment_mapping_rows(saved_mappings)
        _write_json_file(profile_dir / "equipment_mapping.json", new_config)
        clear_profile_dependent_caches()
        self.reload()
        return "Equipment mappings saved successfully."

    def save_classifications(self, labor_classifications: list[str], equipment_classifications: list[str]) -> str:
        """Persist active classifications using the current fixed slot order."""
        labor_slots = _merge_active_labels_into_slots(self._labor_slots, labor_classifications)
        equipment_slots = _merge_active_labels_into_slots(self._equipment_slots, equipment_classifications)
        return self.save_classification_slots(labor_slots, equipment_slots)

    def save_classification_slots(
        self,
        labor_slots: list[dict[str, Any]],
        equipment_slots: list[dict[str, Any]],
    ) -> str:
        """Validate and persist fixed classification slot edits for the active profile."""
        self._ensure_active_profile_is_editable()

        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        validated_labor_slots = _validate_slot_rows(
            labor_slots,
            existing_slots=self._labor_slots,
            slot_label="Labor",
        )
        validated_equipment_slots = _validate_slot_rows(
            equipment_slots,
            existing_slots=self._equipment_slots,
            slot_label="Equipment",
        )

        validated_labor = _active_labels_from_slots(validated_labor_slots)
        validated_equipment = _active_labels_from_slots(validated_equipment_slots)

        labor_rename_map = _build_slot_label_rename_map(self._labor_slots, validated_labor_slots)
        equipment_rename_map = _build_slot_label_rename_map(self._equipment_slots, validated_equipment_slots)

        remapped_labor_rows = _apply_label_renames_to_rows(
            self._labor_mapping_rows,
            "target_classification",
            labor_rename_map,
        )
        remapped_equipment_rows = _apply_label_renames_to_rows(
            self._equipment_mapping_rows,
            "target_category",
            equipment_rename_map,
        )
        remapped_labor_rate_rows = _apply_label_renames_to_rows(
            self._labor_rate_rows,
            "classification",
            labor_rename_map,
        )
        remapped_equipment_rate_rows = _apply_label_renames_to_rows(
            self._equipment_rate_rows,
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

        updated_labor_mapping = _rename_labor_mapping_config_targets(
            loader.get_labor_mapping(),
            labor_rename_map,
        )
        updated_equipment_mapping = _rename_equipment_mapping_config_targets(
            loader.get_equipment_mapping(),
            equipment_rename_map,
        )
        updated_rates = _rename_rates_config_targets(
            loader.get_rates(),
            labor_rename_map,
            equipment_rename_map,
        )
        updated_recap_template_map = _rename_recap_template_map_targets(
            loader.get_recap_template_map(),
            labor_rename_map,
            equipment_rename_map,
        )

        updated_labor_slots = build_slot_config_from_rows(validated_labor_slots)
        updated_equipment_slots = build_slot_config_from_rows(validated_equipment_slots)

        _write_json_files(
            {
                profile_dir / "target_labor_classifications.json": updated_labor_slots,
                profile_dir / "target_equipment_classifications.json": updated_equipment_slots,
                profile_dir / "labor_mapping.json": updated_labor_mapping,
                profile_dir / "equipment_mapping.json": updated_equipment_mapping,
                profile_dir / "rates.json": updated_rates,
                profile_dir / "recap_template_map.json": updated_recap_template_map,
            }
        )
        clear_profile_dependent_caches()
        self.reload()

        if labor_rename_map or equipment_rename_map:
            return "Target classifications saved successfully. Updated classification references in mappings, rates, and recap row mappings."
        return "Target classifications saved successfully."

    def save_rates(
        self,
        labor_rows: list[dict[str, str]],
        equipment_rows: list[dict[str, str]],
    ) -> str:
        """Validate and persist labor and equipment rates for the active profile."""
        self._ensure_active_profile_is_editable()
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_rates = loader.get_rates()

        valid_labor_targets = set(self._labor_classifications)
        valid_equipment_targets = set(self._equipment_classifications)

        labor_rates: dict[str, dict[str, float]] = {}
        for row in labor_rows:
            classification = str(row.get("classification", "")).strip()
            if not classification:
                continue
            if classification not in valid_labor_targets:
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
            if category not in valid_equipment_targets:
                raise ValueError(f"Unknown equipment rate category '{category}'.")
            rate = _parse_optional_rate(row.get("rate"), f"{category} equipment rate")
            if rate is None:
                continue
            equipment_rates[category] = {"rate": rate}

        new_rates = dict(existing_rates)
        new_rates["labor_rates"] = labor_rates
        new_rates["equipment_rates"] = equipment_rates
        _write_json_file(profile_dir / "rates.json", new_rates)
        clear_profile_dependent_caches()
        self.reload()
        return "Rates saved successfully."

    def _reload_active_profile_config_data(self) -> None:
        """Reload active-profile config tables and lists."""
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        labor_mapping = loader.get_labor_mapping()
        equipment_mapping = loader.get_equipment_mapping()
        rates = loader.get_rates()

        labor_slots_config = loader.get_labor_slots()
        equipment_slots_config = loader.get_equipment_slots()

        self._labor_slots = [dict(slot) for slot in labor_slots_config.get("slots", []) if isinstance(slot, dict)]
        self._equipment_slots = [dict(slot) for slot in equipment_slots_config.get("slots", []) if isinstance(slot, dict)]
        self._labor_classifications = [
            str(item).strip()
            for item in labor_slots_config.get("classifications", [])
            if str(item).strip()
        ]
        self._equipment_classifications = [
            str(item).strip()
            for item in equipment_slots_config.get("classifications", [])
            if str(item).strip()
        ]
        self._labor_mapping_rows = _build_labor_mapping_rows(
            labor_mapping,
            observed_raw_values=self._observed_labor_raw_values,
        )
        self._equipment_mapping_rows = _build_equipment_mapping_rows(
            equipment_mapping,
            observed_raw_descriptions=self._observed_equipment_raw_values,
        )
        self._labor_rate_rows = _build_labor_rate_rows(rates, self._labor_classifications)
        self._equipment_rate_rows = _build_equipment_rate_rows(rates, self._equipment_classifications)

    def _build_active_profile_summary(self) -> dict[str, Any]:
        """Build an active-profile summary including template path details."""
        metadata = self._profile_manager.get_active_profile_metadata()
        profile_dir = Path(str(metadata.get("profile_dir", ""))).resolve()
        loader = ConfigLoader(config_dir=profile_dir) if profile_dir.exists() else ConfigLoader()
        try:
            template_path = loader.get_template_path()
        except Exception:
            template_path = None

        summary = dict(metadata)
        summary["template_path"] = str(template_path) if template_path else "-"
        summary["default_profile_locked"] = self.is_default_profile_locked
        summary["default_profile_unlocked"] = self.is_default_profile_unlocked
        return summary

    def _ensure_active_profile_is_editable(self) -> None:
        """Raise when the active profile is intentionally read-only."""
        if not self.is_active_profile_editable:
            raise ValueError(self.read_only_message)

    def _active_profile_dir(self) -> Path:
        """Return the active profile directory for profile-scoped editing."""
        profile_dir = self._profile_manager.get_active_profile_dir()
        if not profile_dir.is_dir():
            raise FileNotFoundError(f"Active profile directory was not found: {profile_dir}")
        return profile_dir


def clear_profile_dependent_caches() -> None:
    """Clear cached config-derived helpers so the active profile can switch safely."""
    ConfigLoader._shared_cache.clear()

    from job_cost_tool.core.export import recap_mapper
    from job_cost_tool.core.normalization import equipment_normalizer, labor_normalizer, material_normalizer, normalizer
    from job_cost_tool.core.parsing import line_classifier

    cache_functions = [
        line_classifier._get_input_model,
        line_classifier._get_transaction_types,
        line_classifier._get_ignore_patterns,
        line_classifier._get_section_headers,
        labor_normalizer._get_labor_mapping,
        labor_normalizer._get_target_labor_classifications,
        labor_normalizer._get_active_labor_slot_lookup,
        equipment_normalizer._get_equipment_mapping,
        equipment_normalizer._get_target_equipment_classifications,
        equipment_normalizer._get_active_equipment_slot_lookup,
        material_normalizer._get_vendor_normalization,
        normalizer._get_phase_mapping,
        recap_mapper._get_target_labor_classifications,
        recap_mapper._get_target_equipment_classifications,
        recap_mapper._get_active_labor_slots,
        recap_mapper._get_active_equipment_slots,
        recap_mapper._get_active_labor_slot_lookup,
        recap_mapper._get_active_equipment_slot_lookup,
        recap_mapper._get_rates,
    ]

    for cache_function in cache_functions:
        if hasattr(cache_function, "cache_clear"):
            cache_function.cache_clear()



def persist_observed_labor_raw_values(profile_dir: Path, observed_raw_values: list[str]) -> bool:
    """Persist newly observed labor raw values as unmapped saved-mapping placeholders."""
    if profile_dir.name.strip().casefold() == "default":
        return False

    observed_values = _dedupe_casefold_preserving_order(observed_raw_values)
    if not observed_values:
        return False

    config_path = profile_dir / "labor_mapping.json"
    if not config_path.is_file():
        return False

    try:
        with config_path.open("r", encoding="utf-8-sig") as config_file:
            labor_mapping = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(labor_mapping, dict):
        return False

    base_rows = _normalize_saved_labor_mapping_rows(
        _build_labor_mapping_rows(labor_mapping, observed_raw_values=None)
    )
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
            }
        )
        did_update = True

    if not did_update:
        return False

    updated_mapping = dict(labor_mapping)
    updated_mapping["saved_mappings"] = _normalize_saved_labor_mapping_rows(base_rows)
    _write_json_file(config_path, updated_mapping)
    clear_profile_dependent_caches()
    return True


def persist_observed_equipment_raw_values(profile_dir: Path, observed_raw_descriptions: list[str]) -> bool:
    """Persist newly observed equipment descriptions as unmapped saved-mapping placeholders."""
    if profile_dir.name.strip().casefold() == "default":
        return False

    observed_values = _dedupe_casefold_preserving_order(observed_raw_descriptions)
    if not observed_values:
        return False

    config_path = profile_dir / "equipment_mapping.json"
    if not config_path.is_file():
        return False

    try:
        with config_path.open("r", encoding="utf-8-sig") as config_file:
            equipment_mapping = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(equipment_mapping, dict):
        return False

    base_rows = _normalize_saved_equipment_mapping_rows(
        _build_equipment_mapping_rows(equipment_mapping)
    )
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
        canonical_raw_description = _canonicalize_equipment_description(raw_description)
        if not canonical_raw_description or canonical_raw_description.casefold() in seen_raw_descriptions:
            continue
        seen_raw_descriptions.add(canonical_raw_description.casefold())
        base_rows.append(
            {
                "raw_description": canonical_raw_description,
                "target_category": "",
            }
        )
        did_update = True

    if not did_update:
        return False

    updated_mapping = {
        key: value
        for key, value in dict(equipment_mapping).items()
        if key != "keyword_mappings"
    }
    updated_mapping["saved_mappings"] = _normalize_saved_equipment_mapping_rows(base_rows)
    updated_mapping["raw_mappings"] = _build_raw_equipment_mappings_from_rows(updated_mapping["saved_mappings"])
    _write_json_file(config_path, updated_mapping)
    clear_profile_dependent_caches()
    return True


def _build_labor_mapping_rows(
    labor_mapping: dict[str, Any],
    *,
    observed_raw_values: list[str] | None = None,
) -> list[dict[str, str]]:
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
            }
        )

    rows.sort(key=lambda row: (row["target_classification"].casefold(), row["raw_value"].casefold()))
    return rows


def _normalize_saved_labor_mapping_rows(saved_mappings: Any) -> list[dict[str, str]]:
    """Normalize saved labor editor rows while preserving blank unmapped placeholders."""
    if not isinstance(saved_mappings, list):
        return []

    normalized_rows: list[dict[str, str]] = []
    seen_raw_values: set[str] = set()
    for row in saved_mappings:
        if not isinstance(row, dict):
            continue
        raw_value = _canonicalize_labor_token(str(row.get("raw_value", "")).strip())
        if not raw_value:
            continue
        normalized_raw = raw_value.casefold()
        if normalized_raw in seen_raw_values:
            continue
        seen_raw_values.add(normalized_raw)
        normalized_rows.append(
            {
                "raw_value": raw_value,
                "target_classification": str(row.get("target_classification", "")).strip(),
                "notes": str(row.get("notes", "")).strip(),
            }
        )
    return normalized_rows


def _normalize_raw_labor_mappings(raw_mappings: Any) -> dict[str, str]:
    """Normalize direct raw labor mappings into canonical exact keys."""
    if not isinstance(raw_mappings, dict):
        return {}

    normalized_mappings: dict[str, str] = {}
    for raw_value, target_classification in raw_mappings.items():
        raw_key = _canonicalize_labor_token(str(raw_value).strip())
        target_text = str(target_classification).strip()
        if raw_key and target_text:
            normalized_mappings[raw_key] = target_text
    return normalized_mappings


def _build_saved_rows_from_raw_mappings(raw_mappings: dict[str, str]) -> list[dict[str, str]]:
    """Materialize raw mapping entries into admin-facing row data."""
    rows = [
        {
            "raw_value": raw_value,
            "target_classification": target_classification,
            "notes": "",
        }
        for raw_value, target_classification in raw_mappings.items()
    ]
    rows.sort(key=lambda row: (row["target_classification"].casefold(), row["raw_value"].casefold()))
    return rows


def _build_raw_mappings_from_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    """Build the exact persisted raw mapping lookup from saved editor rows."""
    raw_mappings: dict[str, str] = {}
    for row in rows:
        raw_value = _canonicalize_labor_token(str(row.get("raw_value", "")).strip())
        target_classification = str(row.get("target_classification", "")).strip()
        if raw_value and target_classification:
            raw_mappings[raw_value] = target_classification
    return raw_mappings

def _normalize_saved_equipment_mapping_rows(saved_mappings: Any) -> list[dict[str, str]]:
    """Normalize saved equipment editor rows while preserving blank unmapped placeholders."""
    if not isinstance(saved_mappings, list):
        return []

    normalized_rows: list[dict[str, str]] = []
    seen_raw_descriptions: set[str] = set()
    for row in saved_mappings:
        if not isinstance(row, dict):
            continue
        raw_description = _canonicalize_equipment_description(
            str(row.get("raw_description") or row.get("raw_pattern") or "").strip()
        )
        if not raw_description:
            continue
        normalized_raw = raw_description.casefold()
        if normalized_raw in seen_raw_descriptions:
            continue
        seen_raw_descriptions.add(normalized_raw)
        normalized_rows.append(
            {
                "raw_description": raw_description,
                "target_category": str(row.get("target_category", "")).strip(),
            }
        )
    return normalized_rows


def _normalize_raw_equipment_mappings(raw_mappings: Any) -> dict[str, str]:
    """Normalize direct raw equipment mappings into canonical exact keys."""
    if not isinstance(raw_mappings, dict):
        return {}

    normalized_mappings: dict[str, str] = {}
    for raw_description, target_category in raw_mappings.items():
        canonical_raw_description = _canonicalize_equipment_description(str(raw_description).strip())
        target_text = str(target_category).strip()
        if canonical_raw_description and target_text:
            normalized_mappings[canonical_raw_description] = target_text
    return normalized_mappings


def _build_saved_equipment_rows_from_raw_mappings(raw_mappings: dict[str, str]) -> list[dict[str, str]]:
    """Materialize raw equipment mapping entries into admin-facing row data."""
    rows = [
        {
            "raw_description": raw_description,
            "target_category": target_category,
        }
        for raw_description, target_category in raw_mappings.items()
    ]
    rows.sort(key=lambda row: (row["target_category"].casefold(), row["raw_description"].casefold()))
    return rows


def _build_raw_equipment_mappings_from_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    """Build the exact persisted raw equipment mapping lookup from saved editor rows."""
    raw_mappings: dict[str, str] = {}
    for row in rows:
        raw_description = _canonicalize_equipment_description(
            str(row.get("raw_description") or row.get("raw_pattern") or "").strip()
        )
        target_category = str(row.get("target_category", "")).strip()
        if raw_description and target_category:
            raw_mappings[raw_description] = target_category
    return raw_mappings

def _build_equipment_mapping_rows(
    equipment_mapping: dict[str, Any],
    *,
    observed_raw_descriptions: list[str] | None = None,
) -> list[dict[str, str]]:
    """Flatten raw-first equipment mapping rows and observed values into editor rows."""
    saved_rows = _normalize_saved_equipment_mapping_rows(equipment_mapping.get("saved_mappings", []))

    if saved_rows:
        rows = saved_rows
    else:
        raw_mappings = _normalize_raw_equipment_mappings(equipment_mapping.get("raw_mappings", {}))
        if raw_mappings:
            rows = _build_saved_equipment_rows_from_raw_mappings(raw_mappings)
        else:
            rows = _build_saved_equipment_rows_from_raw_mappings(
                _normalize_raw_equipment_mappings(equipment_mapping.get("keyword_mappings", {}))
            )

    seen_raw_descriptions = {
        str(row.get("raw_description", "")).strip().casefold()
        for row in rows
        if str(row.get("raw_description", "")).strip()
    }

    for raw_description in observed_raw_descriptions or []:
        raw_description_text = _canonicalize_equipment_description(str(raw_description).strip())
        if not raw_description_text or raw_description_text.casefold() in seen_raw_descriptions:
            continue
        seen_raw_descriptions.add(raw_description_text.casefold())
        rows.append(
            {
                "raw_description": raw_description_text,
                "target_category": "",
            }
        )

    rows.sort(key=lambda row: (row["target_category"].casefold(), row["raw_description"].casefold()))
    return [
        {
            "raw_description": str(row.get("raw_description", "")).strip(),
            "raw_pattern": str(row.get("raw_description", "")).strip(),
            "target_category": str(row.get("target_category", "")).strip(),
        }
        for row in rows
    ]


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


def _validate_unique_labels(values: list[str], label_name: str) -> list[str]:
    """Validate editable classification labels."""
    cleaned_values: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            raise ValueError(f"{label_name} values may not be empty.")
        normalized = value.casefold()
        if normalized in seen:
            raise ValueError(f"Duplicate {label_name.casefold()} '{value}' is not allowed.")
        seen.add(normalized)
        cleaned_values.append(value)
    return cleaned_values


def _build_label_rename_map(previous_labels: list[str], updated_labels: list[str]) -> dict[str, str]:
    """Build a best-effort rename map for in-place classification edits."""
    rename_map: dict[str, str] = {}
    matcher = SequenceMatcher(a=previous_labels, b=updated_labels, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag != "replace":
            continue
        old_segment = previous_labels[old_start:old_end]
        new_segment = updated_labels[new_start:new_end]
        if len(old_segment) != len(new_segment):
            continue
        for old_label, new_label in zip(old_segment, new_segment):
            if old_label != new_label:
                rename_map[old_label] = new_label
    return rename_map


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
        if key not in {"aliases", "class_mappings", "mapping_notes"}
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
            {
                "raw_value": str(row.get("raw_value", "")).strip(),
                "target_classification": rename_map.get(
                    str(row.get("target_classification", "")).strip(),
                    str(row.get("target_classification", "")).strip(),
                ),
                "notes": str(row.get("notes", "")).strip(),
            }
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
            {
                "raw_description": str(row.get("raw_description", "")).strip(),
                "target_category": rename_map.get(
                    str(row.get("target_category", "")).strip(),
                    str(row.get("target_category", "")).strip(),
                ),
            }
            for row in saved_rows
        ]

    keyword_mappings = _normalize_raw_equipment_mappings(equipment_mapping.get("keyword_mappings", {}))
    if keyword_mappings or "keyword_mappings" in equipment_mapping:
        updated_config["keyword_mappings"] = {
            raw_description: rename_map.get(target_category, target_category)
            for raw_description, target_category in keyword_mappings.items()
        }
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


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON safely to disk for profile-scoped config edits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    serialized = json.dumps(payload, indent=2)
    temp_path.write_text(serialized, encoding="utf-8")
    temp_path.replace(path)


def _write_json_files(payloads: dict[Path, dict[str, Any]]) -> None:
    """Write multiple JSON files using temp files before replacing originals."""
    temp_paths: list[tuple[Path, Path]] = []
    try:
        for path, payload in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            serialized = json.dumps(payload, indent=2)
            temp_path.write_text(serialized, encoding="utf-8")
            temp_paths.append((temp_path, path))
        for temp_path, path in temp_paths:
            temp_path.replace(path)
    finally:
        for temp_path, _ in temp_paths:
            if temp_path.exists():
                temp_path.unlink()


def _canonicalize_labor_token(value: str) -> str:
    """Canonicalize labor mapping tokens consistently with labor normalization."""
    collapsed = " ".join(str(value).strip().upper().split())
    return collapsed.replace("APPRENTICESHIP", "APP")


def _canonicalize_equipment_description(value: str) -> str:
    """Canonicalize raw equipment descriptions conservatively for raw-first matching."""
    return " ".join(str(value).strip().upper().split())


def _stringify_rate(value: Any) -> str:
    """Convert a saved rate value to a user-editable string."""
    if value in {None, ""}:
        return ""
    return str(value)
