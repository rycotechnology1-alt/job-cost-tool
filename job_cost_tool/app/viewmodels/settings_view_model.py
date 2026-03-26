"""View-model for profile settings and lightweight admin actions."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from job_cost_tool.core.config import ConfigLoader, ProfileManager

_LABOR_GROUP_RE = re.compile(r"^(?P<group>\d+)\b")


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
        self._labor_classifications: list[str] = []
        self._equipment_classifications: list[str] = []
        self._labor_rate_rows: list[dict[str, str]] = []
        self._equipment_rate_rows: list[dict[str, str]] = []
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
    def labor_classifications(self) -> list[str]:
        """Return labor recap classifications for the active profile."""
        return list(self._labor_classifications)

    @property
    def equipment_classifications(self) -> list[str]:
        """Return equipment recap classifications for the active profile."""
        return list(self._equipment_classifications)

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

    def save_labor_mappings(self, rows: list[dict[str, str]]) -> str:
        """Validate and persist labor mapping rows for the active profile."""
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_config = loader.get_labor_mapping()
        valid_targets = set(self._labor_classifications)

        aliases: dict[str, str] = {}
        class_mappings: dict[str, dict[str, str]] = {}
        mapping_notes: dict[str, str] = {}
        seen_rows: set[tuple[str, str]] = set()

        for row in rows:
            raw_value = str(row.get("raw_value", "")).strip()
            target_classification = str(row.get("target_classification", "")).strip()
            note = str(row.get("notes", "")).strip()
            if not raw_value:
                raise ValueError("Labor mapping rows must include a raw value.")
            if not target_classification:
                raise ValueError(f"Labor mapping '{raw_value}' is missing a target classification.")
            if target_classification not in valid_targets:
                raise ValueError(
                    f"Labor mapping '{raw_value}' references unknown target classification '{target_classification}'."
                )

            raw_key = _canonicalize_labor_token(raw_value)
            canonical_alias = _derive_labor_alias(raw_value)
            labor_group = _extract_labor_group(target_classification)
            duplicate_key = (raw_key, target_classification)
            if duplicate_key in seen_rows:
                raise ValueError(
                    f"Duplicate labor mapping entry found for '{raw_value}' -> '{target_classification}'."
                )
            seen_rows.add(duplicate_key)

            aliases[raw_key] = canonical_alias
            class_mappings.setdefault(labor_group, {})[canonical_alias] = target_classification
            if note:
                mapping_notes[f"{raw_key}|{target_classification}"] = note

        new_config = dict(existing_config)
        new_config["aliases"] = aliases
        new_config["class_mappings"] = class_mappings
        if mapping_notes:
            new_config["mapping_notes"] = mapping_notes
        else:
            new_config.pop("mapping_notes", None)

        _write_json_file(profile_dir / "labor_mapping.json", new_config)
        clear_profile_dependent_caches()
        self.reload()
        return "Labor mappings saved successfully."

    def save_equipment_mappings(self, rows: list[dict[str, str]]) -> str:
        """Validate and persist equipment mapping rows for the active profile."""
        profile_dir = self._active_profile_dir()
        loader = ConfigLoader(config_dir=profile_dir)
        existing_config = loader.get_equipment_mapping()
        valid_targets = set(self._equipment_classifications)

        keyword_mappings: dict[str, str] = {}
        seen_patterns: set[str] = set()
        for row in rows:
            raw_pattern = str(row.get("raw_pattern", "")).strip()
            target_category = str(row.get("target_category", "")).strip()
            if not raw_pattern:
                raise ValueError("Equipment mapping rows must include a raw description or pattern.")
            if not target_category:
                raise ValueError(f"Equipment mapping '{raw_pattern}' is missing a target category.")
            if target_category not in valid_targets:
                raise ValueError(
                    f"Equipment mapping '{raw_pattern}' references unknown target category '{target_category}'."
                )

            normalized_pattern = raw_pattern.casefold()
            if normalized_pattern in seen_patterns:
                raise ValueError(f"Duplicate equipment mapping pattern '{raw_pattern}' is not allowed.")
            seen_patterns.add(normalized_pattern)
            keyword_mappings[raw_pattern] = target_category

        new_config = dict(existing_config)
        new_config["keyword_mappings"] = keyword_mappings
        _write_json_file(profile_dir / "equipment_mapping.json", new_config)
        clear_profile_dependent_caches()
        self.reload()
        return "Equipment mappings saved successfully."

    def save_classifications(self, labor_classifications: list[str], equipment_classifications: list[str]) -> str:
        """Validate and persist recap classification lists for the active profile."""
        profile_dir = self._active_profile_dir()
        validated_labor = _validate_unique_labels(labor_classifications, "Labor classification")
        validated_equipment = _validate_unique_labels(equipment_classifications, "Equipment classification")

        _validate_labor_classification_references(
            rows=self._labor_mapping_rows,
            rate_rows=self._labor_rate_rows,
            valid_classifications=validated_labor,
        )
        _validate_equipment_classification_references(
            rows=self._equipment_mapping_rows,
            rate_rows=self._equipment_rate_rows,
            valid_classifications=validated_equipment,
        )

        _write_json_file(
            profile_dir / "target_labor_classifications.json",
            {"classifications": validated_labor},
        )
        _write_json_file(
            profile_dir / "target_equipment_classifications.json",
            {"classifications": validated_equipment},
        )
        clear_profile_dependent_caches()
        self.reload()
        return "Target classifications saved successfully."

    def save_rates(
        self,
        labor_rows: list[dict[str, str]],
        equipment_rows: list[dict[str, str]],
    ) -> str:
        """Validate and persist labor and equipment rates for the active profile."""
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

        self._labor_classifications = [
            str(item).strip()
            for item in loader.get_target_labor_classifications().get("classifications", [])
            if str(item).strip()
        ]
        self._equipment_classifications = [
            str(item).strip()
            for item in loader.get_target_equipment_classifications().get("classifications", [])
            if str(item).strip()
        ]
        self._labor_mapping_rows = _build_labor_mapping_rows(labor_mapping)
        self._equipment_mapping_rows = _build_equipment_mapping_rows(equipment_mapping)
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
        return summary

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
        equipment_normalizer._get_equipment_mapping,
        equipment_normalizer._get_target_equipment_classifications,
        material_normalizer._get_vendor_normalization,
        normalizer._get_phase_mapping,
        recap_mapper._get_target_labor_classifications,
        recap_mapper._get_target_equipment_classifications,
    ]

    for cache_function in cache_functions:
        if hasattr(cache_function, "cache_clear"):
            cache_function.cache_clear()


def _build_labor_mapping_rows(labor_mapping: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten labor mapping config into editable rows."""
    aliases = labor_mapping.get("aliases", {}) if isinstance(labor_mapping.get("aliases"), dict) else {}
    class_mappings = labor_mapping.get("class_mappings", {}) if isinstance(labor_mapping.get("class_mappings"), dict) else {}
    notes = labor_mapping.get("mapping_notes", {}) if isinstance(labor_mapping.get("mapping_notes"), dict) else {}

    rows: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for raw_value, canonical_alias in aliases.items():
        canonical_alias_text = str(canonical_alias).strip()
        for group, group_mappings in class_mappings.items():
            if not isinstance(group_mappings, dict) or canonical_alias_text not in group_mappings:
                continue
            target_classification = str(group_mappings[canonical_alias_text]).strip()
            pair = (str(raw_value).strip(), target_classification)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            rows.append(
                {
                    "raw_value": str(raw_value).strip(),
                    "target_classification": target_classification,
                    "notes": str(notes.get(f"{pair[0]}|{pair[1]}", "")).strip(),
                }
            )

    for group, group_mappings in class_mappings.items():
        if not isinstance(group_mappings, dict):
            continue
        for canonical_alias, target_classification in group_mappings.items():
            synthetic_raw = f"{group}/{canonical_alias}"
            pair = (synthetic_raw, str(target_classification).strip())
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            rows.append(
                {
                    "raw_value": synthetic_raw,
                    "target_classification": str(target_classification).strip(),
                    "notes": str(notes.get(f"{synthetic_raw}|{target_classification}", "")).strip(),
                }
            )

    rows.sort(key=lambda row: (row["target_classification"], row["raw_value"]))
    return rows


