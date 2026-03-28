"""Focused tests for PR detail tokenization behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_cost_tool.core.models.record import EQUIPMENT, LABOR, OTHER
from job_cost_tool.core.parsing.tokenizer import tokenize_pr_line


class TokenizerTests(unittest.TestCase):
    """Verify permissive equipment extraction without disturbing other PR parsing."""

    def test_structured_equipment_line_still_uses_strict_pattern(self) -> None:
        line = "103/F 1.00 / 205 / Dondero Jr, John 12/2024 Cat Skid Steer / 1"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase", return_value=EQUIPMENT):
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

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase", return_value=EQUIPMENT):
            result = tokenize_pr_line(line, phase_code="20", phase_name_raw="Internal Equip. Charges")

        self.assertEqual(result["employee_name"], "Dondero Jr, John")
        self.assertEqual(result["equipment_description"], "Cat 299D")
        self.assertEqual(result["line_family"], EQUIPMENT)
        self.assertNotIn(
            "PR equipment detail line was recognized but equipment description was not parsed cleanly.",
            result["warnings"],
        )

    def test_labor_payroll_tail_does_not_regress_into_equipment_description(self) -> None:
        line = "103/F 1.00 / 205 / Dondero Jr, John 123 Regular Earnings"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase", return_value=LABOR):
            result = tokenize_pr_line(line, phase_code="10", phase_name_raw="Labor-Electricians")

        self.assertEqual(result["employee_name"], "Dondero Jr, John")
        self.assertIsNone(result["equipment_description"])
        self.assertEqual(result["line_family"], LABOR)

    def test_ambiguous_non_equipment_tail_does_not_get_equipment_fallback(self) -> None:
        line = "103/F 1.00 / 205 / Unclear Detail Tail"

        with patch("job_cost_tool.core.parsing.tokenizer.infer_record_type_from_phase", return_value=OTHER):
            result = tokenize_pr_line(line, phase_code="99", phase_name_raw="Unknown Phase")

        self.assertEqual(result["employee_name"], "Unclear Detail Tail")
        self.assertIsNone(result["equipment_description"])
        self.assertEqual(result["line_family"], OTHER)
        self.assertIn("PR detail line family is ambiguous and should be reviewed.", result["warnings"])


if __name__ == "__main__":
    unittest.main()
