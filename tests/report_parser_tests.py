"""Focused regression tests for report-level record emission."""

from __future__ import annotations

import unittest

from job_cost_tool.core.models.record import LABOR, MATERIAL, PROJECT_MANAGEMENT, SUBCONTRACTOR
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


    def test_consecutive_jc_lines_are_emitted_as_separate_records(self) -> None:
        pages = [
            {
                "page_number": 2,
                "text": "\n".join(
                    [
                        "31 . . Internal Equip. Charges",
                        "JC 02/04/26 Equipment from 230566 to 260089 (JCA 0078) -4.00 -152.00",
                        "JC 02/09/26 Equipment from 230566 to 260089 (JCA 0078) -8.00 -304.00",
                        "JC 02/09/26 Equipment from 230566 to 260089 (JCA 0078) -6.00 -228.00",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 3)
        self.assertEqual([record.transaction_type for record in records], ["JC", "JC", "JC"])
        self.assertEqual(
            [record.source_line_text for record in records],
            [
                "JC 02/04/26 Equipment from 230566 to 260089 (JCA 0078) -4.00 -152.00",
                "JC 02/09/26 Equipment from 230566 to 260089 (JCA 0078) -8.00 -304.00",
                "JC 02/09/26 Equipment from 230566 to 260089 (JCA 0078) -6.00 -228.00",
            ],
        )
        self.assertTrue(all(record.record_type == "equipment" for record in records))
        self.assertTrue(all(record.transaction_type == "JC" for record in records))



    def test_phase_header_with_dotted_subphase_updates_context_for_following_pr_record(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "20 . . Labor-Electricians",
                        "PR 03/11/26 103/J 1.00 / 1716 / Dorsey , Michael A5 Regular Earnings 8.00 ST 973.98",
                        "Total For Phase: 20 . . 8.00 973.98",
                        "29 .999. Labor-Non-Job Related Time",
                        "PR 03/12/26 103/J 1.00 / 1716 / Dorsey , Michael A5 Regular Earnings 8.00 ST 973.98",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].phase_code, "20")
        self.assertEqual(records[0].phase_name_raw, "Labor-Electricians")
        self.assertEqual(records[1].phase_code, "29 .999")
        self.assertEqual(records[1].phase_name_raw, "Labor-Non-Job Related Time")
        self.assertEqual(records[1].transaction_type, "PR")
        self.assertEqual(records[1].record_type, LABOR)
        self.assertEqual(
            records[1].raw_description,
            "103/J 1.00 / 1716 / Dorsey , Michael A5 Regular Earnings",
        )



    def test_phase_25_project_management_jc_record_keeps_project_management_raw_type(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "25 . . Labor-Project Mgmt",
                        "JC 03/05/26 Bugeted PM Allocation 0.00 20,000.00",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].phase_code, "25")
        self.assertEqual(records[0].phase_name_raw, "Labor-Project Mgmt")
        self.assertEqual(records[0].transaction_type, "JC")
        self.assertEqual(records[0].record_type, PROJECT_MANAGEMENT)
        self.assertEqual(records[0].raw_description, "Bugeted PM Allocation")
        self.assertEqual(records[0].hours, 0.0)
        self.assertEqual(records[0].cost, 20000.0)
        self.assertNotIn("Section type is not yet confidently classified.", records[0].warnings)


    def test_phase_40_subcontracted_ap_record_keeps_subcontractor_raw_type(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "40 . . Subcontracted",
                        "AP 03/20/26 974 CJ Shaughnessy Crane 24942 / TR# 108 / 1 / APCo: 2 / SL#-Item 842600.001-1 0.00 6,000.00",
                        "quote",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].phase_code, "40")
        self.assertEqual(records[0].phase_name_raw, "Subcontracted")
        self.assertEqual(records[0].transaction_type, "AP")
        self.assertEqual(records[0].record_type, SUBCONTRACTOR)
        self.assertEqual(records[0].vendor_id_raw, "974")
        self.assertEqual(records[0].vendor_name, "CJ Shaughnessy Crane")


    def test_unknown_transaction_line_starts_new_record_instead_of_merging(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "11 . . Material-Electrical",
                        "AP 03/20/26 1201 St Jean Construction 1006 / TR# 68 / 1 / APCo: 2 / PO#-Line 830000.0024-1 door 0.00 9192.15",
                        "IC 03/20/26 Trego bofa cost to DCR Blue Hills / Src JCCo: 1 0.00 -898.25",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].transaction_type, "AP")
        self.assertEqual(records[1].transaction_type, "IC")
        self.assertEqual(records[1].record_type, MATERIAL)
        self.assertEqual(records[1].source_line_text, "IC 03/20/26 Trego bofa cost to DCR Blue Hills / Src JCCo: 1 0.00 -898.25")
        self.assertEqual(records[1].raw_description, "Trego bofa cost to DCR Blue Hills / Src JCCo: 1")
        self.assertEqual(records[1].hours, 0.0)
        self.assertEqual(records[1].cost, -898.25)

    def test_negative_amount_ap_line_keeps_material_family_and_numeric_columns(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "11 . . Material-Electrical",
                        "AP 03/12/26 772 Berts Electric Suppl 576862 / TR# 24 / 0 / APCo: 2 Material 0.00 -525.00",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_type, MATERIAL)
        self.assertEqual(records[0].hours, 0.0)
        self.assertEqual(records[0].cost, -525.0)
        self.assertEqual(records[0].vendor_id_raw, "772")
        self.assertEqual(records[0].vendor_name, "Berts Electric Suppl")
        self.assertEqual(records[0].warnings, [])

    def test_market_recovery_ic_line_uses_phase_mapping_for_material_fallback(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "29 . . Market Recovery",
                        "IC 12/22/25 MR252080 / Src JCCo: 1 0.00 -28,950.00",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].phase_code, "29")
        self.assertEqual(records[0].phase_name_raw, "Market Recovery")
        self.assertEqual(records[0].transaction_type, "IC")
        self.assertEqual(records[0].record_type, MATERIAL)
        self.assertEqual(records[0].raw_description, "MR252080 / Src JCCo: 1")
        self.assertEqual(records[0].hours, 0.0)
        self.assertEqual(records[0].cost, -28950.0)


    def test_jc_labor_line_without_explicit_hour_type_still_remains_a_record(self) -> None:
        pages = [
            {
                "page_number": 1,
                "text": "\n".join(
                    [
                        "20 . . Labor-Electricians",
                        "JC 01/07/26 Jay Dondero to 810500 warranty -4.00 -658.45",
                    ]
                ),
            }
        ]

        records = parse_report_pages(pages)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].transaction_type, "JC")
        self.assertEqual(records[0].record_type, "labor")
        self.assertEqual(records[0].raw_description, "Jay Dondero to 810500 warranty")
        self.assertEqual(records[0].hours, -4.0)
        self.assertIsNone(records[0].hour_type)
        self.assertEqual(records[0].cost, -658.45)


if __name__ == "__main__":
    unittest.main()
