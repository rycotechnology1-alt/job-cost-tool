"""Service-level tests for non-Qt settings/profile workflow orchestration."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import ConfigLoader, ProfileManager
from services.settings_workflow_service import SettingsWorkflowService


TEST_ROOT = Path("tests/_settings_workflow_tmp")


class SettingsWorkflowServiceTests(unittest.TestCase):
    """Verify settings workflow behavior outside the Qt view-model layer."""

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
                "labor_rows": {},
                "equipment_rows": {},
                "materials_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "amount": "B"}},
                "subcontractors_section": {
                    "start_row": 1,
                    "end_row": 1,
                    "columns": {"name": "A", "description": "B", "amount": "C"},
                },
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
                    {"phase_code": "13 .25 .", "phase_name": "Material-Transfer"},
                    {"phase_code": "29 .   .", "phase_name": "Market Recovery"},
                    {"phase_code": "29 .999.", "phase_name": "Labor-Non-Job Related Time"},
                    {"phase_code": "50 .15 .", "phase_name": "Utility Service Connections"},
                ]
            },
        )

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_service_saves_default_omit_rules_with_canonical_phase_codes(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch(
            "core.config.config_loader.get_legacy_config_root",
            return_value=TEST_ROOT / "legacy_config",
        ):
            service = SettingsWorkflowService(profile_manager=manager)
            message = service.save_default_omit_rules(
                [
                    {"phase_code": " 29 .999. "},
                    {"phase_code": "13 .25 ."},
                ]
            )

        self.assertEqual(
            message,
            "Default omit rules saved. Reprocess the current PDF to apply them to loaded records.",
        )
        self.assertEqual(
            service.default_omit_rule_rows,
            [
                {"phase_code": "29 .999", "phase_name": "Labor-Non-Job Related Time"},
                {"phase_code": "13 .25", "phase_name": "Material-Transfer"},
            ],
        )
        self.assertIn({"phase_code": "50 .15", "phase_name": "Utility Service Connections"}, service.available_default_omit_phase_options)

    def test_service_merges_observed_values_into_editor_state(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")

        with patch(
            "core.config.config_loader.get_legacy_config_root",
            return_value=TEST_ROOT / "legacy_config",
        ):
            service = SettingsWorkflowService(profile_manager=manager)
            self.assertTrue(
                service.set_observed_phase_options(
                    [
                        {"phase_code": "29 .999.", "phase_name": "Labor-Non-Job Related Time"},
                        {"phase_code": "29 .999", "phase_name": ""},
                    ]
                )
            )
            self.assertTrue(service.set_observed_labor_raw_values(["103/F", "103/f"]))
            self.assertTrue(
                service.set_observed_equipment_raw_values(
                    ["593/2024 Freightliner Bucket/MH", "593/2024 freightliner bucket/mh"]
                )
            )

        self.assertIn(
            {"raw_value": "103/F", "target_classification": "", "notes": "", "is_observed": True},
            service.labor_mapping_rows,
        )
        self.assertEqual(
            service.equipment_mapping_rows,
            [
                {
                    "raw_description": "FREIGHTLINER BUCKET/MH",
                    "raw_pattern": "FREIGHTLINER BUCKET/MH",
                    "target_category": "",
                    "is_observed": True,
                }
            ],
        )
        self.assertIn(
            {"phase_code": "29 .999", "phase_name": "Labor-Non-Job Related Time"},
            service.available_default_omit_phase_options,
        )
        self.assertFalse(service.set_observed_labor_raw_values(["103/F"]))

    def test_service_switches_active_profile_and_reloads_state(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        service = SettingsWorkflowService(profile_manager=manager)

        message = service.set_active_profile("editable_profile")

        self.assertEqual(
            message,
            "Active profile changed to Editable Profile. Reload or reprocess the current PDF to apply the new profile bundle to loaded records.",
        )
        self.assertEqual(service.active_profile.get("profile_name"), "editable_profile")
        self.assertEqual(service.active_profile.get("display_name"), "Editable Profile")

    def test_service_saves_labor_mappings_and_reloads_rows(self) -> None:
        manager = self._build_manager()
        manager.duplicate_profile(
            source_profile_name="default",
            new_profile_name="editable_profile",
            display_name="Editable Profile",
            description="Editable clone",
        )
        manager.set_active_profile("editable_profile")
        service = SettingsWorkflowService(profile_manager=manager)

        message = service.save_labor_mappings(
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
            service.labor_mapping_rows,
            [
                {"raw_value": "104/EO", "target_classification": "", "notes": "review later"},
                {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "mapped"},
            ],
        )

    def _build_manager(self) -> ProfileManager:
        return ProfileManager(
            profiles_root=TEST_ROOT / "profiles",
            settings_path=self.settings_path,
            legacy_config_root=TEST_ROOT / "legacy_config",
        )

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
