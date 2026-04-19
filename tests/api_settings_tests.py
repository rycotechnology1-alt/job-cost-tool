"""Tests for the minimal API runtime settings seam."""

from __future__ import annotations

import unittest
from pathlib import Path

from api.settings import ApiSettings


class ApiSettingsTests(unittest.TestCase):
    """Verify phase-1 API defaults stay simple and hosted-friendly."""

    def test_hosted_defaults_use_postgres_blob_and_tmp_paths(self) -> None:
        settings = ApiSettings.from_env({})

        self.assertEqual(settings.database_provider, "postgres")
        self.assertEqual(settings.storage_provider, "vercel_blob")
        self.assertEqual(settings.database_path, "/tmp/job-cost-api/lineage.db")
        self.assertEqual(settings.upload_root, Path("/tmp/job-cost-api/uploads"))
        self.assertEqual(settings.export_root, Path("/tmp/job-cost-api/exports"))
        self.assertEqual(settings.upload_retention_hours, 24)
        self.assertEqual(settings.engine_version, "dev-local")

    def test_with_overrides_preserves_simple_explicit_runtime_values(self) -> None:
        settings = ApiSettings.from_env({}).with_overrides(
            database_path=":memory:",
            upload_root="tests/runtime/uploads",
            export_root="tests/runtime/exports",
            upload_retention_hours=48,
            engine_version="engine-test",
        )

        self.assertEqual(settings.database_path, ":memory:")
        self.assertEqual(settings.upload_root, Path("tests/runtime/uploads"))
        self.assertEqual(settings.export_root, Path("tests/runtime/exports"))
        self.assertEqual(settings.upload_retention_hours, 48)
        self.assertEqual(settings.engine_version, "engine-test")


if __name__ == "__main__":
    unittest.main()
