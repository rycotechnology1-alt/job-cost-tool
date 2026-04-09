"""Service-level tests for non-Qt review workflow orchestration."""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import ConfigLoader, ProfileManager
from core.models.record import EQUIPMENT, LABOR, MATERIAL, Record
from services.review_workflow_service import load_edit_options, load_review_data, update_review_record


TEST_ROOT = Path("tests/_review_workflow_tmp")


class ReviewWorkflowServiceTests(unittest.TestCase):
    """Verify review workflow orchestration without Qt view-model dependencies."""

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

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_load_review_data_applies_default_omit_rules_without_dropping_records(self) -> None:
        manager = self._build_manager()
        loader_class = ConfigLoader
        self._write_json(
            TEST_ROOT / "profiles" / "default" / "review_rules.json",
            {"default_omit_rules": [{"phase_code": "29 .999."}]},
        )

        matching_record = Record(
            record_type=LABOR,
            phase_code="29 .999",
            raw_description="Non-job-related labor line",
            cost=973.98,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized="J",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            phase_name_raw="Labor-Non-Job Related Time",
            source_page=1,
            source_line_text="PR 03/12/26 ...",
            record_type_normalized=LABOR,
            recap_labor_slot_id=None,
            recap_labor_classification=None,
        )
        non_matching_record = Record(
            record_type=MATERIAL,
            phase_code="29",
            raw_description="Market recovery line",
            cost=-28950.0,
            hours=None,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name="Market Recovery",
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            phase_name_raw="Market Recovery",
            source_page=1,
            source_line_text="IC 12/22/25 ...",
            record_type_normalized=MATERIAL,
            vendor_name_normalized="Market Recovery",
        )

        with patch(
            "services.review_workflow_service.ConfigLoader",
            side_effect=lambda *args, **kwargs: loader_class(config_dir=manager.get_active_profile_dir()),
        ), patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[matching_record, non_matching_record],
        ), patch(
            "services.review_workflow_service.normalize_records",
            return_value=[matching_record, non_matching_record],
        ):
            result = load_review_data("sample.pdf")

        self.assertEqual(len(result.records), 2)
        self.assertTrue(result.records[0].is_omitted)
        self.assertFalse(result.records[1].is_omitted)
        self.assertEqual(result.blocking_issues, [])
        self.assertEqual(result.status_text, "Processed 2 records from sample.pdf. Ready for review.")

    def test_update_review_record_surfaces_blocking_issue_when_manual_unomit_removes_default_omit(self) -> None:
        manager = self._build_manager()
        loader_class = ConfigLoader

        record = Record(
            record_type=LABOR,
            phase_code="29 .999",
            raw_description="Non-job-related labor line",
            cost=973.98,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized="J",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            phase_name_raw="Labor-Non-Job Related Time",
            source_page=1,
            source_line_text="PR 03/12/26 ...",
            record_type_normalized=LABOR,
            recap_labor_slot_id=None,
            recap_labor_classification=None,
            is_omitted=True,
        )

        with patch(
            "services.review_workflow_service.ConfigLoader",
            side_effect=lambda *args, **kwargs: loader_class(config_dir=manager.get_active_profile_dir()),
        ):
            result = update_review_record([record], 0, {"is_omitted": False}, file_path="sample.pdf")

        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected review update result.")
        self.assertFalse(result.records[0].is_omitted)
        self.assertIn(
            "Record on page 1 (phase 29 .999, labor): Recap labor classification is missing.",
            result.blocking_issues,
        )
        self.assertEqual(
            result.status_text,
            "Changes applied. Processed 1 records from sample.pdf. Export blocked by 1 issue(s).",
        )

    def test_update_review_record_resolves_slot_ids_for_classification_edits(self) -> None:
        manager = self._build_manager()
        loader_class = ConfigLoader

        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized="J",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="source",
            record_type_normalized=LABOR,
            recap_labor_slot_id=None,
            recap_labor_classification=None,
            is_omitted=True,
        )

        with patch(
            "services.review_workflow_service.ConfigLoader",
            side_effect=lambda *args, **kwargs: loader_class(config_dir=manager.get_active_profile_dir()),
        ), patch(
            "services.review_workflow_service.validate_records",
            side_effect=lambda records: (records, []),
        ):
            result = update_review_record(
                [record],
                0,
                {"recap_labor_classification": "103 Journeyman", "is_omitted": True},
                file_path="sample.pdf",
            )

        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected review update result.")
        self.assertEqual(result.review_records[0].recap_labor_classification, "103 Journeyman")
        self.assertEqual(result.review_records[0].recap_labor_slot_id, "labor_1")

    def test_update_review_record_rejects_unknown_labor_classification(self) -> None:
        manager = self._build_manager()
        loader_class = ConfigLoader

        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized="J",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="source",
            record_type_normalized=LABOR,
            recap_labor_slot_id=None,
            recap_labor_classification=None,
            is_omitted=True,
        )

        with patch(
            "services.review_workflow_service.ConfigLoader",
            side_effect=lambda *args, **kwargs: loader_class(config_dir=manager.get_active_profile_dir()),
        ):
            with self.assertRaisesRegex(ValueError, "Labor classification 'Not Allowed' is not allowed for this review."):
                update_review_record(
                    [record],
                    0,
                    {"recap_labor_classification": "Not Allowed"},
                    file_path="sample.pdf",
                )

    def test_update_review_record_rejects_unknown_equipment_classification(self) -> None:
        manager = self._build_manager()
        loader_class = ConfigLoader

        record = Record(
            record_type=EQUIPMENT,
            phase_code="20",
            raw_description="Equipment line",
            cost=100.0,
            hours=8.0,
            hour_type="EA",
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description="Pickup truck",
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="source",
            record_type_normalized=EQUIPMENT,
            recap_equipment_slot_id=None,
            is_omitted=False,
        )

        with patch(
            "services.review_workflow_service.ConfigLoader",
            side_effect=lambda *args, **kwargs: loader_class(config_dir=manager.get_active_profile_dir()),
        ):
            with self.assertRaisesRegex(ValueError, "Equipment classification 'Not Allowed' is not allowed for this review."):
                update_review_record(
                    [record],
                    0,
                    {"equipment_category": "Not Allowed"},
                    file_path="sample.pdf",
                )

    def test_load_edit_options_returns_profile_defined_choices(self) -> None:
        manager = self._build_manager()
        loader_class = ConfigLoader

        with patch(
            "services.review_workflow_service.ConfigLoader",
            side_effect=lambda *args, **kwargs: loader_class(config_dir=manager.get_active_profile_dir()),
        ):
            labor_options, equipment_options = load_edit_options()

        self.assertEqual(labor_options, ["103 Journeyman"])
        self.assertEqual(equipment_options, ["Pick-up Truck"])

    def _build_manager(self) -> ProfileManager:
        return ProfileManager(
            profiles_root=TEST_ROOT / "profiles",
            settings_path=self.settings_path,
            legacy_config_root=TEST_ROOT / "legacy_config",
        )

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
