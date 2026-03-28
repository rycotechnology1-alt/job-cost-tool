"""Lightweight tests for profile-aware config loading."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from job_cost_tool.app.viewmodels.review_view_model import ReviewViewModel
from job_cost_tool.app.viewmodels.settings_view_model import (
    SettingsViewModel,
    _active_labels_from_slots,
    _build_equipment_mapping_rows,
    _build_label_rename_map,
    _build_labor_mapping_rows,
    _build_slot_label_rename_map,
    _dedupe_casefold_preserving_order,
    _rename_equipment_mapping_config_targets,
    _rename_labor_mapping_config_targets,
    _rename_rates_config_targets,
    _rename_recap_template_map_targets,
    _validate_equipment_classification_references,
    _validate_labor_classification_references,
    _validate_slot_rows,
    persist_observed_equipment_raw_values,
    persist_observed_labor_raw_values,
)
from job_cost_tool.core.config import ConfigLoader, ProfileManager
from job_cost_tool.core.models.record import Record


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

    def test_default_profile_is_locked_by_default_and_unlock_state_persists(self) -> None:
        manager = self._build_manager()

        self.assertFalse(manager.is_default_profile_unlocked())

        manager.set_default_profile_unlocked(True)
        self.assertTrue(manager.is_default_profile_unlocked())
        reloaded_manager = self._build_manager()
        self.assertTrue(reloaded_manager.is_default_profile_unlocked())

        manager.set_default_profile_unlocked(False)
        self.assertFalse(self._build_manager().is_default_profile_unlocked())

    def test_settings_view_model_respects_default_profile_lock_and_unlock(self) -> None:
        manager = self._build_manager()

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()
            self.assertTrue(view_model.is_default_profile)
            self.assertTrue(view_model.is_default_profile_locked)
            self.assertFalse(view_model.is_active_profile_editable)
            self.assertEqual(view_model.read_only_message, "Default profile is locked. Unlock it to make changes.")

            with self.assertRaisesRegex(ValueError, "Default profile is locked. Unlock it to make changes."):
                view_model.save_labor_mappings([])

            unlock_message = view_model.unlock_default_profile()
            self.assertEqual(unlock_message, "Default profile is now unlocked for editing.")
            self.assertTrue(view_model.is_active_profile_editable)
            self.assertFalse(view_model.is_default_profile_locked)

            lock_message = view_model.lock_default_profile()
            self.assertEqual(lock_message, "Default profile has been locked.")
            self.assertFalse(view_model.is_active_profile_editable)
            self.assertTrue(view_model.is_default_profile_locked)

    def test_default_profile_cannot_be_deleted_even_when_unlocked(self) -> None:
        manager = self._build_manager()
        manager.set_default_profile_unlocked(True)

        with self.assertRaisesRegex(ValueError, "Default profile cannot be deleted"):
            manager.delete_profile("default")

    def test_config_loader_normalizes_raw_first_labor_mapping_structure(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "labor_mapping.json",
            {
                "raw_mappings": {" 103/f ": "103 Journeyman"},
                "saved_mappings": [
                    {"raw_value": "103/f", "target_classification": "103 Journeyman", "notes": "keep"},
                    {"raw_value": "104/eo", "target_classification": "", "notes": "todo"},
                ],
            },
        )

        loader = ConfigLoader(config_dir=(TEST_ROOT / "profiles" / "default"))
        labor_mapping = loader.get_labor_mapping()

        self.assertEqual(labor_mapping["raw_mappings"], {"103/F": "103 Journeyman"})
        self.assertEqual(
            labor_mapping["saved_mappings"],
            [
                {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep"},
                {"raw_value": "104/EO", "target_classification": "", "notes": "todo"},
            ],
        )

    def test_config_loader_normalizes_raw_first_equipment_mapping_structure(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "equipment_mapping.json",
            {
                "raw_mappings": {" 627/2025 ford transit van ": "Pick-up Truck"},
                "saved_mappings": [
                    {"raw_description": "627/2025 ford transit van", "target_category": "Pick-up Truck"},
                    {"raw_description": " crane truck ", "target_category": ""},
                ],
            },
        )

        loader = ConfigLoader(config_dir=(TEST_ROOT / "profiles" / "default"))
        equipment_mapping = loader.get_equipment_mapping()

        self.assertEqual(equipment_mapping["raw_mappings"], {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"})
        self.assertEqual(
            equipment_mapping["saved_mappings"],
            [
                {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                {"raw_description": "CRANE TRUCK", "target_category": ""},
            ],
        )
        self.assertEqual(equipment_mapping["keyword_mappings"], {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"})

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
                "raw_mappings": {"103/J": "Old Journeyman"},
                "saved_mappings": [
                    {"raw_value": "103/J", "target_classification": "Old Journeyman", "notes": "note"},
                ],
                "class_mappings": {"contract_a": {"J": "Old Journeyman"}},
                "mapping_notes": {"103/J|Old Journeyman": "note"},
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

        self.assertEqual(updated_labor_mapping["raw_mappings"]["103/J"], "New Journeyman")
        self.assertEqual(
            updated_labor_mapping["saved_mappings"],
            [{"raw_value": "103/J", "target_classification": "New Journeyman", "notes": "note"}],
        )
        self.assertNotIn("class_mappings", updated_labor_mapping)
        self.assertNotIn("mapping_notes", updated_labor_mapping)
        self.assertEqual(updated_equipment_mapping["keyword_mappings"]["TRUCK"], "New Truck")
        self.assertIn("New Journeyman", updated_rates["labor_rates"])
        self.assertIn("New Truck", updated_rates["equipment_rates"])
        self.assertIn("New Journeyman", updated_recap_map["labor_rows"])
        self.assertIn("New Truck", updated_recap_map["equipment_rows"])

    def test_build_labor_mapping_rows_ignores_legacy_only_config_without_raw_first_rows(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "aliases": {"103/F": "F"},
                "class_mappings": {
                    "103": {"F": "103 Foreman"},
                },
                "mapping_notes": {"103/F|103 Foreman": "legacy note"},
            }
        )

        self.assertEqual(rows, [])

    def test_build_labor_mapping_rows_prefers_explicit_saved_mappings(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "raw_mappings": {"103/F": "103 Foreman"},
                "saved_mappings": [
                    {"raw_value": "103/F", "target_classification": "Big Boy", "notes": "keep me"},
                ],
            }
        )

        self.assertEqual(rows, [{"raw_value": "103/F", "target_classification": "Big Boy", "notes": "keep me"}])

    def test_build_labor_mapping_rows_merges_observed_raw_values_without_inflating_raw_first_rows(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "raw_mappings": {
                    "103/F": "Foreman",
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

    def test_build_labor_mapping_rows_uses_raw_mappings_when_saved_rows_are_absent(self) -> None:
        rows = _build_labor_mapping_rows(
            {
                "raw_mappings": {
                    "103/F": "103 Foreman",
                    "104/F": "104 Foreman",
                },
            }
        )

        self.assertEqual(
            rows,
            [
                {"raw_value": "103/F", "target_classification": "103 Foreman", "notes": ""},
                {"raw_value": "104/F", "target_classification": "104 Foreman", "notes": ""},
            ],
        )


    def test_build_equipment_mapping_rows_prefers_explicit_saved_mappings(self) -> None:
        rows = _build_equipment_mapping_rows(
            {
                "raw_mappings": {"CRANE TRUCK": "Pick-up Truck"},
                "saved_mappings": [
                    {"raw_description": "CRANE TRUCK", "target_category": "Utility Van"},
                ],
            }
        )

        self.assertEqual(
            rows,
            [{"raw_description": "CRANE TRUCK", "raw_pattern": "CRANE TRUCK", "target_category": "Utility Van"}],
        )

    def test_build_equipment_mapping_rows_appends_observed_unmapped_descriptions(self) -> None:
        rows = _build_equipment_mapping_rows(
            {
                "saved_mappings": [
                    {"raw_description": "CRANE TRUCK", "target_category": "Pick-up Truck"},
                ],
            },
            observed_raw_descriptions=["593/2024 Freightliner Bucket/MH", "crane truck"],
        )

        self.assertEqual(
            rows,
            [
                {"raw_description": "593/2024 FREIGHTLINER BUCKET/MH", "raw_pattern": "593/2024 FREIGHTLINER BUCKET/MH", "target_category": ""},
                {"raw_description": "CRANE TRUCK", "raw_pattern": "CRANE TRUCK", "target_category": "Pick-up Truck"},
            ],
        )

    def test_build_equipment_mapping_rows_uses_raw_mappings_then_keyword_mappings_for_compatibility(self) -> None:
        raw_rows = _build_equipment_mapping_rows(
            {
                "raw_mappings": {
                    "627/2025 FORD TRANSIT VAN": "Pick-up Truck",
                },
            }
        )
        keyword_rows = _build_equipment_mapping_rows(
            {
                "keyword_mappings": {
                    "bucket truck": "Pick-up Truck",
                },
            }
        )

        self.assertEqual(
            raw_rows,
            [{"raw_description": "627/2025 FORD TRANSIT VAN", "raw_pattern": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"}],
        )
        self.assertEqual(
            keyword_rows,
            [{"raw_description": "BUCKET TRUCK", "raw_pattern": "BUCKET TRUCK", "target_category": "Pick-up Truck"}],
        )


    def test_config_loader_synthesizes_keyword_compatibility_view_from_raw_only_equipment_config(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "equipment_mapping.json",
            {
                "raw_mappings": {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"},
                "saved_mappings": [
                    {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                ],
            },
        )

        loader = ConfigLoader(config_dir=(TEST_ROOT / "profiles" / "default"))
        equipment_mapping = loader.get_equipment_mapping()

        self.assertEqual(equipment_mapping["raw_mappings"], {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"})
        self.assertEqual(equipment_mapping["keyword_mappings"], {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"})

    def test_save_labor_mappings_persists_raw_mappings_and_blank_saved_rows(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()
            message = view_model.save_labor_mappings(
                [
                    {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "mapped"},
                    {"raw_value": "104/EO", "target_classification": "", "notes": "review later"},
                ]
            )

        saved_config = json.loads(
            (TEST_ROOT / "profiles" / "editable_profile" / "labor_mapping.json").read_text(encoding="utf-8")
        )

        self.assertEqual(message, "Labor mappings saved successfully.")
        self.assertEqual(saved_config["raw_mappings"], {"103/F": "103 Journeyman"})
        self.assertEqual(
            saved_config["saved_mappings"],
            [
                {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "mapped"},
                {"raw_value": "104/EO", "target_classification": "", "notes": "review later"},
            ],
        )
        self.assertNotIn("aliases", saved_config)
        self.assertNotIn("class_mappings", saved_config)
        self.assertNotIn("mapping_notes", saved_config)

    def test_save_labor_mappings_rejects_duplicate_canonical_raw_keys(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()
            with self.assertRaisesRegex(ValueError, "Duplicate labor mapping raw value"):
                view_model.save_labor_mappings(
                    [
                        {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": ""},
                        {"raw_value": "103/f", "target_classification": "103 Journeyman", "notes": ""},
                    ]
                )


    def test_save_equipment_mappings_persists_raw_mappings_and_blank_saved_rows(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()
            message = view_model.save_equipment_mappings(
                [
                    {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                    {"raw_description": "CRANE TRUCK", "target_category": ""},
                ]
            )

        saved_config = json.loads(
            (TEST_ROOT / "profiles" / "editable_profile" / "equipment_mapping.json").read_text(encoding="utf-8")
        )

        self.assertEqual(message, "Equipment mappings saved successfully.")
        self.assertEqual(saved_config["raw_mappings"], {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"})
        self.assertEqual(
            saved_config["saved_mappings"],
            [
                {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                {"raw_description": "CRANE TRUCK", "target_category": ""},
            ],
        )
        self.assertNotIn("keyword_mappings", saved_config)

    def test_save_equipment_mappings_rejects_duplicate_canonical_raw_descriptions(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()
            with self.assertRaisesRegex(ValueError, "Duplicate equipment mapping raw description"):
                view_model.save_equipment_mappings(
                    [
                        {"raw_description": "crane truck", "target_category": "Pick-up Truck"},
                        {"raw_description": " CRANE   TRUCK ", "target_category": "Pick-up Truck"},
                    ]
                )

    def test_persist_observed_labor_raw_values_appends_new_placeholder_and_preserves_existing_rows(self) -> None:
        profile_dir = TEST_ROOT / "profiles" / "editable_profile"
        shutil.copytree(TEST_ROOT / "profiles" / "default", profile_dir)
        self._write_json(
            profile_dir / "profile.json",
            {
                "profile_name": "editable_profile",
                "display_name": "Editable Profile",
                "description": "Editable clone",
                "version": "1.0",
                "template_filename": "recap_template.xlsx",
                "is_active": False,
            },
        )
        self._write_json(
            profile_dir / "labor_mapping.json",
            {
                "raw_mappings": {"103/F": "103 Journeyman"},
                "saved_mappings": [
                    {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep me"},
                ],
            },
        )

        did_update = persist_observed_labor_raw_values(profile_dir, ["103/F", "104/J"])
        updated = json.loads((profile_dir / "labor_mapping.json").read_text(encoding="utf-8"))

        self.assertTrue(did_update)
        self.assertEqual(updated["raw_mappings"], {"103/F": "103 Journeyman"})
        self.assertEqual(
            updated["saved_mappings"],
            [
                {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep me"},
                {"raw_value": "104/J", "target_classification": "", "notes": ""},
            ],
        )

    def test_persist_observed_labor_raw_values_does_not_duplicate_known_rows(self) -> None:
        profile_dir = TEST_ROOT / "profiles" / "editable_profile"
        shutil.copytree(TEST_ROOT / "profiles" / "default", profile_dir)
        self._write_json(
            profile_dir / "profile.json",
            {
                "profile_name": "editable_profile",
                "display_name": "Editable Profile",
                "description": "Editable clone",
                "version": "1.0",
                "template_filename": "recap_template.xlsx",
                "is_active": False,
            },
        )
        self._write_json(
            profile_dir / "labor_mapping.json",
            {
                "raw_mappings": {"103/F": "103 Journeyman"},
                "saved_mappings": [
                    {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep me"},
                ],
            },
        )

        did_update = persist_observed_labor_raw_values(profile_dir, ["103/f", " 103/F "])
        updated = json.loads((profile_dir / "labor_mapping.json").read_text(encoding="utf-8"))

        self.assertFalse(did_update)
        self.assertEqual(
            updated["saved_mappings"],
            [
                {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep me"},
            ],
        )

    def test_persist_observed_labor_raw_values_skips_default_profile_without_writing(self) -> None:
        profile_dir = TEST_ROOT / "profiles" / "default"
        original = json.loads((profile_dir / "labor_mapping.json").read_text(encoding="utf-8"))

        did_update = persist_observed_labor_raw_values(profile_dir, ["103/F"])
        updated = json.loads((profile_dir / "labor_mapping.json").read_text(encoding="utf-8"))

        self.assertFalse(did_update)
        self.assertEqual(updated, original)


    def test_persist_observed_equipment_raw_values_appends_new_placeholder_and_preserves_existing_rows(self) -> None:
        profile_dir = TEST_ROOT / "profiles" / "editable_profile"
        shutil.copytree(TEST_ROOT / "profiles" / "default", profile_dir)
        self._write_json(
            profile_dir / "profile.json",
            {
                "profile_name": "editable_profile",
                "display_name": "Editable Profile",
                "description": "Editable clone",
                "version": "1.0",
                "template_filename": "recap_template.xlsx",
                "is_active": False,
            },
        )
        self._write_json(
            profile_dir / "equipment_mapping.json",
            {
                "raw_mappings": {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"},
                "saved_mappings": [
                    {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                ],
                "keyword_mappings": {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"},
            },
        )

        did_update = persist_observed_equipment_raw_values(profile_dir, ["627/2025 FORD TRANSIT VAN", "crane truck"])
        updated = json.loads((profile_dir / "equipment_mapping.json").read_text(encoding="utf-8"))

        self.assertTrue(did_update)
        self.assertEqual(updated["raw_mappings"], {"627/2025 FORD TRANSIT VAN": "Pick-up Truck"})
        self.assertNotIn("keyword_mappings", updated)
        self.assertEqual(
            updated["saved_mappings"],
            [
                {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                {"raw_description": "CRANE TRUCK", "target_category": ""},
            ],
        )

    def test_persist_observed_equipment_raw_values_skips_default_profile_without_writing(self) -> None:
        profile_dir = TEST_ROOT / "profiles" / "default"
        original = json.loads((profile_dir / "equipment_mapping.json").read_text(encoding="utf-8"))

        did_update = persist_observed_equipment_raw_values(profile_dir, ["CRANE TRUCK"])
        updated = json.loads((profile_dir / "equipment_mapping.json").read_text(encoding="utf-8"))

        self.assertFalse(did_update)
        self.assertEqual(updated, original)


    def test_settings_view_model_shows_persisted_observed_equipment_rows(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        profile_dir = TEST_ROOT / "profiles" / "editable_profile"
        persist_observed_equipment_raw_values(
            profile_dir,
            ["593/2024 Freightliner Bucket/MH", "619/2025 Freightliner Digger Derrick"],
        )

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()

        self.assertEqual(
            view_model.equipment_mapping_rows,
            [
                {"raw_description": "593/2024 FREIGHTLINER BUCKET/MH", "raw_pattern": "593/2024 FREIGHTLINER BUCKET/MH", "target_category": ""},
                {"raw_description": "619/2025 FREIGHTLINER DIGGER DERRICK", "raw_pattern": "619/2025 FREIGHTLINER DIGGER DERRICK", "target_category": ""},
            ],
        )

    def test_settings_view_model_shows_observed_equipment_rows_without_duplicate_placeholders(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch("job_cost_tool.app.viewmodels.settings_view_model.ProfileManager", return_value=manager):
            view_model = SettingsViewModel()
            view_model.set_observed_equipment_raw_values([
                "593/2024 Freightliner Bucket/MH",
                "593/2024   freightliner   bucket/mh",
            ])

        self.assertEqual(
            view_model.equipment_mapping_rows,
            [
                {"raw_description": "593/2024 FREIGHTLINER BUCKET/MH", "raw_pattern": "593/2024 FREIGHTLINER BUCKET/MH", "target_category": ""},
            ],
        )

    def test_review_view_model_load_and_reload_trigger_observed_labor_persistence(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        record = Record(
            record_type="labor",
            phase_code="20",
            raw_description="Labor line",
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="F",
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="source",
        )

        with patch("job_cost_tool.app.viewmodels.review_view_model.ProfileManager", return_value=manager), patch(
            "job_cost_tool.app.viewmodels.review_view_model.parse_pdf",
            return_value=[record],
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.normalize_records",
            return_value=[record],
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.validate_records",
            side_effect=lambda records: (records, []),
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.persist_observed_labor_raw_values"
        ) as persist_mock:
            view_model = ReviewViewModel()
            view_model.load_pdf("sample.pdf")
            view_model.reload_current_pdf()

        self.assertEqual(persist_mock.call_count, 2)
        first_call_args = persist_mock.call_args_list[0].args
        second_call_args = persist_mock.call_args_list[1].args
        self.assertEqual(first_call_args[0], manager.get_active_profile_dir())
        self.assertEqual(first_call_args[1], ["103/F"])
        self.assertEqual(second_call_args[1], ["103/F"])


    def test_review_view_model_load_and_reload_trigger_observed_equipment_persistence(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        record = Record(
            record_type="equipment",
            phase_code="20",
            raw_description="Equipment line",
            cost=100.0,
            hours=2.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description="627/2025 FORD TRANSIT VAN",
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="source",
        )

        with patch("job_cost_tool.app.viewmodels.review_view_model.ProfileManager", return_value=manager), patch(
            "job_cost_tool.app.viewmodels.review_view_model.parse_pdf",
            return_value=[record],
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.normalize_records",
            return_value=[record],
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.validate_records",
            side_effect=lambda records: (records, []),
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.persist_observed_labor_raw_values"
        ), patch(
            "job_cost_tool.app.viewmodels.review_view_model.persist_observed_equipment_raw_values"
        ) as persist_mock:
            view_model = ReviewViewModel()
            view_model.load_pdf("sample.pdf")
            view_model.reload_current_pdf()

        self.assertEqual(persist_mock.call_count, 2)
        first_call_args = persist_mock.call_args_list[0].args
        second_call_args = persist_mock.call_args_list[1].args
        self.assertEqual(first_call_args[0], manager.get_active_profile_dir())
        self.assertEqual(first_call_args[1], ["627/2025 FORD TRANSIT VAN"])
        self.assertEqual(second_call_args[1], ["627/2025 FORD TRANSIT VAN"])

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
