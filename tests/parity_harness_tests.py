"""Representative parity-harness tests for the accepted phase-1 workflow."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from core.config import ConfigLoader
from tests.parity_harness.corpus import load_parity_case
from tests.parity_harness.harness import (
    build_reference_export_snapshot,
    build_expected_snapshot,
    compare_parity_snapshot,
    run_desktop_reference_path,
    run_web_api_path,
)
from tests.parity_harness.workbook_semantics import compare_workbook_snapshots


TEST_ROOT = Path("tests/_parity_tmp")


class Phase1ParityHarnessTests(unittest.TestCase):
    """Verify the semantic parity harness across desktop and accepted web paths."""

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        ConfigLoader.clear_runtime_caches()

    def test_material_vendor_resolution_case_matches_expected_semantics_for_desktop_and_web(self) -> None:
        case = load_parity_case("material_vendor_resolution")
        expected_snapshot = build_expected_snapshot(case)

        desktop_snapshot = run_desktop_reference_path(case, TEST_ROOT / "desktop")
        web_snapshot = run_web_api_path(case, TEST_ROOT / "web")

        desktop_diffs = compare_parity_snapshot(expected_snapshot, desktop_snapshot, label="desktop path")
        web_diffs = compare_parity_snapshot(expected_snapshot, web_snapshot, label="web path")
        cross_path_diffs = compare_parity_snapshot(desktop_snapshot, web_snapshot, label="desktop vs web")

        self.assertEqual(desktop_diffs, [])
        self.assertEqual(web_diffs, [])
        self.assertEqual(cross_path_diffs, [])

    def test_workbook_semantic_diff_reports_meaningful_mismatch(self) -> None:
        expected = {
            "worksheet_name": "Recap",
            "cells": {"G27": {"value": "Vendor Approved", "style_id": 1}},
        }
        actual = {
            "worksheet_name": "Recap",
            "cells": {"G27": {"value": "Wrong Vendor", "style_id": 1}},
        }

        diffs = compare_workbook_snapshots(expected, actual, label="workbook parity")

        self.assertEqual(len(diffs), 1)
        self.assertIn("G27", diffs[0])
        self.assertIn("Wrong Vendor", diffs[0])

    def test_real_reference_exports_match_desktop_and_web_semantically(self) -> None:
        case_names = [
            "1harness",
            "2pass",
            "5pass",
            "6harness",
            "7harness",
            "10harness",
            "11harness",
            "12pass",
            "15harness-user-omit",
            "17harness",
            "18harness",
            "19pass",
            "22harness",
        ]

        for case_name in case_names:
            with self.subTest(case=case_name):
                case = load_parity_case(case_name)
                expected_export_snapshot = build_reference_export_snapshot(case)

                desktop_snapshot = run_desktop_reference_path(case, TEST_ROOT / f"{case_name}-desktop")
                web_snapshot = run_web_api_path(case, TEST_ROOT / f"{case_name}-web")

                cross_path_diffs = compare_parity_snapshot(desktop_snapshot, web_snapshot, label=f"{case_name}: desktop vs web")
                desktop_export_diffs = compare_workbook_snapshots(
                    expected_export_snapshot,
                    desktop_snapshot.export_snapshot,
                    label=f"{case_name}: desktop export",
                )
                web_export_diffs = compare_workbook_snapshots(
                    expected_export_snapshot,
                    web_snapshot.export_snapshot,
                    label=f"{case_name}: web export",
                )

                self.assertEqual(cross_path_diffs, [])
                self.assertEqual(desktop_export_diffs, [])
                self.assertEqual(web_export_diffs, [])


if __name__ == "__main__":
    unittest.main()
