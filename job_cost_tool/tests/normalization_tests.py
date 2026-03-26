"""Focused normalization tests for narrow business-rule exceptions."""

from __future__ import annotations

import unittest

from job_cost_tool.core.models.record import LABOR, MATERIAL, Record
from job_cost_tool.core.normalization.normalizer import normalize_records
from job_cost_tool.services.validation_service import validate_records


class NormalizationRuleTests(unittest.TestCase):
    """Verify targeted normalization business rules."""

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
