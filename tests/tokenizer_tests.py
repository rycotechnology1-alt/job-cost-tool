"""Focused tests for PR detail tokenization behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER
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
