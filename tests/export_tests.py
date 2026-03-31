"""Lightweight tests for recap export behavior."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

import job_cost_tool.core.export.recap_mapper as recap_mapper
from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, Record
from job_cost_tool.services.export_service import export_records_to_recap
from job_cost_tool.services.validation_service import validate_records


TEST_TEMPLATE_MAP = {
    "worksheet_name": "Recap",
    "header_fields": {
        "project": {"cell": "B6"},
        "description": {"cell": "B7"},
        "prepared_by": {"cell": "B8"},
        "job_number": {"cell": "G6"},
        "date": {"cell": "G7"},
        "report_or_co_number": {"cell": "G8"},
    },
    "labor_rows": {
        "103 Journeyman": {
            "st_hours": "B14",
            "ot_hours": "C14",
            "dt_hours": "D14",
            "st_rate": "E14",
            "ot_rate": "F14",
            "dt_rate": "G14",
        },
        "104 Apprentice": {
            "st_hours": "B22",
            "ot_hours": "C22",
            "dt_hours": "D22",
            "st_rate": "E22",
            "ot_rate": "F22",
            "dt_rate": "G22",
        },
    },
    "equipment_rows": {
        "Pick-up Truck": {"hours_qty": "B32", "rate": "D32"},
        "Utility Van": {"hours_qty": "B33", "rate": "D33"},
    },
    "materials_section": {
        "start_row": 46,
        "end_row": 52,
        "columns": {"name": "A", "amount": "B"},
    },
    "subcontractors_section": {
        "start_row": 46,
        "end_row": 50,
        "columns": {"name": "E", "description": "F", "amount": "G"},
    },
    "permits_fees_section": {
        "start_row": 57,
        "end_row": 58,
        "columns": {"description": "A", "amount": "C"},
    },
    "police_detail_section": {
        "start_row": 63,
        "end_row": 64,
        "columns": {"description": "A", "amount": "C"},
    },
}

TEST_LABOR_SLOT_CONFIG = {
    "slots": [
        {"slot_id": "labor_1", "label": "103 Journeyman", "active": True},
        {"slot_id": "labor_2", "label": "104 Apprentice", "active": True},
    ],
    "classifications": ["103 Journeyman", "104 Apprentice"],
}
TEST_EQUIPMENT_SLOT_CONFIG = {
    "slots": [
        {"slot_id": "equipment_1", "label": "Pick-up Truck", "active": True},
        {"slot_id": "equipment_2", "label": "Utility Van", "active": True},
    ],
    "classifications": ["Pick-up Truck", "Utility Van"],
}
TEST_LABOR_ROW_SLOTS = {
    "labor_1": {
        "slot_id": "labor_1",
        "label": "103 Journeyman",
        "active": True,
        "template_label": "103 Journeyman",
        "mapping": TEST_TEMPLATE_MAP["labor_rows"]["103 Journeyman"],
    },
    "labor_2": {
        "slot_id": "labor_2",
        "label": "104 Apprentice",
        "active": True,
        "template_label": "104 Apprentice",
        "mapping": TEST_TEMPLATE_MAP["labor_rows"]["104 Apprentice"],
    },
}
TEST_EQUIPMENT_ROW_SLOTS = {
    "equipment_1": {
        "slot_id": "equipment_1",
        "label": "Pick-up Truck",
        "active": True,
        "template_label": "Pick-up Truck",
        "mapping": TEST_TEMPLATE_MAP["equipment_rows"]["Pick-up Truck"],
    },
    "equipment_2": {
        "slot_id": "equipment_2",
        "label": "Utility Van",
        "active": True,
        "template_label": "Utility Van",
        "mapping": TEST_TEMPLATE_MAP["equipment_rows"]["Utility Van"],
    },
}
TARGET_RATES = {
    "labor_rates": {
        "103 Journeyman": {"standard_rate": 199.5, "overtime_rate": 299.25, "double_time_rate": 399.0},
        "104 Apprentice": {"standard_rate": 150.0, "overtime_rate": 225.0, "double_time_rate": 300.0},
    },
    "equipment_rates": {
        "Pick-up Truck": {"rate": 88.0},
        "Utility Van": {"rate": 44.5},
    },
}
TEST_TMP_ROOT = Path("job_cost_tool/tests/_tmp")


class ExportWorkflowTests(unittest.TestCase):
    """Verify recap export safety and repeatability."""

    def setUp(self) -> None:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp_path = TEST_TMP_ROOT / self._testMethodName
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        self.template_path = self.temp_path / "template.xlsx"
        self.output_path = self.temp_path / "output.xlsx"
        self._create_template(self.template_path)

        recap_mapper._get_target_labor_classifications.cache_clear()
        recap_mapper._get_target_equipment_classifications.cache_clear()
        recap_mapper._get_active_labor_slots.cache_clear()
        recap_mapper._get_active_equipment_slots.cache_clear()
        recap_mapper._get_active_labor_slot_lookup.cache_clear()
        recap_mapper._get_active_equipment_slot_lookup.cache_clear()
        recap_mapper._get_rates.cache_clear()
        recap_mapper._get_material_section_capacity.cache_clear()

        self.recap_map_patch = patch(
            "job_cost_tool.core.export.excel_exporter.ConfigLoader.get_recap_template_map",
            return_value=TEST_TEMPLATE_MAP,
        )
        self.recap_map_mapper_patch = patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_recap_template_map",
            return_value=TEST_TEMPLATE_MAP,
        )
        self.labor_row_slots_patch = patch(
            "job_cost_tool.core.export.excel_exporter.ConfigLoader.get_labor_row_slots",
            return_value=TEST_LABOR_ROW_SLOTS,
        )
        self.equipment_row_slots_patch = patch(
            "job_cost_tool.core.export.excel_exporter.ConfigLoader.get_equipment_row_slots",
            return_value=TEST_EQUIPMENT_ROW_SLOTS,
        )
        self.labor_patch = patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_target_labor_classifications",
            return_value=TEST_LABOR_SLOT_CONFIG,
        )
        self.equipment_patch = patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_target_equipment_classifications",
            return_value=TEST_EQUIPMENT_SLOT_CONFIG,
        )
        self.rates_patch = patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_rates",
            return_value=TARGET_RATES,
        )
        self.recap_map_patch.start()
        self.recap_map_mapper_patch.start()
        self.labor_row_slots_patch.start()
        self.equipment_row_slots_patch.start()
        self.labor_patch.start()
        self.equipment_patch.start()
        self.rates_patch.start()

        self.addCleanup(self.recap_map_patch.stop)
        self.addCleanup(self.recap_map_mapper_patch.stop)
        self.addCleanup(self.labor_row_slots_patch.stop)
        self.addCleanup(self.equipment_row_slots_patch.stop)
        self.addCleanup(self.labor_patch.stop)
        self.addCleanup(self.equipment_patch.stop)
        self.addCleanup(self.rates_patch.stop)
        self.addCleanup(recap_mapper._get_target_labor_classifications.cache_clear)
        self.addCleanup(recap_mapper._get_target_equipment_classifications.cache_clear)
        self.addCleanup(recap_mapper._get_active_labor_slots.cache_clear)
        self.addCleanup(recap_mapper._get_active_equipment_slots.cache_clear)
        self.addCleanup(recap_mapper._get_active_labor_slot_lookup.cache_clear)
        self.addCleanup(recap_mapper._get_active_equipment_slot_lookup.cache_clear)
        self.addCleanup(recap_mapper._get_rates.cache_clear)
        self.addCleanup(recap_mapper._get_material_section_capacity.cache_clear)
        self.addCleanup(self._cleanup_temp_dir)

    def test_export_fails_when_blockers_exist(self) -> None:
        records = [self._labor_record(recap_classification=None)]

        with self.assertRaisesRegex(ValueError, "Export blocked until all blocking issues are resolved"):
            export_records_to_recap(records, str(self.template_path), str(self.output_path))

    def test_export_succeeds_after_correction(self) -> None:
        records = [
            self._labor_record(recap_classification="103 Journeyman", recap_slot_id="labor_1", hours=8),
            self._equipment_record(category="Pick-up Truck", recap_slot_id="equipment_1", hours=2),
            self._material_record(vendor="Vendor A", cost=100),
        ]

        export_records_to_recap(records, str(self.template_path), str(self.output_path))

        worksheet = load_workbook(self.output_path)["Recap"]
        self.assertEqual(worksheet["B6"].value, "Sample Project")
        self.assertEqual(worksheet["G6"].value, "JOB-100")
        self.assertEqual(worksheet["A14"].value, "103 Journeyman")
        self.assertEqual(worksheet["B14"].value, 8)
        self.assertEqual(worksheet["E14"].value, 199.5)
        self.assertEqual(worksheet["F14"].value, 299.25)
        self.assertEqual(worksheet["G14"].value, 399)
        self.assertEqual(worksheet["A32"].value, "Pick-up Truck")
        self.assertEqual(worksheet["B32"].value, 2)
        self.assertEqual(worksheet["D32"].value, 88)
        self.assertEqual(worksheet["A46"].value, "Vendor A")
        self.assertEqual(worksheet["B46"].value, 100)
        self.assertEqual(worksheet["B53"].value, "=SUM(B46:B52)")

    def test_export_uses_slot_rows_after_profile_label_rename(self) -> None:
        renamed_labor_slot_config = {
            "slots": [
                {"slot_id": "labor_1", "label": "Big Boy", "active": True},
                {"slot_id": "labor_2", "label": "104 Apprentice", "active": True},
            ],
            "classifications": ["Big Boy", "104 Apprentice"],
        }
        renamed_labor_row_slots = {
            **TEST_LABOR_ROW_SLOTS,
            "labor_1": {
                "slot_id": "labor_1",
                "label": "Big Boy",
                "active": True,
                "template_label": "103 Journeyman",
                "mapping": TEST_TEMPLATE_MAP["labor_rows"]["103 Journeyman"],
            },
        }
        renamed_rates = {
            **TARGET_RATES,
            "labor_rates": {
                "Big Boy": {"standard_rate": 210.0, "overtime_rate": 315.0, "double_time_rate": 420.0},
                "104 Apprentice": TARGET_RATES["labor_rates"]["104 Apprentice"],
            },
        }

        with patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_target_labor_classifications",
            return_value=renamed_labor_slot_config,
        ), patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_rates",
            return_value=renamed_rates,
        ), patch(
            "job_cost_tool.core.export.excel_exporter.ConfigLoader.get_labor_row_slots",
            return_value=renamed_labor_row_slots,
        ):
            recap_mapper._get_target_labor_classifications.cache_clear()
            recap_mapper._get_active_labor_slots.cache_clear()
            recap_mapper._get_active_labor_slot_lookup.cache_clear()
            recap_mapper._get_rates.cache_clear()

            records = [self._labor_record(recap_classification="Big Boy", recap_slot_id="labor_1", hours=8)]
            export_records_to_recap(records, str(self.template_path), str(self.output_path))

        worksheet = load_workbook(self.output_path)["Recap"]
        self.assertEqual(worksheet["A14"].value, "Big Boy")
        self.assertEqual(worksheet["B14"].value, 8)
        self.assertEqual(worksheet["E14"].value, 210)
        self.assertEqual(worksheet["F14"].value, 315)
        self.assertEqual(worksheet["G14"].value, 420)

    def test_export_uses_active_equipment_slot_labels_after_profile_label_rename(self) -> None:
        renamed_equipment_slot_config = {
            "slots": [
                {"slot_id": "equipment_1", "label": "Big Rig", "active": True},
                {"slot_id": "equipment_2", "label": "Utility Van", "active": True},
            ],
            "classifications": ["Big Rig", "Utility Van"],
        }
        renamed_equipment_row_slots = {
            **TEST_EQUIPMENT_ROW_SLOTS,
            "equipment_1": {
                "slot_id": "equipment_1",
                "label": "Big Rig",
                "active": True,
                "template_label": "Pick-up Truck",
                "mapping": TEST_TEMPLATE_MAP["equipment_rows"]["Pick-up Truck"],
            },
        }
        renamed_rates = {
            **TARGET_RATES,
            "equipment_rates": {
                "Big Rig": {"rate": 99.0},
                "Utility Van": TARGET_RATES["equipment_rates"]["Utility Van"],
            },
        }

        with patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_target_equipment_classifications",
            return_value=renamed_equipment_slot_config,
        ), patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_rates",
            return_value=renamed_rates,
        ), patch(
            "job_cost_tool.core.export.excel_exporter.ConfigLoader.get_equipment_row_slots",
            return_value=renamed_equipment_row_slots,
        ):
            recap_mapper._get_target_equipment_classifications.cache_clear()
            recap_mapper._get_active_equipment_slots.cache_clear()
            recap_mapper._get_active_equipment_slot_lookup.cache_clear()
            recap_mapper._get_rates.cache_clear()

            records = [self._equipment_record(category="Big Rig", recap_slot_id="equipment_1", hours=2)]
            export_records_to_recap(records, str(self.template_path), str(self.output_path))

        worksheet = load_workbook(self.output_path)["Recap"]
        self.assertEqual(worksheet["A32"].value, "Big Rig")
        self.assertEqual(worksheet["B32"].value, 2)
        self.assertEqual(worksheet["D32"].value, 99)

    def test_export_collapses_material_vendor_overflow_into_additional_vendors(self) -> None:
        records = [
            self._material_record(vendor=f"Vendor {index}", cost=10 + index)
            for index in range(8)
        ]

        export_records_to_recap(records, str(self.template_path), str(self.output_path))

        worksheet = load_workbook(self.output_path)["Recap"]
        self.assertEqual(worksheet["A46"].value, "Vendor 0")
        self.assertEqual(worksheet["B46"].value, 10)
        self.assertEqual(worksheet["A47"].value, "Vendor 1")
        self.assertEqual(worksheet["B47"].value, 11)
        self.assertEqual(worksheet["A48"].value, "Vendor 2")
        self.assertEqual(worksheet["B48"].value, 12)
        self.assertEqual(worksheet["A49"].value, "Vendor 3")
        self.assertEqual(worksheet["B49"].value, 13)
        self.assertEqual(worksheet["A50"].value, "Vendor 4")
        self.assertEqual(worksheet["B50"].value, 14)
        self.assertEqual(worksheet["A51"].value, "Vendor 5")
        self.assertEqual(worksheet["B51"].value, 15)
        self.assertEqual(worksheet["A52"].value, "Additional Vendors")
        self.assertEqual(worksheet["B52"].value, 33)
        self.assertEqual(worksheet["B53"].value, "=SUM(B46:B52)")

    def test_material_overflow_uses_current_template_capacity(self) -> None:
        smaller_template_map = {
            **TEST_TEMPLATE_MAP,
            "materials_section": {
                **TEST_TEMPLATE_MAP["materials_section"],
                "end_row": 48,
            },
        }
        records = [
            self._material_record(vendor=f"Vendor {index}", cost=10 + index)
            for index in range(4)
        ]

        with patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_recap_template_map",
            return_value=smaller_template_map,
        ):
            recap_mapper._get_material_section_capacity.cache_clear()
            payload = recap_mapper.build_recap_payload(records)

        self.assertEqual(
            payload["materials"],
            [
                {"name": "Vendor 0", "amount": 10},
                {"name": "Vendor 1", "amount": 11},
                {"name": "Additional Vendors", "amount": 25},
            ],
        )

    def test_material_overflow_preserves_vendors_by_first_appearance_order(self) -> None:
        smaller_template_map = {
            **TEST_TEMPLATE_MAP,
            "materials_section": {
                **TEST_TEMPLATE_MAP["materials_section"],
                "end_row": 48,
            },
        }
        records = [
            self._material_record(vendor="Vendor C", cost=30),
            self._material_record(vendor="Vendor A", cost=10),
            self._material_record(vendor="Vendor C", cost=5),
            self._material_record(vendor="Vendor B", cost=20),
            self._material_record(vendor="Vendor D", cost=40),
        ]

        with patch(
            "job_cost_tool.core.export.recap_mapper.ConfigLoader.get_recap_template_map",
            return_value=smaller_template_map,
        ):
            recap_mapper._get_material_section_capacity.cache_clear()
            payload = recap_mapper.build_recap_payload(records)

        self.assertEqual(
            payload["materials"],
            [
                {"name": "Vendor C", "amount": 35},
                {"name": "Vendor A", "amount": 10},
                {"name": "Additional Vendors", "amount": 60},
            ],
        )

    def test_export_fails_if_rate_target_cell_mapping_is_missing(self) -> None:
        broken_labor_row_slots = {
            **TEST_LABOR_ROW_SLOTS,
            "labor_1": {
                **TEST_LABOR_ROW_SLOTS["labor_1"],
                "mapping": {
                    key: value
                    for key, value in TEST_LABOR_ROW_SLOTS["labor_1"]["mapping"].items()
                    if key != "st_rate"
                },
            },
        }

        with patch(
            "job_cost_tool.core.export.excel_exporter.ConfigLoader.get_labor_row_slots",
            return_value=broken_labor_row_slots,
        ):
            records = [self._labor_record(recap_classification="103 Journeyman", recap_slot_id="labor_1", hours=8)]
            with self.assertRaisesRegex(ValueError, "missing 'st_rate'"):
                export_records_to_recap(records, str(self.template_path), str(self.output_path))

    def test_validation_blocks_missing_labor_hour_type_before_export(self) -> None:
        records = [
            self._labor_record(
                recap_classification="103 Journeyman",
                recap_slot_id="labor_1",
                hours=-4,
                hour_type=None,
            )
        ]

        validated_records, blocking_issues = validate_records(records)

        self.assertIn(
            "Record on page 1 (phase 20, labor): Labor hour type is missing for export.",
            blocking_issues,
        )
        self.assertIn(
            "BLOCKING: Labor hour type is missing for export.",
            validated_records[0].warnings,
        )

    def test_export_blocks_missing_labor_hour_type_before_recap_build(self) -> None:
        records = [
            self._labor_record(
                recap_classification="103 Journeyman",
                recap_slot_id="labor_1",
                hours=-4,
                hour_type=None,
            )
        ]

        with patch("job_cost_tool.services.export_service.build_recap_payload") as build_payload_mock:
            with self.assertRaisesRegex(ValueError, "Labor hour type is missing for export"):
                export_records_to_recap(records, str(self.template_path), str(self.output_path))

        build_payload_mock.assert_not_called()


    def test_export_fails_if_template_missing(self) -> None:
        records = [self._labor_record(recap_classification="103 Journeyman", recap_slot_id="labor_1")]
        missing_template = self.temp_path / "missing-template.xlsx"

        with self.assertRaisesRegex(FileNotFoundError, "Recap template workbook was not found"):
            export_records_to_recap(records, str(missing_template), str(self.output_path))

    def test_export_clears_previous_data_when_reused(self) -> None:
        first_records = [
            self._material_record(vendor="Vendor A", cost=100),
            self._material_record(vendor="Vendor B", cost=200),
        ]
        second_records = [
            self._material_record(vendor="Vendor C", cost=300),
        ]

        export_records_to_recap(first_records, str(self.template_path), str(self.output_path))
        export_records_to_recap(second_records, str(self.template_path), str(self.output_path))

        worksheet = load_workbook(self.output_path)["Recap"]
        self.assertEqual(worksheet["A46"].value, "Vendor C")
        self.assertEqual(worksheet["B46"].value, 300)
        self.assertIsNone(worksheet["A47"].value)
        self.assertIsNone(worksheet["B47"].value)
        self.assertEqual(worksheet["B53"].value, "=SUM(B46:B52)")

    def test_omitted_record_does_not_block_or_export(self) -> None:
        records = [
            self._labor_record(recap_classification=None, is_omitted=True),
            self._material_record(vendor="Vendor A", cost=100),
        ]

        validated_records, blocking_issues = validate_records(records)
        self.assertEqual(blocking_issues, [])

        export_records_to_recap(validated_records, str(self.template_path), str(self.output_path))

        worksheet = load_workbook(self.output_path)["Recap"]
        self.assertIsNone(worksheet["B14"].value)
        self.assertEqual(worksheet["A46"].value, "Vendor A")
        self.assertEqual(worksheet["B46"].value, 100)

    def _cleanup_temp_dir(self) -> None:
        shutil.rmtree(self.temp_path, ignore_errors=True)

    def _create_template(self, path: Path) -> None:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Recap"

        for cell in ["B6", "B7", "B8", "G6", "G7", "G8", "B14", "C14", "D14", "E14", "F14", "G14", "B22", "C22", "D22", "E22", "F22", "G22", "B32", "D32", "B33", "D33", "A46", "B46", "A47", "B47", "A48", "B48", "A49", "B49", "A50", "B50", "A51", "B51", "A52", "B52", "E46", "F46", "G46", "E47", "F47", "G47", "E48", "F48", "G48", "E49", "F49", "G49", "E50", "F50", "G50", "A57", "C57", "A58", "C58", "A63", "C63", "A64", "C64"]:
            worksheet[cell] = None

        worksheet["H23"] = "=SUM(H12:H22)"
        worksheet["E42"] = "=SUM(E27:E41)"
        worksheet["B53"] = "=SUM(B46:B52)"
        worksheet["G51"] = "=SUM(G46:G50)"
        worksheet["C59"] = "=SUM(C57:C58)"
        worksheet["C65"] = "=SUM(C63:C64)"
        workbook.save(path)

    def _labor_record(
        self,
        recap_classification: str | None,
        hours: float = 8,
        is_omitted: bool = False,
        recap_slot_id: str | None = None,
        hour_type: str | None = "ST",
    ) -> Record:
        return Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="Labor line",
            cost=100,
            hours=hours,
            hour_type=hour_type,
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized="J",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            job_number="JOB-100",
            job_name="Sample Project",
            source_page=1,
            source_line_text="Labor source",
            record_type_normalized=LABOR,
            recap_labor_slot_id=recap_slot_id,
            recap_labor_classification=recap_classification,
            vendor_name_normalized=None,
            is_omitted=is_omitted,
        )

    def _equipment_record(self, category: str, hours: float = 2, recap_slot_id: str | None = None) -> Record:
        return Record(
            record_type=EQUIPMENT,
            phase_code="31",
            raw_description="Equipment line",
            cost=50,
            hours=hours,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description="Pickup truck",
            equipment_category=category,
            confidence=0.9,
            warnings=[],
            job_number="JOB-100",
            job_name="Sample Project",
            source_page=1,
            source_line_text="Equipment source",
            record_type_normalized=EQUIPMENT,
            recap_labor_classification=None,
            recap_equipment_slot_id=recap_slot_id,
            vendor_name_normalized=None,
        )

    def _material_record(self, vendor: str, cost: float) -> Record:
        return Record(
            record_type=MATERIAL,
            phase_code="50",
            raw_description="Material line",
            cost=cost,
            hours=None,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=vendor,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            job_number="JOB-100",
            job_name="Sample Project",
            source_page=1,
            source_line_text="Material source",
            record_type_normalized=MATERIAL,
            recap_labor_classification=None,
            vendor_name_normalized=vendor,
        )


if __name__ == "__main__":
    unittest.main()
