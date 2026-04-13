"""Focused regression tests for pure profile-bundle editing helpers."""

from __future__ import annotations

import unittest

from services.profile_bundle_helpers import (
    build_classification_bundle_edit_result,
    build_default_omit_rules_config,
    build_equipment_mapping_config,
    build_labor_mapping_config,
    build_rates_config,
    merge_observed_equipment_raw_values,
    merge_observed_labor_raw_values,
)


class ProfileBundleHelpersTests(unittest.TestCase):
    def test_build_default_omit_rules_config_rejects_duplicate_canonical_phase_codes(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate default omit phase code"):
            build_default_omit_rules_config(
                {"notes": "keep"},
                [
                    {"phase_code": " 29 .999. "},
                    {"phase_code": "29 .999"},
                ],
            )

    def test_build_labor_mapping_config_preserves_raw_first_shape(self) -> None:
        result = build_labor_mapping_config(
            {"mapping_notes": {"deprecated": True}, "extra": "keep"},
            [
                {"raw_value": "103/f", "target_classification": "103 Journeyman", "notes": "mapped"},
                {"raw_value": "104/eo", "target_classification": "", "notes": "review later"},
            ],
            valid_targets=["103 Journeyman"],
        )

        self.assertEqual(
            result,
            {
                "extra": "keep",
                "raw_mappings": {"103/F": "103 Journeyman"},
                "saved_mappings": [
                    {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "mapped"},
                    {"raw_value": "104/EO", "target_classification": "", "notes": "review later"},
                ],
            },
        )

    def test_build_equipment_mapping_config_preserves_blank_saved_rows(self) -> None:
        result = build_equipment_mapping_config(
            {"extra": "keep"},
            [
                {"raw_description": "627/2025 ford transit van", "target_category": "Pick-up Truck"},
                {"raw_description": "crane truck", "target_category": ""},
            ],
            valid_targets=["Pick-up Truck"],
        )

        self.assertEqual(
            result,
            {
                "extra": "keep",
                "raw_mappings": {"FORD TRANSIT VAN": "Pick-up Truck"},
                "saved_mappings": [
                    {"raw_description": "FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                    {"raw_description": "CRANE TRUCK", "target_category": ""},
                ],
            },
        )

    def test_build_classification_bundle_edit_result_propagates_slot_renames(self) -> None:
        result = build_classification_bundle_edit_result(
            existing_labor_slots=[
                {"slot_id": "labor_1", "label": "Old Labor", "active": True},
                {"slot_id": "labor_2", "label": "", "active": False},
            ],
            updated_labor_slots=[
                {"slot_id": "labor_1", "label": "New Labor", "active": True},
                {"slot_id": "labor_2", "label": "", "active": False},
            ],
            existing_equipment_slots=[
                {"slot_id": "equipment_1", "label": "Old Equipment", "active": True},
            ],
            updated_equipment_slots=[
                {"slot_id": "equipment_1", "label": "New Equipment", "active": True},
            ],
            labor_mapping_rows=[{"raw_value": "103/F", "target_classification": "Old Labor", "notes": ""}],
            equipment_mapping_rows=[{"raw_description": "CRANE TRUCK", "target_category": "Old Equipment"}],
            labor_rate_rows=[{"classification": "Old Labor", "standard_rate": "100", "overtime_rate": "", "double_time_rate": ""}],
            equipment_rate_rows=[{"category": "Old Equipment", "rate": "50"}],
            labor_mapping_config={
                "raw_mappings": {"103/F": "Old Labor"},
                "saved_mappings": [{"raw_value": "103/F", "target_classification": "Old Labor", "notes": ""}],
            },
            equipment_mapping_config={
                "raw_mappings": {"CRANE TRUCK": "Old Equipment"},
                "saved_mappings": [{"raw_description": "CRANE TRUCK", "target_category": "Old Equipment"}],
            },
            rates_config={
                "labor_rates": {"Old Labor": {"standard_rate": 100.0}},
                "equipment_rates": {"Old Equipment": {"rate": 50.0}},
            },
            recap_template_map={
                "labor_rows": {"Old Labor": {"row": 10}},
                "equipment_rows": {"Old Equipment": {"row": 20}},
            },
            template_metadata={
                "labor_active_slot_capacity": 1,
                "equipment_active_slot_capacity": 1,
            },
        )

        self.assertEqual(result.labor_rename_map, {"Old Labor": "New Labor"})
        self.assertEqual(result.equipment_rename_map, {"Old Equipment": "New Equipment"})
        self.assertEqual(result.labor_mapping_config["raw_mappings"], {"103/F": "New Labor"})
        self.assertEqual(result.equipment_mapping_config["raw_mappings"], {"CRANE TRUCK": "New Equipment"})
        self.assertEqual(result.rates_config["labor_rates"], {"New Labor": {"standard_rate": 100.0}})
        self.assertEqual(result.rates_config["equipment_rates"], {"New Equipment": {"rate": 50.0}})
        self.assertEqual(result.recap_template_map["labor_rows"], {"Old Labor": {"row": 10}})
        self.assertEqual(result.recap_template_map["equipment_rows"], {"Old Equipment": {"row": 20}})

    def test_build_classification_bundle_edit_result_rejects_active_rows_over_template_capacity(self) -> None:
        with self.assertRaisesRegex(ValueError, "Labor active classifications exceed template capacity"):
            build_classification_bundle_edit_result(
                existing_labor_slots=[{"slot_id": "labor_1", "label": "Slot A", "active": True}],
                updated_labor_slots=[
                    {"slot_id": "labor_1", "label": "Slot A", "active": True},
                    {"slot_id": "labor_2", "label": "Overflow", "active": True},
                ],
                existing_equipment_slots=[],
                updated_equipment_slots=[],
                labor_mapping_rows=[],
                equipment_mapping_rows=[],
                labor_rate_rows=[],
                equipment_rate_rows=[],
                labor_mapping_config={"raw_mappings": {}, "saved_mappings": []},
                equipment_mapping_config={"raw_mappings": {}, "saved_mappings": []},
                rates_config={"labor_rates": {}, "equipment_rates": {}},
                recap_template_map={"labor_rows": {"Slot 1": {"row": 10}}, "equipment_rows": {}},
                template_metadata={"labor_active_slot_capacity": 1, "equipment_active_slot_capacity": 0},
            )

    def test_build_rates_config_rejects_unknown_classification(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown labor rate classification"):
            build_rates_config(
                {"labor_rates": {}, "equipment_rates": {}},
                [{"classification": "Missing", "standard_rate": "10", "overtime_rate": "", "double_time_rate": ""}],
                [],
                valid_labor_targets=["Journeyman"],
                valid_equipment_targets=[],
            )

    def test_merge_observed_labor_raw_values_adds_only_missing_placeholders(self) -> None:
        updated_mapping, did_update = merge_observed_labor_raw_values(
            {
                "raw_mappings": {"103/F": "103 Journeyman"},
                "saved_mappings": [{"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep"}],
            },
            ["103/f", "104/eo"],
        )

        self.assertTrue(did_update)
        self.assertEqual(
            updated_mapping["saved_mappings"],
            [
                {"raw_value": "103/F", "target_classification": "103 Journeyman", "notes": "keep"},
                {"raw_value": "104/EO", "target_classification": "", "notes": "", "is_observed": True},
            ],
        )

    def test_merge_observed_equipment_raw_values_rebuilds_raw_mappings(self) -> None:
        updated_mapping, did_update = merge_observed_equipment_raw_values(
            {
                "raw_mappings": {"FORD TRANSIT VAN": "Pick-up Truck"},
                "saved_mappings": [{"raw_description": "FORD TRANSIT VAN", "target_category": "Pick-up Truck"}],
            },
            ["627/2025 ford transit van", "crane truck"],
        )

        self.assertTrue(did_update)
        self.assertEqual(updated_mapping["raw_mappings"], {"FORD TRANSIT VAN": "Pick-up Truck"})
        self.assertEqual(
            updated_mapping["saved_mappings"],
            [
                {"raw_description": "FORD TRANSIT VAN", "target_category": "Pick-up Truck"},
                {"raw_description": "CRANE TRUCK", "target_category": "", "is_observed": True},
            ],
        )


if __name__ == "__main__":
    unittest.main()
