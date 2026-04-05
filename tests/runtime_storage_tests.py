"""Regression tests for the phase-1 runtime storage seam."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from infrastructure.storage import LocalRuntimeFileStore


TEST_ROOT = Path("tests/_runtime_storage_tmp")


class RuntimeStorageTests(unittest.TestCase):
    """Verify local runtime storage still behaves correctly behind the storage seam."""

    def setUp(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        self.store = LocalRuntimeFileStore(
            upload_root=TEST_ROOT / "uploads",
            export_root=TEST_ROOT / "exports",
        )

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_export_artifact_round_trips_through_storage_ref(self) -> None:
        stored_artifact = self.store.save_export_artifact(
            processing_run_id="processing-run:123",
            session_revision=2,
            original_filename="recap-export.xlsx",
            content_bytes=b"workbook-bytes",
        )

        resolved_artifact = self.store.get_export_artifact(stored_artifact.storage_ref)

        self.assertTrue(stored_artifact.storage_ref.startswith("exports/"))
        self.assertEqual(resolved_artifact.original_filename, "recap-export.xlsx")
        self.assertEqual(resolved_artifact.file_size_bytes, len(b"workbook-bytes"))
        self.assertEqual(resolved_artifact.file_path.read_bytes(), b"workbook-bytes")


if __name__ == "__main__":
    unittest.main()