def _build_equipment_mapping_rows(equipment_mapping: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten equipment mapping config into editable rows."""
    keyword_mappings = equipment_mapping.get("keyword_mappings", {})
    if not isinstance(keyword_mappings, dict):
        return []
    rows = [
        {
            "raw_pattern": str(raw_pattern).strip(),
            "target_category": str(target_category).strip(),
        }
        for raw_pattern, target_category in keyword_mappings.items()
        if str(raw_pattern).strip()
    ]
    rows.sort(key=lambda row: row["raw_pattern"].casefold())
    return rows


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
        raw_pattern = str(row.get("raw_pattern", "")).strip()
        target_category = str(row.get("target_category", "")).strip()
        if target_category and target_category.casefold() not in valid_targets:
            raise ValueError(
                f"Equipment classification '{target_category}' is still referenced by equipment mapping '{raw_pattern}'. "
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


def _extract_labor_group(target_classification: str) -> str:
    """Extract the labor group prefix from a target labor classification label."""
    match = _LABOR_GROUP_RE.match(target_classification.strip())
    if not match:
        raise ValueError(
            f"Labor target classification '{target_classification}' must start with a labor group like '103' or '104'."
        )
    return match.group("group")


def _derive_labor_alias(raw_value: str) -> str:
    """Derive the canonical alias token used in labor class mappings."""
    if "/" in raw_value:
        alias_source = raw_value.split("/")[-1]
    else:
        alias_source = raw_value
    return _canonicalize_labor_token(alias_source)


def _canonicalize_labor_token(value: str) -> str:
    """Canonicalize labor mapping tokens consistently with labor normalization."""
    collapsed = " ".join(str(value).strip().upper().split())
    return collapsed.replace("APPRENTICESHIP", "APP")


def _stringify_rate(value: Any) -> str:
    """Convert a saved rate value to a user-editable string."""
    if value in {None, ""}:
        return ""
    return str(value)
