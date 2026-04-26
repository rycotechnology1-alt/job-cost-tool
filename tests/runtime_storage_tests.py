"""Regression tests for the phase-1 runtime storage seam."""

from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from infrastructure.storage import LocalRuntimeFileStore, VercelBlobRuntimeStorage
from tests.runtime_storage_test_helpers import FakeBlobObjectClient


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

    def test_delete_export_artifact_removes_payload_and_metadata(self) -> None:
        stored_artifact = self.store.save_export_artifact(
            processing_run_id="processing-run:123",
            session_revision=2,
            original_filename="recap-export.xlsx",
            content_bytes=b"workbook-bytes",
        )

        self.store.delete_export_artifact(stored_artifact.storage_ref)

        self.assertFalse(stored_artifact.file_path.exists())
        self.assertFalse((stored_artifact.file_path.parent / "metadata.json").exists())
        with self.assertRaises(FileNotFoundError):
            self.store.get_export_artifact(stored_artifact.storage_ref)

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

    def test_stored_upload_reports_expiration_timestamp(self) -> None:
        stored_upload = self.store.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        resolved_upload = self.store.get_upload(stored_upload.upload_id)

        self.assertEqual(stored_upload.expires_at, self.current_time + timedelta(hours=24))
        self.assertEqual(resolved_upload.expires_at, self.current_time + timedelta(hours=24))

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


class VercelBlobRuntimeStorageTests(unittest.TestCase):
    """Verify the shared hosted runtime storage implementation stays multi-instance safe."""

    def setUp(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        self.current_time = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
        self.blob_client = FakeBlobObjectClient()
        self.instance_a = VercelBlobRuntimeStorage(
            blob_client=self.blob_client,
            upload_root=TEST_ROOT / "instance-a" / "uploads",
            export_root=TEST_ROOT / "instance-a" / "exports",
            upload_retention_hours=24,
            now_provider=lambda: self.current_time,
        )
        self.instance_b = VercelBlobRuntimeStorage(
            blob_client=self.blob_client,
            upload_root=TEST_ROOT / "instance-b" / "uploads",
            export_root=TEST_ROOT / "instance-b" / "exports",
            upload_retention_hours=24,
            now_provider=lambda: self.current_time,
        )

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_upload_saved_by_one_instance_can_be_loaded_by_another(self) -> None:
        stored_upload = self.instance_a.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        resolved_upload = self.instance_b.get_upload(stored_upload.upload_id)

        self.assertEqual(resolved_upload.upload_id, stored_upload.upload_id)
        self.assertEqual(resolved_upload.storage_ref, stored_upload.storage_ref)
        self.assertEqual(resolved_upload.expires_at, self.current_time + timedelta(hours=24))
        self.assertEqual(resolved_upload.file_path.read_bytes(), b"pdf-bytes")
        self.assertTrue(str(resolved_upload.file_path).startswith(str((TEST_ROOT / "instance-b").resolve())))

    def test_export_artifact_saved_by_one_instance_can_be_downloaded_by_another(self) -> None:
        stored_artifact = self.instance_a.save_export_artifact(
            processing_run_id="processing-run:123",
            session_revision=1,
            original_filename="recap.xlsx",
            content_bytes=b"export-bytes",
        )

        resolved_artifact = self.instance_b.get_export_artifact(stored_artifact.storage_ref)

        self.assertEqual(resolved_artifact.storage_ref, stored_artifact.storage_ref)
        self.assertEqual(resolved_artifact.original_filename, "recap.xlsx")
        self.assertEqual(resolved_artifact.file_path.read_bytes(), b"export-bytes")

    def test_delete_export_artifact_removes_remote_payload_metadata_and_cached_file(self) -> None:
        stored_artifact = self.instance_a.save_export_artifact(
            processing_run_id="processing-run:123",
            session_revision=1,
            original_filename="recap.xlsx",
            content_bytes=b"export-bytes",
        )

        self.instance_b.delete_export_artifact(stored_artifact.storage_ref)

        self.assertNotIn(stored_artifact.storage_ref, self.blob_client.list_paths(prefix="exports/"))
        self.assertNotIn(
            "exports/processing-run-123/" + stored_artifact.storage_ref.split("/")[2] + "/metadata.json",
            self.blob_client.list_paths(prefix="exports/"),
        )
        self.assertFalse((TEST_ROOT / "instance-b" / "exports" / stored_artifact.storage_ref).exists())
        with self.assertRaises(FileNotFoundError):
            self.instance_a.get_export_artifact(stored_artifact.storage_ref)

    def test_get_upload_rejects_expired_remote_upload_without_request_time_cleanup(self) -> None:
        stored_upload = self.instance_a.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        self.current_time += timedelta(hours=25)

        with self.assertRaises(FileNotFoundError):
            self.instance_b.get_upload(stored_upload.upload_id)

        self.assertIn(f"uploads/{stored_upload.upload_id}/metadata.json", self.blob_client.list_paths(prefix="uploads/"))

    def test_cleanup_expired_uploads_deletes_remote_payload_and_metadata_explicitly(self) -> None:
        stored_upload = self.instance_a.save_upload(
            original_filename="report.pdf",
            content_bytes=b"pdf-bytes",
            content_type="application/pdf",
        )

        self.current_time += timedelta(hours=25)
        deleted_count = self.instance_b.cleanup_expired_uploads()

        self.assertEqual(deleted_count, 1)
        self.assertEqual(self.blob_client.list_paths(prefix="uploads/"), [])
        with self.assertRaises(FileNotFoundError):
            self.instance_a.get_upload(stored_upload.upload_id)


if __name__ == "__main__":
    unittest.main()
