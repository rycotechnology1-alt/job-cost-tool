"""Regression tests for the phase-1 runtime storage seam."""

from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from infrastructure.storage import LocalRuntimeFileStore


TEST_ROOT = Path("tests/_runtime_storage_tmp")


class RuntimeStorageTests(unittest.TestCase):
    """Verify local runtime storage still behaves correctly behind the storage seam."""

    def setUp(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        self.current_time = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
        self.store = LocalRuntimeFileStore(
            upload_root=TEST_ROOT / "uploads",
            export_root=TEST_ROOT / "exports",
            upload_retention_hours=24,
            now_provider=lambda: self.current_time,
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

    def test_cleanup_expired_upload_deletes_directory(self) -> None:
        stored_upload = self.store.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        self.current_time += timedelta(hours=25)
        deleted_count = self.store.cleanup_expired_uploads()

        self.assertEqual(deleted_count, 1)
        self.assertFalse((TEST_ROOT / "uploads" / stored_upload.upload_id).exists())

    def test_cleanup_preserves_fresh_upload_directory(self) -> None:
        stored_upload = self.store.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        self.current_time += timedelta(hours=23)
        deleted_count = self.store.cleanup_expired_uploads()

        self.assertEqual(deleted_count, 0)
        self.assertTrue((TEST_ROOT / "uploads" / stored_upload.upload_id).exists())

    def test_cleanup_uses_legacy_directory_mtime_when_created_at_is_missing(self) -> None:
        stored_upload = self.store.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )
        upload_dir = TEST_ROOT / "uploads" / stored_upload.upload_id
        metadata_path = upload_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.pop("created_at", None)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

        legacy_time = self.current_time - timedelta(hours=25)
        legacy_timestamp = legacy_time.timestamp()
        for path in [upload_dir, metadata_path, upload_dir / "report.pdf"]:
            path.touch()
            Path(path).stat()
        import os
        os.utime(upload_dir / "report.pdf", (legacy_timestamp, legacy_timestamp))
        os.utime(metadata_path, (legacy_timestamp, legacy_timestamp))
        os.utime(upload_dir, (legacy_timestamp, legacy_timestamp))

        deleted_count = self.store.cleanup_expired_uploads()

        self.assertEqual(deleted_count, 1)
        self.assertFalse(upload_dir.exists())

    def test_cleanup_disabled_leaves_uploads_untouched(self) -> None:
        disabled_store = LocalRuntimeFileStore(
            upload_root=TEST_ROOT / "uploads-disabled",
            export_root=TEST_ROOT / "exports-disabled",
            upload_retention_hours=0,
            now_provider=lambda: self.current_time,
        )
        stored_upload = disabled_store.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        self.current_time += timedelta(days=30)
        deleted_count = disabled_store.cleanup_expired_uploads()

        self.assertEqual(deleted_count, 0)
        self.assertTrue((TEST_ROOT / "uploads-disabled" / stored_upload.upload_id).exists())


if __name__ == "__main__":
    unittest.main()
