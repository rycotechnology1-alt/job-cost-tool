"""Lightweight tests for profile-aware config loading."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import ConfigLoader, ProfileManager


TEST_ROOT = Path("tests/_profile_tmp")


class ProfileConfigTests(unittest.TestCase):
    """Verify the remaining shared profile and config behavior after desktop removal."""

    def setUp(self) -> None:
        ConfigLoader._shared_cache.clear()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        (TEST_ROOT / "profiles" / "default").mkdir(parents=True, exist_ok=True)
        (TEST_ROOT / "legacy_config").mkdir(parents=True, exist_ok=True)

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
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "labor_mapping.json",
            {"raw_mappings": {}, "saved_mappings": []},
        )
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "equipment_mapping.json",
            {"raw_mappings": {}, "saved_mappings": []},
        )
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
                "labor_rows": {"Journeyman": {"st_hours": "B1"}},
                "equipment_rows": {"Truck": {"hours_qty": "C1"}},
                "materials_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "amount": "B"}},
                "subcontractors_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "description": "B", "amount": "C"}},
                "permits_fees_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
                "police_detail_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
            },
        )
        (TEST_ROOT / "profiles" / "default" / "recap_template.xlsx").write_bytes(b"template")

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_profile_manager_discovers_profile_and_metadata(self) -> None:
        with patch("core.config.profile_manager.get_app_settings_path", return_value=TEST_ROOT / "missing_app_settings.json"):
            manager = ProfileManager(
                profiles_root=TEST_ROOT / "profiles",
                legacy_config_root=TEST_ROOT / "legacy_config",
            )

        profiles = manager.list_profiles()

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_name"], "default")
        self.assertEqual(profiles[0]["display_name"], "Default Profile")
        self.assertEqual(profiles[0]["description"], "Test profile")
        self.assertEqual(profiles[0]["template_filename"], "recap_template.xlsx")
        self.assertEqual(manager.get_profile_dir("default"), (TEST_ROOT / "profiles" / "default").resolve())

    def test_config_loader_reads_required_and_optional_profile_configs(self) -> None:
        loader = ConfigLoader(
            config_dir=TEST_ROOT / "profiles" / "default",
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )

        self.assertEqual(loader.get_labor_mapping(), {"raw_mappings": {}, "saved_mappings": []})
        self.assertEqual(loader.get_equipment_mapping(), {"raw_mappings": {}, "saved_mappings": []})
        self.assertEqual(loader.get_input_model(), {"report_type": "vista_job_cost", "section_headers": {}})
        self.assertEqual(loader.get_target_labor_classifications()["classifications"], ["103 Journeyman"])
        self.assertEqual(loader.get_target_equipment_classifications()["classifications"], ["Pick-up Truck"])
        self.assertEqual(loader.get_rates(), {"labor_rates": {}, "equipment_rates": {}})
        self.assertEqual(loader.get_review_rules(), {"default_omit_rules": []})
        self.assertEqual(loader.get_template_path(), (TEST_ROOT / "profiles" / "default" / "recap_template.xlsx").resolve())

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

        loader = ConfigLoader(
            config_dir=TEST_ROOT / "profiles" / "default",
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )
        slots = loader.get_labor_slots()

        self.assertEqual(slots["capacity"], 2)
        self.assertEqual(slots["classifications"], ["Legacy A", "Legacy B"])
        self.assertEqual(slots["slots"][0]["slot_id"], "labor_1")
        self.assertEqual(slots["slots"][1]["slot_id"], "labor_2")
        self.assertEqual(slots["slots"][2], {"slot_id": "labor_3", "label": "Legacy C", "active": False})

    def test_config_loader_normalizes_template_metadata(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "template_metadata.json",
            {
                "display_label": "Crew Template",
                "labor_rows": [
                    {"row_id": "labor_row_1", "template_label": "Journeyman", "mapping": {"st_hours": "B1"}},
                    {"row_id": "labor_row_2", "template_label": "Foreman", "mapping": {"st_hours": "B2"}},
                ],
                "equipment_rows": [
                    {"row_id": "equipment_row_1", "template_label": "Truck", "mapping": {"hours_qty": "C1"}},
                ],
                "export_behaviors": {"collapse_inactive_classifications": False},
            },
        )

        loader = ConfigLoader(
            config_dir=TEST_ROOT / "profiles" / "default",
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )

        self.assertEqual(
            loader.get_template_metadata(),
            {
                "template_id": "recap-template",
                "display_label": "Crew Template",
                "template_filename": "recap_template.xlsx",
                "template_artifact_ref": "recap_template.xlsx",
                "template_file_hash": None,
                "labor_active_slot_capacity": 2,
                "equipment_active_slot_capacity": 1,
                "labor_rows": [
                    {"row_id": "labor_row_1", "template_label": "Journeyman", "mapping": {"st_hours": "B1"}},
                    {"row_id": "labor_row_2", "template_label": "Foreman", "mapping": {"st_hours": "B2"}},
                ],
                "equipment_rows": [
                    {"row_id": "equipment_row_1", "template_label": "Truck", "mapping": {"hours_qty": "C1"}},
                ],
                "export_behaviors": {"collapse_inactive_classifications": False},
            },
        )

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
