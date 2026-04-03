"""Focused tests for PR detail tokenization behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER, PERMIT, POLICE_DETAIL, PROJECT_MANAGEMENT
from job_cost_tool.core.parsing.tokenizer import tokenize_detail_line, tokenize_pr_line


class TokenizerTests(unittest.TestCase):
    """Verify permissive equipment extraction without disturbing other PR parsing."""

    def test_structured_equipment_line_still_uses_strict_pattern(self) -> None:
        line = "103/F 1.00 / 205 / Dondero Jr, John 12/2024 Cat Skid Steer / 1"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=EQUIPMENT):
            result = tokenize_pr_line(line, phase_code="20", phase_name_raw="Internal Equip. Charges")

        self.assertEqual(result["employee_name"], "Dondero Jr, John")
        self.assertEqual(result["equipment_description"], "12/2024 Cat Skid Steer")
        self.assertEqual(result["line_family"], EQUIPMENT)
        self.assertNotIn(
            "PR equipment detail line was recognized but equipment description was not parsed cleanly.",
            result["warnings"],
        )

    def test_equipment_phase_fallback_preserves_raw_equipment_description_when_strict_pattern_misses(self) -> None:
        line = "103/F 1.00 / 205 / Dondero Jr, John Cat 299D / 1"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=EQUIPMENT):
            result = tokenize_pr_line(line, phase_code="20", phase_name_raw="Internal Equip. Charges")

        self.assertEqual(result["employee_name"], "Dondero Jr, John")
        self.assertEqual(result["equipment_description"], "Cat 299D")
        self.assertEqual(result["line_family"], EQUIPMENT)
        self.assertNotIn(
            "PR equipment detail line was recognized but equipment description was not parsed cleanly.",
            result["warnings"],
        )

    def test_non_year_asset_start_keeps_employee_suffix_out_of_equipment_description(self) -> None:
        line = "104/EO B / 24 / Baez , Juan O 751/Kubota Tracked Skid Steer / 1"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=EQUIPMENT):
            result = tokenize_pr_line(line, phase_code="31", phase_name_raw="Internal Equip. Charges")

        self.assertEqual(result["employee_name"], "Baez , Juan O")
        self.assertEqual(result["equipment_description"], "751/Kubota Tracked Skid Steer")
        self.assertEqual(result["line_family"], EQUIPMENT)
        self.assertNotIn(
            "PR equipment detail line was recognized but equipment description was not parsed cleanly.",
            result["warnings"],
        )

    def test_non_year_asset_start_extracts_tow_behind_compressor(self) -> None:
        line = "104/EO B / 24 / Baez , Juan O 797/SullAir Tow Behind Compressor / 1"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=EQUIPMENT):
            result = tokenize_pr_line(line, phase_code="31", phase_name_raw="Internal Equip. Charges")

        self.assertEqual(result["employee_name"], "Baez , Juan O")
        self.assertEqual(result["equipment_description"], "797/SullAir Tow Behind Compressor")

    def test_non_year_asset_start_extracts_hi_rai_bucket_truck(self) -> None:
        line = "104/EO B / 24 / Baez , Juan O 504/Ford F550 Hi-Rai Bucket Truck / 1"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=EQUIPMENT):
            result = tokenize_pr_line(line, phase_code="31", phase_name_raw="Internal Equip. Charges")

        self.assertEqual(result["employee_name"], "Baez , Juan O")
        self.assertEqual(result["equipment_description"], "504/Ford F550 Hi-Rai Bucket Truck")

    def test_labor_payroll_tail_does_not_regress_into_equipment_description(self) -> None:
        line = "103/F 1.00 / 205 / Dondero Jr, John 123 Regular Earnings"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=LABOR):
            result = tokenize_pr_line(line, phase_code="10", phase_name_raw="Labor-Electricians")

        self.assertEqual(result["employee_name"], "Dondero Jr, John")
        self.assertIsNone(result["equipment_description"])
        self.assertEqual(result["line_family"], LABOR)

    def test_labor_line_without_structured_class_still_keeps_raw_description_for_fallback_mapping(self) -> None:
        line = "PR 03/02/26 1.00 / 186 / Culhane , John P5 Regular Earnings 8.00 ST 701.66"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=LABOR):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="21", phase_name_raw="Labor-Multi-Trade")

        self.assertEqual(result["transaction_type"], "PR")
        self.assertEqual(result["line_family"], LABOR)
        self.assertEqual(result["raw_description"], "1.00 / 186 / Culhane , John P5 Regular Earnings")
        self.assertEqual(result["employee_id"], "186")
        self.assertEqual(result["employee_name"], "Culhane , John P")
        self.assertIsNone(result["labor_class_raw"])
        self.assertEqual(result["hours"], 8.0)
        self.assertEqual(result["hour_type"], "ST")
        self.assertEqual(result["cost"], 701.66)
        self.assertIn(
            "PR labor detail line was recognized but labor class was not parsed cleanly.",
            result["warnings"],
        )

    def test_pr_line_under_material_phase_falls_back_to_phase_family_without_ambiguity(self) -> None:
        line = "PR 03/07/26 1.00 / 557 / Summiel , Devin A18 P/Diem Reimb 0.00 ST 200.00"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=MATERIAL):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="50", phase_name_raw="Other Job Cost")

        self.assertEqual(result["transaction_type"], "PR")
        self.assertEqual(result["line_family"], MATERIAL)
        self.assertEqual(result["raw_description"], "1.00 / 557 / Summiel , Devin A18 P/Diem Reimb")
        self.assertEqual(result["employee_id"], "557")
        self.assertEqual(result["employee_name"], "Summiel , Devin A18 P/Diem Reimb")
        self.assertEqual(result["hours"], 0.0)
        self.assertEqual(result["hour_type"], "ST")
        self.assertEqual(result["cost"], 200.0)
        self.assertNotIn("PR detail line family is ambiguous and should be reviewed.", result["warnings"])

    def test_ambiguous_non_equipment_tail_does_not_get_equipment_fallback(self) -> None:
        line = "103/F 1.00 / 205 / Unclear Detail Tail"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=OTHER):
            result = tokenize_pr_line(line, phase_code="99", phase_name_raw="Unknown Phase")

        self.assertEqual(result["employee_name"], "Unclear Detail Tail")
        self.assertIsNone(result["equipment_description"])
        self.assertEqual(result["line_family"], OTHER)
        self.assertIn("PR detail line family is ambiguous and should be reviewed.", result["warnings"])


    def test_generic_ic_line_uses_phase_family_and_signed_numeric_columns(self) -> None:
        line = "IC 12/22/25 MR252080 / Src JCCo: 1 0.00 -28,950.00"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=MATERIAL):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="29", phase_name_raw="Market Recovery")

        self.assertEqual(result["transaction_type"], "IC")
        self.assertEqual(result["line_family"], MATERIAL)
        self.assertEqual(result["raw_description"], "MR252080 / Src JCCo: 1")
        self.assertEqual(result["hours"], 0.0)
        self.assertEqual(result["cost"], -28950.0)
        self.assertNotIn("Detail line appears to contain amount tokens but they were not parsed cleanly.", result["warnings"])

    def test_negative_amount_ap_line_parses_cleanly(self) -> None:
        line = "AP 03/12/26 772 Berts Electric Suppl 576862 / TR# 24 / 0 / APCo: 2 Material 0.00 -525.00"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=MATERIAL):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="11", phase_name_raw="Material-Electrical")

        self.assertEqual(result["transaction_type"], "AP")
        self.assertEqual(result["line_family"], MATERIAL)
        self.assertEqual(result["vendor_id_raw"], "772")
        self.assertEqual(result["vendor_name"], "Berts Electric Suppl")
        self.assertEqual(result["raw_description"], "772 Berts Electric Suppl 576862 / TR# 24 / 0 / APCo: 2 Material")
        self.assertEqual(result["hours"], 0.0)
        self.assertEqual(result["cost"], -525.0)
        self.assertNotIn("Detail line appears to contain amount tokens but they were not parsed cleanly.", result["warnings"])

    def test_ap_line_under_permits_phase_keeps_vendor_fields_and_permit_family(self) -> None:
        line = "AP 03/02/26 408 Bank of America BOA 3-2-26 / TR# 8 / 0 / APCo: 2 BOA 1446 3-2-26 0.00 1,293.39"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=PERMIT):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="50 .1", phase_name_raw="Permits & Fees")

        self.assertEqual(result["transaction_type"], "AP")
        self.assertEqual(result["line_family"], PERMIT)
        self.assertEqual(result["vendor_id_raw"], "408")
        self.assertEqual(result["vendor_name"], "Bank of America BOA")
        self.assertEqual(result["raw_description"], "408 Bank of America BOA 3-2-26 / TR# 8 / 0 / APCo: 2 BOA 1446 3-2-26")
        self.assertEqual(result["hours"], 0.0)
        self.assertEqual(result["cost"], 1293.39)

    def test_ap_line_under_police_detail_phase_keeps_vendor_fields_and_police_family(self) -> None:
        line = "AP 03/02/26 22714 Project Flagging LLC 63164 / TR# 163 / 0 / APCo: 1 Flagging - 220108 0.00 922.50"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=POLICE_DETAIL):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="50 .2", phase_name_raw="Police Details")

        self.assertEqual(result["transaction_type"], "AP")
        self.assertEqual(result["line_family"], POLICE_DETAIL)
        self.assertEqual(result["vendor_id_raw"], "22714")
        self.assertEqual(result["vendor_name"], "Project Flagging LLC")
        self.assertEqual(result["raw_description"], "22714 Project Flagging LLC 63164 / TR# 163 / 0 / APCo: 1 Flagging - 220108")
        self.assertEqual(result["hours"], 0.0)
        self.assertEqual(result["cost"], 922.5)

    def test_generic_jc_line_under_project_management_phase_keeps_project_management_family(self) -> None:
        line = "JC 03/05/26 Bugeted PM Allocation 0.00 20,000.00"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=PROJECT_MANAGEMENT):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="25", phase_name_raw="Labor-Project Mgmt")

        self.assertEqual(result["transaction_type"], "JC")
        self.assertEqual(result["line_family"], PROJECT_MANAGEMENT)
        self.assertEqual(result["raw_description"], "Bugeted PM Allocation")
        self.assertEqual(result["hours"], 0.0)
        self.assertEqual(result["cost"], 20000.0)
        self.assertEqual(result["warnings"], [])


    def test_generic_jc_line_uses_phase_family_and_signed_numeric_columns(self) -> None:
        line = "JC 01/07/26 Jay Dondero to 810500 warranty -4.00 -658.45"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase_context", return_value=LABOR):
            result = tokenize_detail_line(line, transaction_type=None, phase_code="20", phase_name_raw="Labor-Electricians")

        self.assertEqual(result["transaction_type"], "JC")
        self.assertEqual(result["line_family"], LABOR)
        self.assertEqual(result["raw_description"], "Jay Dondero to 810500 warranty")
        self.assertEqual(result["hours"], -4.0)
        self.assertEqual(result["cost"], -658.45)
        self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main()
