"""Lightweight tests for profile-aware config loading."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from job_cost_tool.app.viewmodels.settings_view_model import (
    _validate_equipment_classification_references,
    _validate_labor_classification_references,
)
from job_cost_tool.core.config import ConfigLoader, ProfileManager


TEST_ROOT = Path("job_cost_tool/tests/_profile_tmp")


class ProfileConfigTests(unittest.TestCase):
    """Verify profile discovery and active-profile config loading."""

    def setUp(self) -> None:
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
