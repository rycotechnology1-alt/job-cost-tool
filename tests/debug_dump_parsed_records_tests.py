"""Tests for the parsed-record diagnostic dump utility."""

from __future__ import annotations

import unittest
from pathlib import Path

from core.models.record import EQUIPMENT, Record
from tools.debug_dump_parsed_records import _default_output_path, _record_to_row


class DebugDumpParsedRecordsTests(unittest.TestCase):
    """Verify the CSV dump helper keeps diff-relevant traceability fields."""

    def test_record_to_row_preserves_traceability_fields(self) -> None:
        record = Record(
            record_type=EQUIPMENT,
            phase_code="31",
            cost=360.0,
            hours=8.0,
            hour_type=None,
            union_code=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description="751/Kubota Tracked Skid Steer",
            equipment_category=None,
            confidence=0.3,
            raw_description="104/EO B / 24 / Baez , Juan O 751/Kubota Tracked Skid Steer / 1",
            labor_class_raw=None,
            phase_name_raw="Internal Equip. Charges",
            source_page=1,
            source_line_text="PR 02/23/26 104/EO B / 24 / Baez , Juan O 751/Kubota Tracked Skid Steer / 1 8.00 360.00",
            employee_id="24",
            employee_name="Baez , Juan O",
            transaction_type="PR",
            equipment_mapping_key="KUBOTA TRACKED SKID STEER",
            warnings=["Example warning"],
        )

        row = _record_to_row(record, 7)

        self.assertEqual(row["record_index"], 7)
        self.assertEqual(row["source_page"], 1)
        self.assertEqual(row["raw_type"], EQUIPMENT)
        self.assertEqual(row["normalized_type"], "")
        self.assertEqual(row["phase_code"], "31")
        self.assertEqual(row["phase_name"], "Internal Equip. Charges")
        self.assertEqual(row["transaction_type"], "PR")
        self.assertEqual(row["equipment_description"], "751/Kubota Tracked Skid Steer")
        self.assertEqual(row["equipment_mapping_key"], "KUBOTA TRACKED SKID STEER")
        self.assertEqual(row["source_line_text"], record.source_line_text)
        self.assertEqual(row["warning_count"], 1)
        self.assertEqual(row["warnings"], "Example warning")
        self.assertFalse(row["has_blocking_warning"])

    def test_default_output_path_lives_next_to_pdf(self) -> None:
        pdf_path = Path(r"C:\temp\header-issue.pdf")

        output_path = _default_output_path(pdf_path)

        self.assertEqual(output_path, Path(r"C:\temp\header-issue_parsed_records.csv"))


if __name__ == "__main__":
    unittest.main()
