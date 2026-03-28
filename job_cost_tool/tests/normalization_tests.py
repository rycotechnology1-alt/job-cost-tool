"""Focused normalization tests for narrow business-rule exceptions."""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, Record
from job_cost_tool.core.normalization.equipment_normalizer import normalize_equipment_record
from job_cost_tool.core.normalization.labor_normalizer import normalize_labor_record
from job_cost_tool.core.normalization.normalizer import normalize_records
from job_cost_tool.services.validation_service import validate_records


class NormalizationRuleTests(unittest.TestCase):
    """Verify targeted normalization business rules."""

    def test_exact_raw_labor_mapping_wins_over_legacy_fallback(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
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
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={
                "raw_mappings": {"103/F": "Big Boy"},
                "aliases": {"F": "F"},
                "class_mappings": {"103": {"F": "Legacy Foreman"}},
                "apprentice_aliases": [],
            },
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={
                "classifications": ["Big Boy", "Legacy Foreman"],
                "slots": [
                    {"slot_id": "labor_1", "label": "Big Boy", "active": True},
                    {"slot_id": "labor_2", "label": "Legacy Foreman", "active": True},
                ],
            },
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertEqual(normalized_record.recap_labor_classification, "Big Boy")
        self.assertEqual(normalized_record.recap_labor_slot_id, "labor_1")
        self.assertEqual(normalized_record.record_type_normalized, LABOR)

    def test_raw_mappings_only_config_normalizes_without_legacy_fields(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
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
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={
                "raw_mappings": {"103/F": "Big Boy"},
                "saved_mappings": [
                    {"raw_value": "103/F", "target_classification": "Big Boy", "notes": ""}
                ],
            },
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={
                "classifications": ["Big Boy"],
                "slots": [{"slot_id": "labor_1", "label": "Big Boy", "active": True}],
            },
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertEqual(normalized_record.recap_labor_classification, "Big Boy")
        self.assertEqual(normalized_record.recap_labor_slot_id, "labor_1")
        self.assertEqual(normalized_record.record_type_normalized, LABOR)

    def test_unmapped_raw_labor_key_no_longer_falls_back_to_legacy_mapping(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
            hours=8.0,
            hour_type="ST",
            union_code="999",
            labor_class_raw="F",
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={
                "aliases": {"F": "F"},
                "class_mappings": {"*": {"F": "Big Boy"}},
                "apprentice_aliases": [],
            },
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={
                "classifications": ["Big Boy"],
                "slots": [{"slot_id": "labor_1", "label": "Big Boy", "active": True}],
            },
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.recap_labor_classification)
        self.assertIsNone(normalized_record.recap_labor_slot_id)
        self.assertEqual(normalized_record.labor_class_normalized, "F")
        self.assertTrue(
            any("999/F" in warning and "not mapped" in warning.casefold() for warning in normalized_record.warnings)
        )
        self.assertEqual(normalized_record.confidence, 0.6)

    def test_exact_raw_mapping_lookup_canonicalizes_spacing_and_case(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
            hours=8.0,
            hour_type="ST",
            union_code=" 103 ",
            labor_class_raw="  f  ",
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={
                "raw_mappings": {"103/F": "Big Boy"},
            },
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={
                "classifications": ["Big Boy"],
                "slots": [{"slot_id": "labor_1", "label": "Big Boy", "active": True}],
            },
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertEqual(normalized_record.recap_labor_classification, "Big Boy")
        self.assertEqual(normalized_record.labor_class_normalized, "F")

    def test_invalid_raw_mapping_target_warns_and_remains_unmapped(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
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
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={
                "raw_mappings": {"103/F": "Not In Profile"},
                "aliases": {"F": "F"},
                "class_mappings": {"103": {"F": "103 Foreman"}},
                "apprentice_aliases": [],
            },
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={
                "classifications": ["103 Foreman"],
                "slots": [{"slot_id": "labor_1", "label": "103 Foreman", "active": True}],
            },
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.recap_labor_classification)
        self.assertTrue(
            any("103/F" in warning and "not valid" in warning.casefold() for warning in normalized_record.warnings)
        )

    def test_inactive_raw_mapping_target_warns_and_remains_unmapped(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
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
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={"raw_mappings": {"103/F": "Big Boy"}},
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={
                "classifications": ["Big Boy"],
                "slots": [{"slot_id": "labor_1", "label": "Big Boy", "active": False}],
            },
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.recap_labor_classification)
        self.assertTrue(any("not active" in warning.casefold() for warning in normalized_record.warnings))

    def test_missing_labor_class_raw_still_warns_appropriately(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Labor source",
        )

        with patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_labor_mapping",
            return_value={"raw_mappings": {}},
        ), patch(
            "job_cost_tool.core.normalization.labor_normalizer.ConfigLoader.get_target_labor_classifications",
            return_value={"classifications": [], "slots": []},
        ):
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()
            normalized_record = normalize_labor_record(record)
            normalize_labor_record.__globals__["_get_labor_mapping"].cache_clear()
            normalize_labor_record.__globals__["_get_target_labor_classifications"].cache_clear()
            normalize_labor_record.__globals__["_get_active_labor_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.recap_labor_classification)
        self.assertTrue(any("missing a raw labor class" in warning.casefold() for warning in normalized_record.warnings))


    def test_raw_only_equipment_config_normalizes_without_keyword_fallback(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
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
            source_line_text="Equipment source",
        )

        with patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_equipment_mapping",
            return_value={
                "raw_mappings": {"627/2025 FORD TRANSIT VAN": "Utility Van"},
                "saved_mappings": [
                    {"raw_description": "627/2025 FORD TRANSIT VAN", "target_category": "Utility Van"}
                ],
            },
        ), patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_target_equipment_classifications",
            return_value={
                "classifications": ["Utility Van"],
                "slots": [{"slot_id": "equipment_1", "label": "Utility Van", "active": True}],
            },
        ):
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()
            normalized_record = normalize_equipment_record(record)
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()

        self.assertEqual(normalized_record.equipment_category, "Utility Van")
        self.assertEqual(normalized_record.recap_equipment_slot_id, "equipment_1")

    def test_unmapped_raw_equipment_description_no_longer_falls_back_to_keyword_matching(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
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
            source_line_text="Equipment source",
        )

        with patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_equipment_mapping",
            return_value={"keyword_mappings": {"FORD TRANSIT": "Utility Van"}},
        ), patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_target_equipment_classifications",
            return_value={
                "classifications": ["Utility Van"],
                "slots": [{"slot_id": "equipment_1", "label": "Utility Van", "active": True}],
            },
        ):
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()
            normalized_record = normalize_equipment_record(record)
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.equipment_category)
        self.assertIsNone(normalized_record.recap_equipment_slot_id)
        self.assertTrue(any("did not match" in warning.casefold() for warning in normalized_record.warnings))
        self.assertEqual(normalized_record.confidence, 0.6)

    def test_exact_raw_equipment_lookup_canonicalizes_spacing_and_case(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
            hours=2.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description="  627/2025   ford   transit van  ",
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Equipment source",
        )

        with patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_equipment_mapping",
            return_value={"raw_mappings": {"627/2025 FORD TRANSIT VAN": "Utility Van"}},
        ), patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_target_equipment_classifications",
            return_value={
                "classifications": ["Utility Van"],
                "slots": [{"slot_id": "equipment_1", "label": "Utility Van", "active": True}],
            },
        ):
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()
            normalized_record = normalize_equipment_record(record)
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()

        self.assertEqual(normalized_record.equipment_category, "Utility Van")

    def test_invalid_raw_equipment_mapping_warns_and_remains_unmapped(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
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
            source_line_text="Equipment source",
        )

        with patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_equipment_mapping",
            return_value={"raw_mappings": {"627/2025 FORD TRANSIT VAN": "Not In Profile"}},
        ), patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_target_equipment_classifications",
            return_value={
                "classifications": ["Utility Van"],
                "slots": [{"slot_id": "equipment_1", "label": "Utility Van", "active": True}],
            },
        ):
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()
            normalized_record = normalize_equipment_record(record)
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.equipment_category)
        self.assertIsNone(normalized_record.recap_equipment_slot_id)
        self.assertTrue(any("invalid target" in warning.casefold() for warning in normalized_record.warnings))
        self.assertEqual(normalized_record.confidence, 0.6)

    def test_inactive_raw_equipment_mapping_warns_and_remains_unmapped(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
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
            source_line_text="Equipment source",
        )

        with patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_equipment_mapping",
            return_value={"raw_mappings": {"627/2025 FORD TRANSIT VAN": "Utility Van"}},
        ), patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_target_equipment_classifications",
            return_value={
                "classifications": ["Utility Van"],
                "slots": [
                    {"slot_id": "equipment_1", "label": "Utility Van", "active": False},
                ],
            },
        ):
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()
            normalized_record = normalize_equipment_record(record)
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.equipment_category)
        self.assertIsNone(normalized_record.recap_equipment_slot_id)
        self.assertTrue(any("inactive target" in warning.casefold() for warning in normalized_record.warnings))
        self.assertEqual(normalized_record.confidence, 0.6)

    def test_missing_equipment_description_still_warns_appropriately(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
            hours=2.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Equipment source",
        )

        with patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_equipment_mapping",
            return_value={"raw_mappings": {}},
        ), patch(
            "job_cost_tool.core.normalization.equipment_normalizer.ConfigLoader.get_target_equipment_classifications",
            return_value={"classifications": [], "slots": []},
        ):
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()
            normalized_record = normalize_equipment_record(record)
            normalize_equipment_record.__globals__["_get_equipment_mapping"].cache_clear()
            normalize_equipment_record.__globals__["_get_target_equipment_classifications"].cache_clear()
            normalize_equipment_record.__globals__["_get_active_equipment_slot_lookup"].cache_clear()

        self.assertIsNone(normalized_record.equipment_category)
        self.assertTrue(any("missing a raw equipment description" in warning.casefold() for warning in normalized_record.warnings))

    def test_family_routing_remains_intact_for_mixed_records(self) -> None:
        labor_record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
            hours=8.0,
            hour_type="ST",
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Labor source",
        )
        equipment_record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
            hours=2.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Equipment source",
        )
        material_record = Record(
            record_type=MATERIAL,
            phase_code="50",
            raw_description="Material line",
            cost=25,
            hours=None,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="Material source",
        )

        phase_cache = normalize_records.__globals__["_get_phase_mapping"]
        phase_cache.cache_clear()
        with patch(
            "job_cost_tool.core.normalization.normalizer.ConfigLoader.get_phase_mapping",
            return_value={},
        ), patch(
            "job_cost_tool.core.normalization.normalizer.normalize_labor_record",
            side_effect=lambda record: replace(record, warnings=record.warnings + ["labor path"]),
        ), patch(
            "job_cost_tool.core.normalization.normalizer.normalize_equipment_record",
            side_effect=lambda record: replace(record, warnings=record.warnings + ["equipment path"]),
        ), patch(
            "job_cost_tool.core.normalization.normalizer.normalize_material_record",
            side_effect=lambda record: replace(record, warnings=record.warnings + ["material path"]),
        ):
            normalized_records = normalize_records([labor_record, equipment_record, material_record])
        phase_cache.cache_clear()

        self.assertIn("labor path", normalized_records[0].warnings)
        self.assertIn("equipment path", normalized_records[1].warnings)
        self.assertIn("material path", normalized_records[2].warnings)

    def test_phase_50_job_reimbursement_normalizes_to_employee_expense_material(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="50",
            raw_description="PR 03/09/26 103/F 1.00 / 205 / Dondero Jr, John A15 Job Reimb 0.00 ST 382.46",
            cost=382.46,
            hours=0.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="F",
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.3,
            warnings=["PR detail line family is ambiguous and should be reviewed."],
            employee_name="Dondero Jr, John",
            source_page=1,
            source_line_text="PR 03/09/26 103/F 1.00 / 205 / Dondero Jr, John A15 Job Reimbursement 0.00 ST 382.46",
        )

        normalized_record = normalize_records([record])[0]
        validated_records, blocking_issues = validate_records([normalized_record])
        validated_record = validated_records[0]

        self.assertEqual(normalized_record.record_type_normalized, MATERIAL)
        self.assertEqual(normalized_record.vendor_name_normalized, "Employee Expense")
        self.assertGreaterEqual(normalized_record.confidence, 0.6)
        self.assertFalse(any("ambiguous" in warning.casefold() for warning in normalized_record.warnings))
        self.assertFalse(any("missing a vendor name" in warning.casefold() for warning in normalized_record.warnings))
        self.assertEqual(blocking_issues, [])
        self.assertEqual(validated_record.vendor_name_normalized, "Employee Expense")


if __name__ == "__main__":
    unittest.main()
