"""Config loading utilities for the Job Cost Tool."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, ClassVar, Iterator

from core.config.classification_slots import build_slot_lookup, get_active_slots, normalize_slot_config
from core.config.export_settings import normalize_export_settings_config
from core.equipment_keys import derive_equipment_mapping_key
from core.phase_codes import canonicalize_phase_code
from core.review_defaults import normalize_review_rules_config
from core.config.template_metadata import build_template_metadata
from core.config.path_utils import get_legacy_config_root
from core.config.profile_manager import ProfileManager


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
    _optional_files: ClassVar[dict[str, str]] = {
        "review_rules": "review_rules.json",
        "export_settings": "export_settings.json",
        "template_metadata": "template_metadata.json",
    }
    _shared_optional_files: ClassVar[dict[str, str]] = {
        "phase_catalog": "phase_catalog.json",
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
    _explicit_context: ClassVar[ContextVar[tuple[Path, Path] | None]] = ContextVar(
        "job_cost_tool_explicit_config_context",
        default=None,
    )

    def __init__(
        self,
        config_dir: Path | None = None,
        *,
        legacy_config_dir: Path | None = None,
    ) -> None:
        """Initialize the loader using an explicit config dir or the active profile."""
        context_override = self._explicit_context.get()
        if config_dir is not None:
            self._config_dir = config_dir.resolve()
        elif context_override is not None:
            self._config_dir = context_override[0]
        else:
            self._config_dir = ProfileManager().get_active_profile_dir()
        if legacy_config_dir is not None:
            self._legacy_config_dir = legacy_config_dir.resolve()
        elif context_override is not None:
            self._legacy_config_dir = context_override[1]
        else:
            self._legacy_config_dir = get_legacy_config_root().resolve()
        self._cache = self._shared_cache.setdefault(self._config_dir, {})

    @classmethod
    @contextmanager
    def use_explicit_context(
        cls,
        *,
        config_dir: Path,
        legacy_config_dir: Path | None = None,
    ) -> Iterator[None]:
        """Temporarily bind implicit ConfigLoader() calls to one explicit config bundle."""
        resolved_context = (
            config_dir.resolve(),
            (legacy_config_dir or get_legacy_config_root()).resolve(),
        )
        token = cls._explicit_context.set(resolved_context)
        cls.clear_runtime_caches()
        try:
            yield
        finally:
            cls._explicit_context.reset(token)
            cls.clear_runtime_caches()

    @classmethod
    def clear_runtime_caches(cls) -> None:
        """Clear shared config caches plus module-level config-derived helper caches."""
        cls._shared_cache.clear()

        from core.export import recap_mapper
        from core.normalization import equipment_normalizer, labor_normalizer, material_normalizer, normalizer
        from core.parsing import line_classifier

        cache_functions = [
            line_classifier._get_input_model,
            line_classifier._get_phase_mapping,
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
            recap_mapper._get_labor_export_row_slots,
            recap_mapper._get_equipment_export_row_slots,
            recap_mapper._get_rates,
            recap_mapper._get_export_settings,
            recap_mapper._get_material_section_capacity,
        ]

        for cache_function in cache_functions:
            if hasattr(cache_function, "cache_clear"):
                cache_function.cache_clear()

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

    def get_template_metadata(self) -> JsonDict:
        """Return normalized template metadata for the active profile/config bundle."""
        return self._load_optional_config("template_metadata")

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
        """Return compacted labor export row mappings keyed by active slot id."""
        return self._build_export_row_mapping("labor", self.get_labor_slots(), "labor_rows")

    def get_equipment_row_slots(self) -> JsonDict:
        """Return compacted equipment export row mappings keyed by active slot id."""
        return self._build_export_row_mapping("equipment", self.get_equipment_slots(), "equipment_rows")

    def get_target_labor_classifications(self) -> JsonDict:
        """Return the active labor recap classifications derived from labor slots."""
        return self.get_labor_slots()

    def get_target_equipment_classifications(self) -> JsonDict:
        """Return the active equipment recap classifications derived from equipment slots."""
        return self.get_equipment_slots()

    def get_rates(self) -> JsonDict:
        """Return the configured rates bundle for the active profile."""
        return self._load_config("rates")

    def get_review_rules(self) -> JsonDict:
        """Return profile-driven review workflow rules such as default omission."""
        return self._load_optional_config("review_rules")

    def get_export_settings(self) -> JsonDict:
        """Return export-only profile settings."""
        return self._load_optional_config("export_settings")

    def get_phase_catalog(self) -> JsonDict:
        """Return the shared company-wide phase catalog."""
        return self._load_shared_optional_config("phase_catalog")

    def get_active_profile_name(self) -> str:
        """Return the active profile name currently in use."""
        profile_dir = self._config_dir
        if profile_dir == self._legacy_config_dir:
            return "default"
        profile_file = profile_dir / "profile.json"
        if profile_file.is_file():
            metadata = self._load_profile_metadata_file(profile_file)
            return str(metadata.get("profile_name", "default"))
        return "default"

    def get_profile_metadata(self) -> JsonDict:
        """Return metadata describing the active profile."""
        profile_file = self._config_dir / "profile.json"
        if profile_file.is_file():
            metadata = self._load_profile_metadata_file(profile_file)
            metadata["profile_dir"] = str(self._config_dir)
            metadata["is_active_profile"] = self._config_dir == ProfileManager().get_active_profile_dir()
            return {str(key): value for key, value in metadata.items()}
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

    def _load_profile_metadata_file(self, profile_file: Path) -> JsonDict:
        """Load and validate one profile metadata file relative to the current config dir."""
        try:
            with profile_file.open("r", encoding="utf-8-sig") as metadata_file:
                loaded_metadata = json.load(metadata_file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Profile metadata file '{profile_file}' contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(loaded_metadata, dict):
            raise ValueError(
                f"Profile metadata file '{profile_file}' must contain a JSON object at the top level"
            )

        required_keys = ("profile_name", "display_name", "description", "version", "template_filename")
        for key in required_keys:
            if key not in loaded_metadata:
                raise ValueError(
                    f"Profile metadata file '{profile_file}' is missing required top-level key '{key}'"
                )
        return {str(key): value for key, value in loaded_metadata.items()}

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


    def _load_optional_config(self, config_name: str) -> JsonDict:
        """Load an optional config file or return its normalized default shape."""
        if config_name not in self._optional_files:
            raise KeyError(f"Unsupported optional config name '{config_name}'")

        if config_name in self._cache:
            return self._cache[config_name]

        file_name = self._optional_files[config_name]
        file_path = self._config_dir / file_name
        if not file_path.is_file():
            normalized_default = self._normalize_loaded_config(config_name, {})
            self._cache[config_name] = normalized_default
            return normalized_default

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

    def _load_shared_optional_config(self, config_name: str) -> JsonDict:
        """Load an optional shared config from the company-wide config directory."""
        if config_name not in self._shared_optional_files:
            raise KeyError(f"Unsupported shared optional config name '{config_name}'")

        cache_key = f"shared::{config_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_name = self._shared_optional_files[config_name]
        file_path = self._legacy_config_dir / file_name
        if not file_path.is_file():
            normalized_default = self._normalize_loaded_config(config_name, {})
            self._cache[cache_key] = normalized_default
            return normalized_default

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
        self._cache[cache_key] = normalized_config
        return normalized_config


    def _normalize_loaded_config(self, config_name: str, loaded_config: JsonDict) -> JsonDict:
        """Normalize compatible config formats into the app's current in-memory shape."""
        if config_name == "labor_mapping":
            return self._normalize_labor_mapping_config(loaded_config)
        if config_name == "equipment_mapping":
            return self._normalize_equipment_mapping_config(loaded_config)
        if config_name == "phase_mapping":
            return self._normalize_phase_mapping_config(loaded_config)
        if config_name == "phase_catalog":
            return self._normalize_phase_catalog_config(loaded_config)
        if config_name == "review_rules":
            return normalize_review_rules_config(loaded_config)
        if config_name == "export_settings":
            return normalize_export_settings_config(loaded_config)
        if config_name == "template_metadata":
            return build_template_metadata(
                loaded_config,
                recap_template_map=self.get_recap_template_map(),
                template_filename=self._resolve_template_metadata_filename(),
            )
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

    def _normalize_phase_mapping_config(self, loaded_config: JsonDict) -> JsonDict:
        """Normalize phase-mapping keys to one shared phase-code representation."""
        normalized_config: JsonDict = {}
        for phase_code, family in loaded_config.items():
            canonical_phase_code = canonicalize_phase_code(phase_code)
            family_text = str(family).strip()
            if canonical_phase_code and family_text:
                normalized_config[canonical_phase_code] = family_text
        return normalized_config

    def _normalize_phase_catalog_config(self, loaded_config: JsonDict) -> JsonDict:
        """Normalize shared phase-catalog rows to canonical phase codes."""
        normalized_rows: list[JsonDict] = []
        seen_phase_codes: set[str] = set()

        raw_rows = loaded_config.get("phases", [])
        if isinstance(raw_rows, list):
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue
                phase_code = canonicalize_phase_code(row.get("phase_code"))
                if not phase_code:
                    continue
                phase_name = " ".join(str(row.get("phase_name", "")).strip().split())
                normalized_key = phase_code.casefold()
                if normalized_key in seen_phase_codes:
                    continue
                seen_phase_codes.add(normalized_key)
                normalized_rows.append(
                    {
                        "phase_code": phase_code,
                        "phase_name": phase_name,
                    }
                )

        return {"phases": normalized_rows}

    def _normalize_labor_mapping_config(self, loaded_config: JsonDict) -> JsonDict:
        """Normalize raw-first labor mapping config."""
        normalized_config = {
            key: value
            for key, value in dict(loaded_config).items()
            if key not in {"phase_defaults", "aliases", "class_mappings", "apprentice_aliases"}
        }

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
            normalized_row = {
                "raw_value": canonical_raw_key,
                "target_classification": str(row.get("target_classification", "")).strip(),
                "notes": str(row.get("notes", "")).strip(),
            }
            if bool(row.get("is_observed")) and not normalized_row["target_classification"]:
                normalized_row["is_observed"] = True
            normalized_saved_rows.append(normalized_row)

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
        """Normalize raw-first equipment mapping config."""
        normalized_config = {
            key: value
            for key, value in dict(loaded_config).items()
            if key != "keyword_mappings"
        }

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
            normalized_row = {
                "raw_description": canonical_raw_description,
                "target_category": str(row.get("target_category", "")).strip(),
            }
            if bool(row.get("is_observed")) and not normalized_row["target_category"]:
                normalized_row["is_observed"] = True
            normalized_saved_rows.append(normalized_row)

        if not normalized_raw_mappings and normalized_saved_rows:
            normalized_raw_mappings = {
                str(row.get("raw_description", "")).strip(): str(row.get("target_category", "")).strip()
                for row in normalized_saved_rows
                if str(row.get("target_category", "")).strip()
            }

        if not normalized_saved_rows and normalized_raw_mappings:
            normalized_saved_rows = [
                {
                    "raw_description": raw_description,
                    "target_category": target_category,
                }
                for raw_description, target_category in normalized_raw_mappings.items()
            ]
        normalized_config["raw_mappings"] = normalized_raw_mappings
        normalized_config["saved_mappings"] = normalized_saved_rows
        return normalized_config

    def _get_slot_context(self, recap_key: str) -> tuple[int, list[str]]:
        """Return active slot capacity and row-label order from template metadata."""
        template_metadata = self.get_template_metadata()
        row_definitions = (
            template_metadata.get(recap_key, [])
            if isinstance(template_metadata.get(recap_key), list)
            else []
        )
        template_labels = [
            str(row.get("template_label") or "").strip()
            for row in row_definitions
            if isinstance(row, dict) and str(row.get("template_label") or "").strip()
        ]
        capacity = len(row_definitions)
        return capacity, template_labels

    def _build_export_row_mapping(
        self,
        slot_prefix: str,
        slot_config: JsonDict,
        recap_key: str,
    ) -> JsonDict:
        """Build compacted export row mappings keyed by active slot id."""
        template_metadata = self.get_template_metadata()
        row_definitions = (
            template_metadata.get(recap_key, [])
            if isinstance(template_metadata.get(recap_key), list)
            else []
        )
        normalized_slots = [
            dict(slot)
            for slot in slot_config.get("slots", [])
            if isinstance(slot, dict)
            and bool(slot.get("active"))
            and str(slot.get("label") or "").strip()
        ] if isinstance(slot_config.get("slots"), list) else []

        if len(normalized_slots) > len(row_definitions):
            raise ValueError(
                f"Configured active {slot_prefix} classifications exceed template capacity ({len(row_definitions)} rows available)."
            )

        slot_rows: JsonDict = {}
        for index, slot in enumerate(normalized_slots):
            if index >= len(row_definitions):
                continue
            row_definition = row_definitions[index]
            if not isinstance(row_definition, dict):
                continue
            row_mapping = row_definition.get("mapping", {})
            slot_id = str(slot.get("slot_id") or f"{slot_prefix}_{index + 1}").strip() or f"{slot_prefix}_{index + 1}"
            slot_rows[slot_id] = {
                "slot_id": slot_id,
                "label": str(slot.get("label", "")).strip(),
                "active": True,
                "template_label": str(row_definition.get("template_label") or "").strip(),
                "mapping": dict(row_mapping) if isinstance(row_mapping, dict) else {},
            }
        return slot_rows

    def _resolve_template_metadata_filename(self) -> str | None:
        """Return the configured template filename for template-metadata derivation."""
        profile_file = self._config_dir / "profile.json"
        if profile_file.is_file():
            try:
                metadata = self._load_profile_metadata_file(profile_file)
            except Exception:
                metadata = {}
            template_filename = str(metadata.get("template_filename") or "").strip()
            if template_filename:
                return template_filename
        return None


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
        elif config_name == "review_rules":
            if "default_omit_rules" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "default_omit_rules", list, "array")
        elif config_name == "export_settings":
            if "labor_minimum_hours" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "labor_minimum_hours", dict, "object")
        elif config_name == "template_metadata":
            for key in ("labor_rows", "equipment_rows"):
                if key in loaded_config:
                    self._validate_key_type(file_path, loaded_config, key, list, "array")
            if "export_behaviors" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "export_behaviors", dict, "object")
        elif config_name == "phase_catalog":
            if "phases" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "phases", list, "array")
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
            if "sales_tax_area" in loaded_config:
                self._validate_key_type(file_path, loaded_config, "sales_tax_area", dict, "object")
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
