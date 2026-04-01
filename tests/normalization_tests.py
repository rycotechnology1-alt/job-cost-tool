"""Focused normalization tests for narrow business-rule exceptions."""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, SUBCONTRACTOR, Record
from job_cost_tool.core.equipment_keys import derive_equipment_mapping_key
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


    def test_phase_2_equipment_mapping_key_cleanup_normalizes_low_risk_variants(self) -> None:
        self.assertEqual(
            derive_equipment_mapping_key("567/2021 Chevrolet 2500 Pick Up"),
            "CHEVROLET 2500 PICK UP",
        )
        self.assertEqual(
            derive_equipment_mapping_key("638/2025 Ford F600 Bucket/ Material Handler"),
            "FORD F600 BUCKET/MAT HANDLER",
        )
        self.assertEqual(
            derive_equipment_mapping_key("638/2025 Ford F600 Bucket / Mat Handler"),
            "FORD F600 BUCKET/MAT HANDLER",
        )
        self.assertEqual(
            derive_equipment_mapping_key("638/2025 Ford F600 Bucket/ MH"),
            "FORD F600 BUCKET/MH",
        )
        self.assertEqual(
            derive_equipment_mapping_key("504/Ford F550 Hi-Rai Bucket Truck W/ Liftgate"),
            "FORD F550 HI-RAI BUCKET TRUCK W/LIFT GATE",
        )
        self.assertEqual(
            derive_equipment_mapping_key("751/Kubota Tracked Skid Steer"),
            "KUBOTA TRACKED SKID STEER",
        )

    def test_equipment_mapping_key_corrects_obvious_spelling_and_wording_variants(self) -> None:
        self.assertEqual(
            derive_equipment_mapping_key("504/Chevy 2500 Utiltiy Body"),
            "CHEVROLET 2500 UTILITY BODY",
        )
        self.assertEqual(
            derive_equipment_mapping_key("365/2018 Freightliner Digger Derrick Handelr"),
            "FREIGHTLINER DIGGER DERRICK HANDLER",
        )
        self.assertEqual(
            derive_equipment_mapping_key("409/2019 GMC Savanna Van"),
            "GMC SAVANA VAN",
        )
        self.assertEqual(
            derive_equipment_mapping_key("410/2019 GMC Savana Van"),
            "GMC SAVANA VAN",
        )

    def test_equipment_mapping_key_normalizes_ram_model_spacing_consistently(self) -> None:
        self.assertEqual(
            derive_equipment_mapping_key("504/Dodge Ram5500 Hi-Rai Bucket Truck"),
            "DODGE RAM 5500 HI-RAI BUCKET TRUCK",
        )
        self.assertEqual(
            derive_equipment_mapping_key("505/Dodge Ram 5500 Hi-Rai Bucket Truck"),
            "DODGE RAM 5500 HI-RAI BUCKET TRUCK",
        )
        self.assertEqual(
            derive_equipment_mapping_key("506/Ram5500 Hi-Rai Bucket Truck"),
            "RAM 5500 HI-RAI BUCKET TRUCK",
        )

    def test_equipment_mapping_key_preserves_meaningful_distinctions(self) -> None:
        self.assertNotEqual(
            derive_equipment_mapping_key("409/2019 Isuzu 16' Box Truck"),
            derive_equipment_mapping_key("504/Chevrolet 2500 Utility Body"),
        )
        self.assertNotEqual(
            derive_equipment_mapping_key("638/2025 Ford F600 Bucket/ Material Handler"),
            derive_equipment_mapping_key("504/Ford F550 Hi-Rai Bucket Truck"),
        )

    def test_multiple_raw_asset_descriptions_collapse_to_same_cleaned_equipment_mapping_key(self) -> None:
        self.assertEqual(
            derive_equipment_mapping_key("567/2021 Chevy 2500 Pick Up"),
            derive_equipment_mapping_key("890/2022 Chevrolet 2500 Pick Up"),
        )


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
                "raw_mappings": {"FORD TRANSIT VAN": "Utility Van"},
                "saved_mappings": [
                    {"raw_description": "FORD TRANSIT VAN", "target_category": "Utility Van"}
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
        self.assertEqual(normalized_record.equipment_description, "627/2025 FORD TRANSIT VAN")
        self.assertEqual(normalized_record.equipment_mapping_key, "FORD TRANSIT VAN")

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
            return_value={"raw_mappings": {"FORD TRANSIT VAN": "Utility Van"}},
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
            return_value={"raw_mappings": {"FORD TRANSIT VAN": "Not In Profile"}},
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
            return_value={"raw_mappings": {"FORD TRANSIT VAN": "Utility Van"}},
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


    def test_phase_29_subphase_remains_distinct_from_market_recovery_in_family_routing(self) -> None:
        subphase_record = Record(
            record_type=MATERIAL,
            phase_code="29 .999",
            raw_description="Paid sick time",
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            phase_name_raw="Labor-Non-Job Related Time",
            source_page=1,
            source_line_text="PR sample",
        )
        market_recovery_record = Record(
            record_type=MATERIAL,
            phase_code="29",
            raw_description="MR252080 / Src JCCo: 1",
            cost=-28950.0,
            hours=0.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            phase_name_raw="Market Recovery",
            source_page=1,
            source_line_text="IC sample",
        )

        phase_cache = normalize_records.__globals__["_get_phase_mapping"]
        phase_cache.cache_clear()
        with patch(
            "job_cost_tool.core.normalization.normalizer.ConfigLoader.get_phase_mapping",
            return_value={"29": "MATERIAL", "29 .999": "LABOR"},
        ), patch(
            "job_cost_tool.core.normalization.normalizer.normalize_labor_record",
            side_effect=lambda record: replace(record, warnings=record.warnings + ["labor path"]),
        ), patch(
            "job_cost_tool.core.normalization.normalizer.normalize_material_record",
            side_effect=lambda record: replace(record, warnings=record.warnings + ["material path"]),
        ):
            normalized_records = normalize_records([subphase_record, market_recovery_record])
        phase_cache.cache_clear()

        self.assertEqual(normalized_records[0].phase_code, "29 .999")
        self.assertEqual(normalized_records[0].record_type_normalized, LABOR)
        self.assertIn("labor path", normalized_records[0].warnings)
        self.assertEqual(normalized_records[1].phase_code, "29")
        self.assertEqual(normalized_records[1].record_type_normalized, MATERIAL)
        self.assertIn("material path", normalized_records[1].warnings)


    def test_phase_40_subcontracted_ap_normalizes_as_subcontractor(self) -> None:
        record = Record(
            record_type=SUBCONTRACTOR,
            phase_code="40",
            raw_description="974 CJ Shaughnessy Crane 24942 / TR# 108 / 1 / APCo: 2 / SL#-Item 842600.001-1",
            cost=6000.0,
            hours=0.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name="CJ Shaughnessy Crane",
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            transaction_type="AP",
            phase_name_raw="Subcontracted",
            vendor_id_raw="974",
            source_page=1,
            source_line_text="AP 03/20/26 974 CJ Shaughnessy Crane 24942 / TR# 108 / 1 / APCo: 2 / SL#-Item 842600.001-1 0.00 6,000.00",
        )

        phase_cache = normalize_records.__globals__["_get_phase_mapping"]
        phase_cache.cache_clear()
        with patch(
            "job_cost_tool.core.normalization.normalizer.ConfigLoader.get_phase_mapping",
            return_value={"40": "SUBCONTRACTOR"},
        ):
            normalized_record = normalize_records([record])[0]
        phase_cache.cache_clear()

        self.assertEqual(normalized_record.phase_code, "40")
        self.assertEqual(normalized_record.phase_name_raw, "Subcontracted")
        self.assertEqual(normalized_record.record_type, SUBCONTRACTOR)
        self.assertEqual(normalized_record.record_type_normalized, SUBCONTRACTOR)
        self.assertEqual(normalized_record.vendor_name, "CJ Shaughnessy Crane")


if __name__ == "__main__":
    unittest.main()
