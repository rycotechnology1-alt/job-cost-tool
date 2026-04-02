"""Focused tests for labor-class review display behavior."""

from __future__ import annotations

import unittest

from job_cost_tool.core.models.record import LABOR, Record


class ReviewDisplayTests(unittest.TestCase):
    """Verify fallback labor mapping sources do not replace effective display class."""

    def test_fallback_raw_labor_source_does_not_become_effective_display_class(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="21",
            raw_description="1.00 / 186 / Culhane , John P5 Regular Earnings",
            cost=701.66,
            hours=8.0,
            hour_type="ST",
            union_code=None,
            labor_class_raw="1.00 / 186 / Culhane , John P5 Regular Earnings",
            labor_class_normalized="1.00 / 186 / CULHANE , JOHN P5 REGULAR EARNINGS",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.6,
            warnings=[],
            record_type_normalized=LABOR,
            recap_labor_slot_id=None,
            recap_labor_classification=None,
        )

        self.assertTrue(record.uses_fallback_labor_mapping_source())
        self.assertIsNone(record.effective_labor_classification())

    def test_mapped_recap_labor_class_wins_over_fallback_raw_source_for_display(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="21",
            raw_description="1.00 / 186 / Culhane , John P5 Regular Earnings",
            cost=701.66,
            hours=8.0,
            hour_type="ST",
            union_code=None,
            labor_class_raw="1.00 / 186 / Culhane , John P5 Regular Earnings",
            labor_class_normalized="1.00 / 186 / CULHANE , JOHN P5 REGULAR EARNINGS",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.6,
            warnings=[],
            record_type_normalized=LABOR,
            recap_labor_slot_id="labor_1",
            recap_labor_classification="103 General Foreman",
        )

        self.assertTrue(record.uses_fallback_labor_mapping_source())
        self.assertEqual(record.effective_labor_classification(), "103 General Foreman")

    def test_normally_parsed_labor_class_still_displays_normalized_class_when_unmapped(self) -> None:
        record = Record(
            record_type=LABOR,
            phase_code="20",
            raw_description="103/F 1.50 / 778 / Fezoco , Edvard V5 Regular Earnings",
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="F",
            labor_class_normalized="103 Foreman",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            record_type_normalized=LABOR,
            recap_labor_slot_id=None,
            recap_labor_classification=None,
        )

        self.assertFalse(record.uses_fallback_labor_mapping_source())
        self.assertEqual(record.effective_labor_classification(), "103 Foreman")


if __name__ == "__main__":
    unittest.main()
