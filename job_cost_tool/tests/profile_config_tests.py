"""Lightweight tests for profile-aware config loading."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from job_cost_tool.app.viewmodels.settings_view_model import (
    _FALLBACK_LABOR_MAPPING_GROUP,
    _active_labels_from_slots,
    _build_label_rename_map,
    _build_labor_mapping_rows,
    _build_slot_label_rename_map,
    _dedupe_casefold_preserving_order,
    _rename_equipment_mapping_config_targets,
    _rename_labor_mapping_config_targets,
    _rename_rates_config_targets,
    _rename_recap_template_map_targets,
    _resolve_labor_mapping_group,
    _validate_equipment_classification_references,
    _validate_labor_classification_references,
    _validate_slot_rows,
)
from job_cost_tool.core.config import ConfigLoader, ProfileManager


TEST_ROOT = Path("job_cost_tool/tests/_profile_tmp")


class ProfileConfigTests(unittest.TestCase):
    """Verify profile discovery and active-profile config loading."""

    def setUp(self) -> None:
        ConfigLoader._shared_cache.clear()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        (TEST_ROOT / "profiles" / "default").mkdir(parents=True, exist_ok=True)
        (TEST_ROOT / "legacy_config").mkdir(parents=True, exist_ok=True)
        self.settings_path = TEST_ROOT / "app_settings.json"

        self._write_json(
            TEST_ROOT / "profiles" / "default" / "profile.json",
            {
                "profile_name": "default",
                "display_name": "Default Profile",
                "description": "Test profile",
                "version": "1.0",
                "template_filename": "recap_template.xlsx",
                "is_active": False,
            },
        )
        self._write_json(TEST_ROOT / "profiles" / "default" / "labor_mapping.json", {"aliases": {}})
        self._write_json(TEST_ROOT / "profiles" / "default" / "equipment_mapping.json", {"keyword_mappings": {}})
        self._write_json(TEST_ROOT / "profiles" / "default" / "phase_mapping.json", {"50": "MATERIAL"})
        self._write_json(TEST_ROOT / "profiles" / "default" / "vendor_normalization.json", {})
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "input_model.json",
            {"report_type": "vista_job_cost", "section_headers": {}},
        )
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "target_labor_classifications.json",
            {"classifications": ["103 Journeyman"]},
        )
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "target_equipment_classifications.json",
            {"classifications": ["Pick-up Truck"]},
        )
        self._write_json(TEST_ROOT / "profiles" / "default" / "rates.json", {"labor_rates": {}, "equipment_rates": {}})
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "recap_template_map.json",
            {
                "worksheet_name": "Recap",
                "header_fields": {},
                "labor_rows": {},
                "equipment_rows": {},
                "materials_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "amount": "B"}},
                "subcontractors_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "description": "B", "amount": "C"}},
                "permits_fees_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
                "police_detail_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
            },
        )
        (TEST_ROOT / "profiles" / "default" / "recap_template.xlsx").write_bytes(b"template")
        self._write_json(self.settings_path, {"active_profile": "default"})

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_profile_manager_discovers_default_profile(self) -> None:
        manager = self._build_manager()

        profiles = manager.list_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_name"], "default")
        self.assertEqual(manager.get_active_profile_name(), "default")
        self.assertEqual(manager.get_active_profile_dir(), (TEST_ROOT / "profiles" / "default").resolve())

    def test_config_loader_reads_active_profile_bundle(self) -> None:
        manager = self._build_manager()
        loader = ConfigLoader(config_dir=manager.get_active_profile_dir())

        self.assertEqual(loader.get_target_labor_classifications()["classifications"], ["103 Journeyman"])
        self.assertEqual(loader.get_labor_slots()["slots"][0]["slot_id"], "labor_1")
        self.assertEqual(loader.get_rates(), {"labor_rates": {}, "equipment_rates": {}})
        self.assertEqual(loader.get_template_path(), (TEST_ROOT / "profiles" / "default" / "recap_template.xlsx").resolve())

    def test_profile_manager_can_duplicate_and_switch_profile(self) -> None:
        manager = self._build_manager()
        duplicated = manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="alt_profile",
            display_name="Alternate Profile",
            description="Cloned test profile",
        )

        self.assertEqual(duplicated["profile_name"], "alt_profile")
        self.assertTrue((TEST_ROOT / "profiles" / "alt_profile" / "profile.json").is_file())

        manager.set_active_profile("alt_profile")
        self.assertEqual(manager.get_active_profile_name(), "alt_profile")
        self.assertEqual(manager.get_active_profile_metadata()["display_name"], "Alternate Profile")

    def test_profile_manager_cannot_delete_default_profile(self) -> None:
        manager = self._build_manager()

        with self.assertRaisesRegex(ValueError, "Default profile cannot be deleted"):
            manager.delete_profile("default")

    def test_profile_manager_cannot_delete_active_profile(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="alt_profile",
            display_name="Alternate Profile",
            description="Cloned test profile",
        )
        manager.set_active_profile("alt_profile")

        with self.assertRaisesRegex(ValueError, "Switch to another profile before deleting this one"):
            manager.delete_profile("alt_profile")

    def test_profile_manager_can_delete_non_default_inactive_profile(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="alt_profile",
            display_name="Alternate Profile",
            description="Cloned test profile",
        )

        manager.delete_profile("alt_profile")

        self.assertIsNone(manager.get_profile_dir("alt_profile"))
        self.assertFalse((TEST_ROOT / "profiles" / "alt_profile").exists())

    def test_config_loader_migrates_old_classification_list_to_slots_using_template_capacity(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "target_labor_classifications.json",
            {"classifications": ["Legacy A", "Legacy B", "Legacy C"]},
        )
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "recap_template_map.json",
            {
                "worksheet_name": "Recap",
                "header_fields": {},
                "labor_rows": {
                    "Slot 1": {"st_hours": "B1"},
                    "Slot 2": {"st_hours": "B2"},
                },
                "equipment_rows": {},
                "materials_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "amount": "B"}},
                "subcontractors_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "description": "B", "amount": "C"}},
                "permits_fees_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
                "police_detail_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
            },
        )

        loader = ConfigLoader(config_dir=(TEST_ROOT / "profiles" / "default"))
        slots = loader.get_labor_slots()

        self.assertEqual(slots["capacity"], 2)
        self.assertEqual(slots["classifications"], ["Legacy A", "Legacy B"])
        self.assertEqual(slots["slots"][0]["slot_id"], "labor_1")
        self.assertEqual(slots["slots"][1]["slot_id"], "labor_2")

    def test_labor_classification_validation_rejects_referenced_mapping_or_rate(self) -> None:
        with self.assertRaisesRegex(ValueError, "still referenced by labor mapping"):
            _validate_labor_classification_references(
                rows=[{"raw_value": "GF", "target_classification": "103 Foreman"}],
                rate_rows=[],
                valid_classifications=["103 Journeyman"],
            )

        with self.assertRaisesRegex(ValueError, "still referenced by configured labor rates"):
            _validate_labor_classification_references(
                rows=[],
                rate_rows=[
                    {
                        "classification": "103 Foreman",
                        "standard_rate": "95",
                        "overtime_rate": "",
                        "double_time_rate": "",
                    }
                ],
                valid_classifications=["103 Journeyman"],
            )

    def test_equipment_classification_validation_rejects_referenced_mapping_or_rate(self) -> None:
        with self.assertRaisesRegex(ValueError, "still referenced by equipment mapping"):
            _validate_equipment_classification_references(
                rows=[{"raw_pattern": "bucket truck", "target_category": "Bucket Truck"}],
                rate_rows=[],
                valid_classifications=["Utility Van"],
            )

        with self.assertRaisesRegex(ValueError, "still referenced by configured equipment rates"):
            _validate_equipment_classification_references(
                rows=[],
                rate_rows=[{"category": "Bucket Truck", "rate": "125"}],
                valid_classifications=["Utility Van"],
            )

    def test_labor_mapping_group_resolution_does_not_require_numeric_prefixes(self) -> None:
        labor_mapping = {
            "phase_defaults": {"20": "contract_a"},
            "class_mappings": {
                "contract_a": {
                    "J": "Journeyman A",
                    "F": "Foreman A",
                }
            },
        }

        resolved_group = _resolve_labor_mapping_group(
            raw_value="J",
            target_classification="Journeyman A",
            labor_mapping=labor_mapping,
        )
        self.assertEqual(resolved_group, "contract_a")

    def test_labor_mapping_group_resolution_accepts_explicit_group_prefix(self) -> None:
        labor_mapping = {
            "phase_defaults": {},
            "class_mappings": {},
        }

        resolved_group = _resolve_labor_mapping_group(
            raw_value="contract_b/J",
            target_classification="Custom Journeyman",
            labor_mapping=labor_mapping,
        )
        self.assertEqual(resolved_group, "contract_b")

    def test_classification_rename_map_updates_profile_references(self) -> None:
        labor_rename_map = _build_label_rename_map(
            ["Old Journeyman", "Foreman"],
            ["New Journeyman", "Foreman"],
        )
        equipment_rename_map = _build_label_rename_map(
            ["Old Truck", "Van"],
            ["New Truck", "Van"],
        )

        updated_labor_mapping = _rename_labor_mapping_config_targets(
            {
                "class_mappings": {"contract_a": {"J": "Old Journeyman"}},
                "mapping_notes": {"J|Old Journeyman": "note"},
            },
            labor_rename_map,
        )
        updated_equipment_mapping = _rename_equipment_mapping_config_targets(
            {"keyword_mappings": {"truck": "Old Truck"}},
            equipment_rename_map,
        )
        updated_rates = _rename_rates_config_targets(
            {
                "labor_rates": {"Old Journeyman": {"standard_rate": 100}},
                "equipment_rates": {"Old Truck": {"rate": 25}},
            },
            labor_rename_map,
            equipment_rename_map,
        )
        updated_recap_map = _rename_recap_template_map_targets(
            {
                "labor_rows": {"Old Journeyman": {"st_hours": "B12"}},
                "equipment_rows": {"Old Truck": {"hours_qty": "B27"}},
            },
            labor_rename_map,
            equipment_rename_map,
        )

        self.assertEqual(updated_labor_mapping["class_mappings"]["contract_a"]["J"], "New Journeyman")
        self.assertIn("J|New Journeyman", updated_labor_mapping["mapping_notes"])
        self.assertEqual(updated_equipment_mapping["keyword_mappings"]["truck"], "New Truck")
        self.assertIn("New Journeyman", updated_rates["labor_rates"])
        self.assertIn("New Truck", updated_rates["equipment_rates"])
        self.assertIn("New Journeyman", updated_recap_map["labor_rows"])
        self.assertIn("New Truck", updated_recap_map["equipment_rows"])

    def test_labor_mapping_group_resolution_falls_back_for_new_custom_target(self) -> None:
        labor_mapping = {
            "phase_defaults": {"20": "contract_a", "21": "contract_b"},
            "class_mappings": {
                "contract_a": {"J": "Journeyman A"},
                "contract_b": {"F": "Foreman B"},
            },
        }

        resolved_group = _resolve_labor_mapping_group(
            raw_value="F",
            target_classification="Big Boy",
            labor_mapping=labor_mapping,
        )
        self.assertEqual(resolved_group, _FALLBACK_LABOR_MAPPING_GROUP)

    def test_build_labor_mapping_rows_omits_synthetic_fallback_group_rows(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"F": "F"},
                "class_mappings": {
                    _FALLBACK_LABOR_MAPPING_GROUP: {"F": "Big Boy"},
                },
            }
        )

        self.assertEqual(rows, [{"raw_value": "F", "target_classification": "Big Boy", "notes": ""}])

    def test_build_labor_mapping_rows_does_not_synthesize_group_based_raw_values(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"103/F": "F"},
                "class_mappings": {
                    "103": {"F": "Foreman"},
                    "104": {"F": "Foreman"},
                },
            }
        )

        self.assertEqual(rows, [{"raw_value": "103/F", "target_classification": "Foreman", "notes": ""}])

    def test_build_labor_mapping_rows_preserves_true_prefixed_raw_values(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"103/F": "F", "104/F": "F", "103/J": "J", "104/J": "J"},
                "class_mappings": {
                    "103": {"F": "103 Foreman", "J": "103 Journeyman"},
                    "104": {"F": "104 Foreman", "J": "104 Journeyman"},
                },
            }
        )

        self.assertEqual(
            rows,
            [
                {"raw_value": "103/F", "target_classification": "103 Foreman", "notes": ""},
                {"raw_value": "103/J", "target_classification": "103 Journeyman", "notes": ""},
                {"raw_value": "104/F", "target_classification": "104 Foreman", "notes": ""},
                {"raw_value": "104/J", "target_classification": "104 Journeyman", "notes": ""},
            ],
        )

    def test_build_labor_mapping_rows_legacy_plain_raw_value_does_not_expand_to_multiple_targets(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"F": "F"},
                "class_mappings": {
                    "103": {"F": "103 Foreman"},
                    "104": {"F": "104 Foreman"},
                },
            }
        )

        self.assertEqual(rows, [{"raw_value": "F", "target_classification": "", "notes": ""}])

    def test_build_labor_mapping_rows_prefers_explicit_saved_mappings(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"103/F": "F"},
                "class_mappings": {
                    "103": {"F": "103 Foreman"},
                    "104": {"F": "104 Foreman"},
                },
                "saved_mappings": [
                    {"raw_value": "103/F", "target_classification": "Big Boy", "notes": "keep me"},
                ],
            }
        )

        self.assertEqual(rows, [{"raw_value": "103/F", "target_classification": "Big Boy", "notes": "keep me"}])

    def test_build_labor_mapping_rows_merges_observed_raw_values_without_inflating_saved_rows(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"103/F": "F"},
                "class_mappings": {
                    "103": {"F": "Foreman"},
                },
            },
            observed_raw_values=["103/F", "104/J", "J"],
        )

        self.assertEqual(
            rows,
            [
                {"raw_value": "104/J", "target_classification": "", "notes": ""},
                {"raw_value": "J", "target_classification": "", "notes": ""},
                {"raw_value": "103/F", "target_classification": "Foreman", "notes": ""},
            ],
        )

    def test_dedupe_casefold_preserving_order_keeps_first_observed_value(self) -> None:
        self.assertEqual(
            _dedupe_casefold_preserving_order(["103/F", "103/f", " J ", "J", ""]),
            ["103/F", "J"],
        )

    def test_validate_slot_rows_rejects_duplicate_active_labels(self) -> None:
        existing_slots = [
            {"slot_id": "labor_1", "label": "Old A", "active": True},
            {"slot_id": "labor_2", "label": "Old B", "active": True},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate active labor classification"):
            _validate_slot_rows(
                [
                    {"slot_id": "labor_1", "label": "Big Boy", "active": True},
                    {"slot_id": "labor_2", "label": "Big Boy", "active": True},
                ],
                existing_slots=existing_slots,
                slot_label="Labor",
            )

    def test_slot_rename_map_tracks_changes_by_slot_id(self) -> None:
        previous_slots = [
            {"slot_id": "labor_1", "label": "Old A", "active": True},
            {"slot_id": "labor_2", "label": "Old B", "active": True},
        ]
        updated_slots = _validate_slot_rows(
            [
                {"slot_id": "labor_1", "label": "New A", "active": True},
                {"slot_id": "labor_2", "label": "", "active": False},
            ],
            existing_slots=previous_slots,
            slot_label="Labor",
        )

        self.assertEqual(_active_labels_from_slots(updated_slots), ["New A"])
        self.assertEqual(_build_slot_label_rename_map(previous_slots, updated_slots), {"Old A": "New A"})

    def _build_manager(self) -> ProfileManager:
        return ProfileManager(
            profiles_root=TEST_ROOT / "profiles",
            settings_path=self.settings_path,
            legacy_config_root=TEST_ROOT / "legacy_config",
        )

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
