"""Config loading utilities for the Job Cost Tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar


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
        "target_labor_classifications": ("classifications",),
        "target_equipment_classifications": ("classifications",),
    }
    _shared_cache: ClassVar[dict[Path, dict[str, JsonDict]]] = {}

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize the loader with a project-relative config directory."""
        base_dir = Path(__file__).resolve().parents[2]
        self._config_dir = (config_dir or (base_dir / "config")).resolve()
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

    def get_target_labor_classifications(self) -> JsonDict:
        """Return the configured target labor recap classifications."""
        return self._load_config("target_labor_classifications")

    def get_target_equipment_classifications(self) -> JsonDict:
        """Return the configured target equipment recap classifications."""
        return self._load_config("target_equipment_classifications")

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
        self._cache[config_name] = loaded_config
        return loaded_config

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

        if config_name == "input_model":
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
            self._validate_key_type(file_path, loaded_config, "classifications", list, "array")

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
