"""Focused regression tests for report-level record emission."""

from __future__ import annotations

import unittest

from job_cost_tool.core.parsing.report_parser import parse_report_pages


class ReportParserTests(unittest.TestCase):
    """Verify non-record header/filter lines do not leak into parsed output."""

    def test_report_filter_header_line_is_not_emitted_as_a_record(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "DEC - JC Detail Report",
                        "All Jobs Phases: 31 . . - 31 . . All Cost Types Units: Actual",
                        "31 . . Internal Equip. Charges",
                        "PR 02/23/26 104/EO B / 24 / Baez , Juan O 751/Kubota Tracked Skid Steer / 1 8.00 360.00",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].transaction_type, "PR")
        self.assertEqual(records[0].equipment_description, "751/Kubota Tracked Skid Steer")
        self.assertNotIn("All Jobs Phases:", records[0].raw_description)

    def test_transaction_start_still_emits_record_even_without_phase_context(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "PR 02/23/26 104/EO B / 24 / Baez , Juan O 751/Kubota Tracked Skid Steer / 1 8.00 360.00",
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].transaction_type, "PR")
        self.assertEqual(records[0].raw_description, "104/EO B / 24 / Baez , Juan O 751/Kubota Tracked Skid Steer / 1")
        self.assertIn("No active phase context was identified for this line.", records[0].warnings)


if __name__ == "__main__":
    unittest.main()
