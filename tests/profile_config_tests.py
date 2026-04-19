"""Lightweight tests for profile-aware config loading."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from core.config import ConfigLoader, ProfileManager
from services.profile_bundle_helpers import (
    active_labels_from_slots,
    build_slot_label_rename_map,
    validate_slot_rows,
)


TEST_ROOT = Path("tests/_profile_tmp")


class ProfileConfigTests(unittest.TestCase):
    """Verify shared profile discovery and config loading behavior."""

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
        self._write_json(self.settings_path, {"active_profile": "default"})
        self._write_json(
            TEST_ROOT / "legacy_config" / "phase_catalog.json",
            {
                "phases": [
                    {"phase_code": "29 .   .", "phase_name": "Market Recovery"},
                    {"phase_code": "29 .999.", "phase_name": "Labor-Non-Job Related Time"},
                    {"phase_code": "50 .15 .", "phase_name": "Utility Service Connections"},
                ]
            },
        )

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_profile_manager_discovers_default_profile_and_metadata(self) -> None:
        manager = self._build_manager()

        profiles = manager.list_profiles()

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["profile_name"], "default")
        self.assertEqual(manager.get_active_profile_name(), "default")
        self.assertEqual(manager.get_active_profile_dir(), (TEST_ROOT / "profiles" / "default").resolve())
        self.assertEqual(
            manager.get_active_profile_metadata(),
            {
                "profile_name": "default",
                "display_name": "Default Profile",
                "description": "Test profile",
                "version": "1.0",
                "template_filename": "recap_template.xlsx",
                "is_active": False,
                "profile_dir": str((TEST_ROOT / "profiles" / "default").resolve()),
                "is_active_profile": True,
            },
        )

    def test_config_loader_reads_required_and_optional_profile_configs(self) -> None:
        manager = self._build_manager()
        loader = ConfigLoader(
            config_dir=manager.get_active_profile_dir(),
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )

        self.assertEqual(loader.get_target_labor_classifications()["classifications"], ["103 Journeyman"])
        self.assertEqual(loader.get_labor_slots()["slots"][0]["slot_id"], "labor_1")
        self.assertEqual(loader.get_rates(), {"labor_rates": {}, "equipment_rates": {}})
        self.assertEqual(loader.get_review_rules(), {"default_omit_rules": []})
        self.assertEqual(
            loader.get_phase_catalog(),
            {
                "phases": [
                    {"phase_code": "29", "phase_name": "Market Recovery"},
                    {"phase_code": "29 .999", "phase_name": "Labor-Non-Job Related Time"},
                    {"phase_code": "50 .15", "phase_name": "Utility Service Connections"},
                ]
            },
        )
        self.assertEqual(loader.get_template_path(), (TEST_ROOT / "profiles" / "default" / "recap_template.xlsx").resolve())

    def test_config_loader_normalizes_default_omit_rules_by_phase_code(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "review_rules.json",
            {
                "default_omit_rules": [
                    {"phase_code": " 29 .999. "},
                    {"phase_code": "29 .999"},
                    {"phase_code": ""},
                    {},
                ]
            },
        )

        loader = ConfigLoader(
            config_dir=(TEST_ROOT / "profiles" / "default"),
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )

        self.assertEqual(loader.get_review_rules(), {"default_omit_rules": [{"phase_code": "29 .999"}]})

    def test_config_loader_canonicalizes_phase_mapping_keys(self) -> None:
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "phase_mapping.json",
            {"29 .   .": "MATERIAL", "29 .999.": "LABOR", "13 .25 .": "MATERIAL"},
        )

        loader = ConfigLoader(
            config_dir=(TEST_ROOT / "profiles" / "default"),
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )

        self.assertEqual(
            loader.get_phase_mapping(),
            {"29": "MATERIAL", "29 .999": "LABOR", "13 .25": "MATERIAL"},
        )

    def test_config_loader_canonicalizes_shared_phase_catalog_rows(self) -> None:
        self._write_json(
            TEST_ROOT / "legacy_config" / "phase_catalog.json",
            {
                "phases": [
                    {"phase_code": "13 .25 .", "phase_name": "Material-Transfer"},
                    {"phase_code": "13 .5  .", "phase_name": "Freight In"},
                    {"phase_code": "29 .   .", "phase_name": "Market Recovery"},
                    {"phase_code": "29 .999.", "phase_name": "Labor-Non-Job Related Time"},
                ]
            },
        )

        loader = ConfigLoader(
            config_dir=(TEST_ROOT / "profiles" / "default"),
            legacy_config_dir=TEST_ROOT / "legacy_config",
        )

        self.assertEqual(
            loader.get_phase_catalog(),
            {
                "phases": [
                    {"phase_code": "13 .25", "phase_name": "Material-Transfer"},
                    {"phase_code": "13 .5", "phase_name": "Freight In"},
                    {"phase_code": "29", "phase_name": "Market Recovery"},
                    {"phase_code": "29 .999", "phase_name": "Labor-Non-Job Related Time"},
                ]
            },
        )

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
            config_dir=(TEST_ROOT / "profiles" / "default"),
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
            config_dir=(TEST_ROOT / "profiles" / "default"),
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

    def test_validate_slot_rows_rejects_duplicate_active_labels(self) -> None:
        existing_slots = [
            {"slot_id": "labor_1", "label": "Old A", "active": True},
            {"slot_id": "labor_2", "label": "Old B", "active": True},
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate active labor classification"):
            validate_slot_rows(
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
        updated_slots = validate_slot_rows(
            [
                {"slot_id": "labor_1", "label": "New A", "active": True},
                {"slot_id": "labor_2", "label": "", "active": False},
            ],
            existing_slots=previous_slots,
            slot_label="Labor",
        )

        self.assertEqual(active_labels_from_slots(updated_slots), ["New A"])
        self.assertEqual(build_slot_label_rename_map(previous_slots, updated_slots), {"Old A": "New A"})

    def _build_manager(self) -> ProfileManager:
        return ProfileManager(
            profiles_root=TEST_ROOT / "profiles",
            settings_path=self.settings_path,
            legacy_config_root=TEST_ROOT / "legacy_config",
        )

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
