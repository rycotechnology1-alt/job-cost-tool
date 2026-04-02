"""Focused tests for shared phase-code canonicalization."""

from __future__ import annotations

import unittest

from job_cost_tool.core.parsing.line_classifier import extract_phase_header
from job_cost_tool.core.phase_codes import canonicalize_phase_code, phase_code_sort_key


class PhaseCodeTests(unittest.TestCase):
    """Verify conservative phase-code canonicalization behavior."""

    def test_canonicalize_phase_code_preserves_meaningful_dotted_subphases(self) -> None:
        self.assertEqual(canonicalize_phase_code("29 .   ."), "29")
        self.assertEqual(canonicalize_phase_code("29 .999."), "29 .999")
        self.assertEqual(canonicalize_phase_code("13 .25 ."), "13 .25")
        self.assertEqual(canonicalize_phase_code("13 .5  ."), "13 .5")
        self.assertNotEqual(canonicalize_phase_code("29 .999."), canonicalize_phase_code("29 .   ."))

    def test_phase_code_sort_key_keeps_parent_and_subphase_distinct(self) -> None:
        ordered = sorted(["29 .999", "29", "13 .25", "13 .5"], key=phase_code_sort_key)
        self.assertEqual(ordered, ["13 .5", "13 .25", "29", "29 .999"])

    def test_extract_phase_header_uses_canonical_phase_code_representation(self) -> None:
        self.assertEqual(
            extract_phase_header("29 .999. Labor-Non-Job Related Time"),
            ("29 .999", "Labor-Non-Job Related Time"),
        )
        self.assertEqual(
            extract_phase_header("29 .   . Market Recovery"),
            ("29", "Market Recovery"),
        )
        self.assertEqual(
            extract_phase_header("13 .25 . Material-Transfer"),
            ("13 .25", "Material-Transfer"),
        )
        self.assertEqual(
            extract_phase_header("50 .15 . Utility Service Connections"),
            ("50 .15", "Utility Service Connections"),
        )


if __name__ == "__main__":
    unittest.main()
