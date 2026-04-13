"""View-model for profile settings and lightweight admin actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import ConfigLoader, ProfileManager
from services.profile_bundle_helpers import (
    build_default_omit_phase_options,
    build_default_omit_rule_rows,
    build_classification_bundle_edit_result,
    build_default_omit_rules_config,
    build_equipment_mapping_config,
    build_equipment_mapping_rows,
    build_equipment_rate_rows,
    build_labor_mapping_config,
    build_labor_mapping_rows,
    build_labor_rate_rows,
    build_rates_config,
    dedupe_casefold_preserving_order,
    merge_observed_equipment_raw_values,
    merge_observed_labor_raw_values,
    normalize_phase_option_rows,
)



class SettingsWorkflowService:
    """Coordinate profile discovery, switching, duplication, and config editing."""

    def __init__(self, profile_manager: ProfileManager | None = None) -> None:
        self._profile_manager = profile_manager or ProfileManager()
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
        self._default_omit_rule_rows: list[dict[str, str]] = []
        self._available_default_omit_phase_options: list[dict[str, str]] = []
        self._observed_phase_options: list[dict[str, str]] = []
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

    @property
    def default_omit_rule_rows(self) -> list[dict[str, str]]:
        """Return editable default-omit phase rules for the active profile."""
        return [dict(row) for row in self._default_omit_rule_rows]

    @property
    def available_default_omit_phase_options(self) -> list[dict[str, str]]:
        """Return known phase-code options for the default-omit editor."""
        return [dict(row) for row in self._available_default_omit_phase_options]

    def reload(self) -> None:
        """Reload profile discovery and active profile config data."""
        self._profiles = self._profile_manager.list_profiles()
        self._active_profile = self._build_active_profile_summary()
        self._reload_active_profile_config_data()

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

    def set_observed_phase_options(self, values: list[dict[str, str]]) -> bool:
        """Update temporary observed phase options used by the default-omit editor."""
        observed_values = normalize_phase_option_rows(values)
        if observed_values == self._observed_phase_options:
            return False
        self._observed_phase_options = observed_values
        self._reload_active_profile_config_data()
        return True

    def set_observed_labor_raw_values(self, values: list[str]) -> bool:
        """Update temporary observed labor raw values used as mapping candidates."""
        observed_values = dedupe_casefold_preserving_order(values)
        if observed_values == self._observed_labor_raw_values:
            return False
        self._observed_labor_raw_values = observed_values
        self._reload_active_profile_config_data()
        return True

    def set_observed_equipment_raw_values(self, values: list[str]) -> bool:
        """Update temporary observed equipment descriptions used as mapping candidates."""
        observed_values = dedupe_casefold_preserving_order(values)
        if observed_values == self._observed_equipment_raw_values:
            return False
        self._observed_equipment_raw_values = observed_values
        self._reload_active_profile_config_data()
        return True

    def save_default_omit_rules(self, rows: list[dict[str, str]]) -> str:
        """Validate and persist default-omit phase rules for the active profile."""
        self._ensure_active_profile_is_editable()
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_config = loader.get_review_rules()
        new_config = build_default_omit_rules_config(existing_config, rows)
        _write_json_file(profile_dir / "review_rules.json", new_config)
        clear_profile_dependent_caches()
        self.reload()
        return "Default omit rules saved. Reprocess the current PDF to apply them to loaded records."

    def save_labor_mappings(self, rows: list[dict[str, str]]) -> str:
        """Validate and persist labor mapping rows for the active profile."""
        self._ensure_active_profile_is_editable()
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_config = loader.get_labor_mapping()
        new_config = build_labor_mapping_config(
            existing_config,
            rows,
            valid_targets=self._labor_classifications,
        )
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
        new_config = build_equipment_mapping_config(
            existing_config,
            rows,
            valid_targets=self._equipment_classifications,
        )
        _write_json_file(profile_dir / "equipment_mapping.json", new_config)
        clear_profile_dependent_caches()
        self.reload()
        return "Equipment mappings saved successfully."

    def save_classification_slots(
        self,
        labor_slots: list[dict[str, Any]],
        equipment_slots: list[dict[str, Any]],
    ) -> str:
        """Validate and persist fixed classification slot edits for the active profile."""
        self._ensure_active_profile_is_editable()

        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        bundle_edit_result = build_classification_bundle_edit_result(
            existing_labor_slots=self._labor_slots,
            updated_labor_slots=labor_slots,
            existing_equipment_slots=self._equipment_slots,
            updated_equipment_slots=equipment_slots,
            labor_mapping_rows=self._labor_mapping_rows,
            equipment_mapping_rows=self._equipment_mapping_rows,
            labor_rate_rows=self._labor_rate_rows,
            equipment_rate_rows=self._equipment_rate_rows,
            labor_mapping_config=loader.get_labor_mapping(),
            equipment_mapping_config=loader.get_equipment_mapping(),
            rates_config=loader.get_rates(),
            recap_template_map=loader.get_recap_template_map(),
            template_metadata=loader.get_template_metadata(),
        )

        _write_json_files(
            {
                profile_dir / "target_labor_classifications.json": bundle_edit_result.labor_slots_config,
                profile_dir / "target_equipment_classifications.json": bundle_edit_result.equipment_slots_config,
                profile_dir / "labor_mapping.json": bundle_edit_result.labor_mapping_config,
                profile_dir / "equipment_mapping.json": bundle_edit_result.equipment_mapping_config,
                profile_dir / "rates.json": bundle_edit_result.rates_config,
                profile_dir / "recap_template_map.json": bundle_edit_result.recap_template_map,
            }
        )
        clear_profile_dependent_caches()
        self.reload()

        if bundle_edit_result.labor_rename_map or bundle_edit_result.equipment_rename_map:
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
        new_rates = build_rates_config(
            existing_rates,
            labor_rows,
            equipment_rows,
            valid_labor_targets=self._labor_classifications,
            valid_equipment_targets=self._equipment_classifications,
        )
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
        phase_catalog = loader.get_phase_catalog()
        review_rules = loader.get_review_rules()
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
        self._labor_mapping_rows = build_labor_mapping_rows(
            labor_mapping,
            observed_raw_values=self._observed_labor_raw_values,
        )
        self._equipment_mapping_rows = build_equipment_mapping_rows(
            equipment_mapping,
            observed_raw_descriptions=self._observed_equipment_raw_values,
        )
        self._available_default_omit_phase_options = build_default_omit_phase_options(
            catalog_phase_rows=phase_catalog.get("phases", []),
            saved_rule_rows=review_rules.get("default_omit_rules", []),
            observed_phase_options=self._observed_phase_options,
        )
        self._default_omit_rule_rows = build_default_omit_rule_rows(
            review_rules,
            phase_options=self._available_default_omit_phase_options,
        )
        self._labor_rate_rows = build_labor_rate_rows(rates, self._labor_classifications)
        self._equipment_rate_rows = build_equipment_rate_rows(rates, self._equipment_classifications)

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
    ConfigLoader.clear_runtime_caches()



def persist_observed_labor_raw_values(profile_dir: Path, observed_raw_values: list[str]) -> bool:
    """Persist newly observed labor raw values as unmapped saved-mapping placeholders."""
    if profile_dir.name.strip().casefold() == "default":
        return False

    observed_values = dedupe_casefold_preserving_order(observed_raw_values)
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

    updated_mapping, did_update = merge_observed_labor_raw_values(labor_mapping, observed_values)
    if not did_update:
        return False

    _write_json_file(config_path, updated_mapping)
    clear_profile_dependent_caches()
    return True


def persist_observed_equipment_raw_values(profile_dir: Path, observed_raw_descriptions: list[str]) -> bool:
    """Persist newly observed equipment descriptions as unmapped saved-mapping placeholders."""
    if profile_dir.name.strip().casefold() == "default":
        return False

    observed_values = dedupe_casefold_preserving_order(observed_raw_descriptions)
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

    updated_mapping, did_update = merge_observed_equipment_raw_values(equipment_mapping, observed_values)
    if not did_update:
        return False

    _write_json_file(config_path, updated_mapping)
    clear_profile_dependent_caches()
    return True


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
