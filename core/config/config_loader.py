"""Config loading utilities for the Job Cost Tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from job_cost_tool.core.config.classification_slots import build_slot_lookup, get_active_slots, normalize_slot_config
from job_cost_tool.core.equipment_keys import derive_equipment_mapping_key
from job_cost_tool.core.config.path_utils import get_legacy_config_root
from job_cost_tool.core.config.profile_manager import ProfileManager


JsonDict = dict[str, Any]


class ConfigLoader:
    """Load and cache JSON configuration files for the application.

    The loader keeps parsing, normalization, and recap-mapping behavior in
    external JSON files so new companies, report formats, and rule sets can be
    introduced without hardcoding those details in Python.
    """

    _required_files: ClassVar[dict[str, str]] = {
        "labor_mapping": "labor_mapping.json",
        "equipment_mapping": "equipment_mapping.json",
        "phase_mapping": "phase_mapping.json",
        "vendor_normalization": "vendor_normalization.json",
        "input_model": "input_model.json",
        "recap_template_map": "recap_template_map.json",
        "target_labor_classifications": "target_labor_classifications.json",
        "target_equipment_classifications": "target_equipment_classifications.json",
        "rates": "rates.json",
    }
    _required_top_level_keys: ClassVar[dict[str, tuple[str, ...]]] = {
        "input_model": ("report_type", "section_headers"),
        "recap_template_map": (
            "worksheet_name",
            "header_fields",
            "labor_rows",
            "equipment_rows",
            "materials_section",
            "subcontractors_section",
            "permits_fees_section",
            "police_detail_section",
        ),
    }
    _shared_cache: ClassVar[dict[Path, dict[str, JsonDict]]] = {}

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize the loader using an explicit config dir or the active profile."""
        if config_dir is not None:
            self._config_dir = config_dir.resolve()
        else:
            self._config_dir = ProfileManager().get_active_profile_dir()
        self._legacy_config_dir = get_legacy_config_root().resolve()
        self._cache = self._shared_cache.setdefault(self._config_dir, {})

    def load_all_configs(self) -> None:
        """Load and cache all required configuration files."""
        self._validate_required_configs()
        for config_name in self._required_files:
            self._load_config(config_name)

    def get_labor_mapping(self) -> JsonDict:
        """Return the labor class normalization mapping."""
        return self._load_config("labor_mapping")

    def get_equipment_mapping(self) -> JsonDict:
        """Return the equipment description normalization mapping."""
        return self._load_config("equipment_mapping")

    def get_phase_mapping(self) -> JsonDict:
        """Return the phase mapping configuration."""
        return self._load_config("phase_mapping")

    def get_vendor_normalization(self) -> JsonDict:
        """Return the vendor normalization mapping."""
        return self._load_config("vendor_normalization")

    def get_input_model(self) -> JsonDict:
        """Return the input report interpretation model."""
        return self._load_config("input_model")

    def get_recap_template_map(self) -> JsonDict:
        """Return the recap template mapping configuration."""
        return self._load_config("recap_template_map")

    def get_labor_slots(self) -> JsonDict:
        """Return fixed-capacity labor slot definitions for the active profile."""
        return self._load_config("target_labor_classifications")

    def get_equipment_slots(self) -> JsonDict:
        """Return fixed-capacity equipment slot definitions for the active profile."""
        return self._load_config("target_equipment_classifications")

    def get_active_labor_slots(self) -> list[JsonDict]:
        """Return the active labor slots for the current profile."""
        return get_active_slots(self.get_labor_slots(), slot_prefix="labor")

    def get_active_equipment_slots(self) -> list[JsonDict]:
        """Return the active equipment slots for the current profile."""
        return get_active_slots(self.get_equipment_slots(), slot_prefix="equipment")

    def get_labor_slot_lookup(self) -> JsonDict:
        """Return a case-insensitive lookup from active labor label to slot metadata."""
        return build_slot_lookup(self.get_active_labor_slots())

    def get_equipment_slot_lookup(self) -> JsonDict:
        """Return a case-insensitive lookup from active equipment label to slot metadata."""
        return build_slot_lookup(self.get_active_equipment_slots())

    def get_labor_row_slots(self) -> JsonDict:
        """Return fixed labor recap row mappings keyed by stable slot id."""
        return self._build_row_slot_mapping("labor", self.get_labor_slots(), "labor_rows")

    def get_equipment_row_slots(self) -> JsonDict:
        """Return fixed equipment recap row mappings keyed by stable slot id."""
        return self._build_row_slot_mapping("equipment", self.get_equipment_slots(), "equipment_rows")

    def get_target_labor_classifications(self) -> JsonDict:
        """Return the active labor recap classifications derived from labor slots."""
        return self.get_labor_slots()

    def get_target_equipment_classifications(self) -> JsonDict:
        """Return the active equipment recap classifications derived from equipment slots."""
        return self.get_equipment_slots()

    def get_rates(self) -> JsonDict:
        """Return the configured rates bundle for the active profile."""
        return self._load_config("rates")

    def get_active_profile_name(self) -> str:
        """Return the active profile name currently in use."""
        profile_dir = self._config_dir
        if profile_dir == self._legacy_config_dir:
            return "default"
        profile_file = profile_dir / "profile.json"
        if profile_file.is_file():
            metadata = ProfileManager().get_active_profile_metadata()
            return str(metadata.get("profile_name", "default"))
        return "default"

    def get_profile_metadata(self) -> JsonDict:
        """Return metadata describing the active profile."""
        metadata = ProfileManager().get_active_profile_metadata()
        return {str(key): value for key, value in metadata.items()}

    def get_template_path(self) -> Path:
        """Return the recap template path for the active profile."""
        profile_metadata = self.get_profile_metadata()
        template_filename = str(profile_metadata.get("template_filename") or "").strip()
        if template_filename:
            template_path = (self._config_dir / template_filename).resolve()
            if template_path.is_file():
                return template_path

        recap_map = self.get_recap_template_map()
        configured_path = str(recap_map.get("default_template_path") or "").strip()
        if configured_path:
            template_path = Path(configured_path).expanduser().resolve()
            if template_path.is_file():
                return template_path

        raise FileNotFoundError(
            f"No recap template workbook could be resolved for config bundle '{self._config_dir}'."
        )

    def _validate_required_configs(self) -> None:
        """Ensure all required config files are present on disk."""
        missing_files = [
            file_name
            for file_name in self._required_files.values()
            if not (self._config_dir / file_name).is_file()
        ]
        if missing_files:
            missing_list = ", ".join(sorted(missing_files))
            raise FileNotFoundError(
                f"Missing required config file(s) in '{self._config_dir}': {missing_list}"
            )

    def _load_config(self, config_name: str) -> JsonDict:
        """Load a config file once and reuse it from the shared cache."""
        if config_name not in self._required_files:
            raise KeyError(f"Unsupported config name '{config_name}'")

        if config_name in self._cache:
            return self._cache[config_name]

        file_name = self._required_files[config_name]
        file_path = self._config_dir / file_name
        if not file_path.is_file():
            raise FileNotFoundError(
                f"Required config '{config_name}' was not found at '{file_path}'"
            )

        try:
            with file_path.open("r", encoding="utf-8-sig") as config_file:
                loaded_config = json.load(config_file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Config file '{file_path}' contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(loaded_config, dict):
            raise ValueError(
                f"Config file '{file_path}' must contain a JSON object at the top level"
            )

        self._validate_top_level_structure(config_name, file_path, loaded_config)
        normalized_config = self._normalize_loaded_config(config_name, loaded_config)
        self._cache[config_name] = normalized_config
        return normalized_config


    def _normalize_loaded_config(self, config_name: str, loaded_config: JsonDict) -> JsonDict:
        """Normalize compatible config formats into the app's current in-memory shape."""
        if config_name == "labor_mapping":
            return self._normalize_labor_mapping_config(loaded_config)
        if config_name == "equipment_mapping":
            return self._normalize_equipment_mapping_config(loaded_config)
        if config_name == "target_labor_classifications":
            capacity, template_labels = self._get_slot_context("labor_rows")
            return normalize_slot_config(
                loaded_config,
                slot_prefix="labor",
                capacity=capacity,
                template_labels=template_labels,
            )
        if config_name == "target_equipment_classifications":
            capacity, template_labels = self._get_slot_context("equipment_rows")
            return normalize_slot_config(
                loaded_config,
                slot_prefix="equipment",
                capacity=capacity,
                template_labels=template_labels,
            )
        return loaded_config

    def _normalize_labor_mapping_config(self, loaded_config: JsonDict) -> JsonDict:
        """Normalize raw-first labor mapping config while tolerating legacy fields."""
        normalized_config = dict(loaded_config)

        raw_mappings = loaded_config.get("raw_mappings", {}) if isinstance(loaded_config.get("raw_mappings"), dict) else {}
        normalized_raw_mappings: JsonDict = {}
        for raw_key, target_classification in raw_mappings.items():
            canonical_raw_key = " ".join(str(raw_key).strip().upper().split()).replace("APPRENTICESHIP", "APP")
            target_text = str(target_classification).strip()
            if canonical_raw_key and target_text:
                normalized_raw_mappings[canonical_raw_key] = target_text

        saved_mappings = loaded_config.get("saved_mappings", []) if isinstance(loaded_config.get("saved_mappings"), list) else []
        normalized_saved_rows: list[JsonDict] = []
        seen_raw_values: set[str] = set()
        for row in saved_mappings:
            if not isinstance(row, dict):
                continue
            canonical_raw_key = " ".join(str(row.get("raw_value", "")).strip().upper().split()).replace("APPRENTICESHIP", "APP")
            if not canonical_raw_key:
                continue
            normalized_raw = canonical_raw_key.casefold()
            if normalized_raw in seen_raw_values:
                continue
            seen_raw_values.add(normalized_raw)
            normalized_saved_rows.append(
                {
                    "raw_value": canonical_raw_key,
                    "target_classification": str(row.get("target_classification", "")).strip(),
                    "notes": str(row.get("notes", "")).strip(),
                }
            )

        if not normalized_saved_rows and normalized_raw_mappings:
            normalized_saved_rows = [
                {
                    "raw_value": raw_key,
                    "target_classification": target_classification,
                    "notes": "",
                }
                for raw_key, target_classification in normalized_raw_mappings.items()
            ]
        if not normalized_raw_mappings and normalized_saved_rows:
            normalized_raw_mappings = {
                str(row.get("raw_value", "")).strip(): str(row.get("target_classification", "")).strip()
                for row in normalized_saved_rows
                if str(row.get("target_classification", "")).strip()
            }

        normalized_config["raw_mappings"] = normalized_raw_mappings
        normalized_config["saved_mappings"] = normalized_saved_rows
        return normalized_config

    def _normalize_equipment_mapping_config(self, loaded_config: JsonDict) -> JsonDict:
        """Normalize raw-first equipment mapping config while tolerating legacy keyword mappings.

        raw_mappings and saved_mappings are the intended persisted source of
        truth. keyword_mappings is synthesized only as an in-memory
        compatibility view when older runtime fallback still expects it.
        """
        normalized_config = dict(loaded_config)

        raw_mappings = loaded_config.get("raw_mappings", {}) if isinstance(loaded_config.get("raw_mappings"), dict) else {}
        normalized_raw_mappings: JsonDict = {}
        for raw_description, target_category in raw_mappings.items():
            canonical_raw_description = derive_equipment_mapping_key(str(raw_description).strip()) or ""
            target_text = str(target_category).strip()
            if canonical_raw_description and target_text:
                normalized_raw_mappings[canonical_raw_description] = target_text

        saved_mappings = loaded_config.get("saved_mappings", []) if isinstance(loaded_config.get("saved_mappings"), list) else []
        normalized_saved_rows: list[JsonDict] = []
        seen_raw_descriptions: set[str] = set()
        for row in saved_mappings:
            if not isinstance(row, dict):
                continue
            canonical_raw_description = derive_equipment_mapping_key(str(row.get("raw_description", "")).strip()) or ""
            if not canonical_raw_description:
                continue
            normalized_raw = canonical_raw_description.casefold()
            if normalized_raw in seen_raw_descriptions:
                continue
            seen_raw_descriptions.add(normalized_raw)
            normalized_saved_rows.append(
                {
                    "raw_description": canonical_raw_description,
                    "target_category": str(row.get("target_category", "")).strip(),
                }
            )

        keyword_mappings = loaded_config.get("keyword_mappings", {}) if isinstance(loaded_config.get("keyword_mappings"), dict) else {}
        normalized_keyword_mappings: JsonDict = {}
        for raw_description, target_category in keyword_mappings.items():
            canonical_raw_description = derive_equipment_mapping_key(str(raw_description).strip()) or ""
            target_text = str(target_category).strip()
            if canonical_raw_description and target_text:
                normalized_keyword_mappings[canonical_raw_description] = target_text

        if not normalized_raw_mappings and normalized_saved_rows:
            normalized_raw_mappings = {
                str(row.get("raw_description", "")).strip(): str(row.get("target_category", "")).strip()
                for row in normalized_saved_rows
                if str(row.get("target_category", "")).strip()
            }
        if not normalized_raw_mappings and normalized_keyword_mappings:
            normalized_raw_mappings = dict(normalized_keyword_mappings)

        if not normalized_saved_rows and normalized_raw_mappings:
            normalized_saved_rows = [
                {
                    "raw_description": raw_description,
                    "target_category": target_category,
                }
                for raw_description, target_category in normalized_raw_mappings.items()
            ]

        if not normalized_keyword_mappings and normalized_raw_mappings:
            normalized_keyword_mappings = dict(normalized_raw_mappings)

        # Keep keyword_mappings as a compatibility-only in-memory mirror for
        # the temporary runtime fallback. The persisted config no longer needs
        # to write it as a co-primary mapping model.
        normalized_config["raw_mappings"] = normalized_raw_mappings
        normalized_config["saved_mappings"] = normalized_saved_rows
        normalized_config["keyword_mappings"] = normalized_keyword_mappings
        return normalized_config

    def _get_slot_context(self, recap_key: str) -> tuple[int, list[str]]:
        """Return slot capacity and row-label order from the recap template map."""
        recap_map = self.get_recap_template_map()
        row_mapping = recap_map.get(recap_key, {}) if isinstance(recap_map.get(recap_key), dict) else {}
        template_labels = [str(label).strip() for label in row_mapping.keys() if str(label).strip()]
        capacity = len(template_labels)
        return capacity, template_labels

    def _build_row_slot_mapping(
        self,
        slot_prefix: str,
        slot_config: JsonDict,
        recap_key: str,
    ) -> JsonDict:
        """Build a stable slot-id to recap-row mapping using fixed row order."""
        recap_map = self.get_recap_template_map()
        raw_rows = recap_map.get(recap_key, {}) if isinstance(recap_map.get(recap_key), dict) else {}
        normalized_slots = slot_config.get("slots", []) if isinstance(slot_config.get("slots"), list) else []

        row_items = list(raw_rows.items())
        if normalized_slots and len(row_items) < len(normalized_slots):
            raise ValueError(
                f"Recap template map '{recap_key}' does not have enough fixed rows for the configured slot capacity."
            )

        slot_rows: JsonDict = {}
        for index, slot in enumerate(normalized_slots):
            if not isinstance(slot, dict) or index >= len(row_items):
                continue
            template_label, row_mapping = row_items[index]
            slot_id = str(slot.get("slot_id") or f"{slot_prefix}_{index + 1}").strip() or f"{slot_prefix}_{index + 1}"
            slot_rows[slot_id] = {
                "slot_id": slot_id,
                "label": str(slot.get("label", "")).strip(),
                "active": bool(slot.get("active")),
                "template_label": str(template_label).strip(),
                "mapping": dict(row_mapping) if isinstance(row_mapping, dict) else {},
            }
        return slot_rows


    def _validate_top_level_structure(
        self,
        config_name: str,
        file_path: Path,
        loaded_config: JsonDict,
    ) -> None:
        """Validate only the expected top-level structure of a config."""
        required_keys = self._required_top_level_keys.get(config_name, ())
        for key in required_keys:
            if key not in loaded_config:
                raise ValueError(
                    f"Config file '{file_path}' is missing required top-level key '{key}'"
                )

        if config_name == "labor_mapping":
            if "raw_mappings" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "raw_mappings", dict, "object")
            if "saved_mappings" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "saved_mappings", list, "array")
        elif config_name == "equipment_mapping":
            if "raw_mappings" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "raw_mappings", dict, "object")
            if "saved_mappings" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "saved_mappings", list, "array")
            if "keyword_mappings" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "keyword_mappings", dict, "object")
        elif config_name == "input_model":
            self._validate_key_type(file_path, loaded_config, "report_type", str, "string")
            self._validate_key_type(file_path, loaded_config, "section_headers", dict, "object")
        elif config_name == "recap_template_map":
            if "default_template_path" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "default_template_path", str, "string")
            self._validate_key_type(file_path, loaded_config, "worksheet_name", str, "string")
            for key in (
                "header_fields",
                "labor_rows",
                "equipment_rows",
                "materials_section",
                "subcontractors_section",
                "permits_fees_section",
                "police_detail_section",
            ):
                self._validate_key_type(file_path, loaded_config, key, dict, "object")
        elif config_name in {
            "target_labor_classifications",
            "target_equipment_classifications",
        }:
            self._validate_classification_structure(file_path, loaded_config)

    def _validate_classification_structure(self, file_path: Path, loaded_config: JsonDict) -> None:
        """Validate slot-based or legacy list-based classification config structure."""
        if "slots" in loaded_config:
            self._validate_key_type(file_path, loaded_config, "slots", list, "array")
        elif "classifications" in loaded_config:
            self._validate_key_type(file_path, loaded_config, "classifications", list, "array")
        else:
            raise ValueError(
                f"Config file '{file_path}' must define either top-level key 'slots' or 'classifications'"
            )

    def _validate_key_type(
        self,
        file_path: Path,
        loaded_config: JsonDict,
        key: str,
        expected_type: type[Any],
        expected_label: str,
    ) -> None:
        """Validate a single top-level key type in a config file."""
        if not isinstance(loaded_config[key], expected_type):
            raise ValueError(
                f"Config file '{file_path}' has invalid top-level key '{key}': expected {expected_label}"
            )
