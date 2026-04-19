"""Tests for the minimal API runtime settings seam."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.app import create_app
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

    def test_explicit_env_mapping_does_not_read_repo_dotenv(self) -> None:
        with patch("api.settings.load_dotenv", side_effect=AssertionError("dotenv should not load"), create=True):
            settings = ApiSettings.from_env({})

        self.assertEqual(settings.database_provider, "postgres")

    def test_from_env_loads_repo_dotenv_when_no_explicit_mapping_is_provided(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "JOB_COST_API_DATABASE_PROVIDER=postgres",
                        "JOB_COST_API_POSTGRES_ADMIN_URL=postgresql://admin-from-dotenv",
                        "JOB_COST_API_POSTGRES_POOLED_URL=postgresql://pooled-from-dotenv",
                        "JOB_COST_API_STORAGE_PROVIDER=vercel_blob",
                        "BLOB_READ_WRITE_TOKEN=blob-token-from-dotenv",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                with patch("api.settings._resolve_repo_env_path", return_value=env_path, create=True):
                    settings = ApiSettings.from_env()

        self.assertEqual(settings.database_provider, "postgres")
        self.assertEqual(settings.postgres_admin_url, "postgresql://admin-from-dotenv")
        self.assertEqual(settings.postgres_pooled_url, "postgresql://pooled-from-dotenv")
        self.assertEqual(settings.storage_provider, "vercel_blob")
        self.assertEqual(settings.blob_read_write_token, "blob-token-from-dotenv")

    def test_process_environment_values_override_repo_dotenv_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "JOB_COST_API_POSTGRES_ADMIN_URL=postgresql://admin-from-dotenv",
                        "JOB_COST_API_POSTGRES_POOLED_URL=postgresql://pooled-from-dotenv",
                        "JOB_COST_API_STORAGE_PROVIDER=local",
                        "BLOB_READ_WRITE_TOKEN=blob-token-from-dotenv",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "JOB_COST_API_POSTGRES_POOLED_URL": "postgresql://pooled-from-os",
                    "JOB_COST_API_STORAGE_PROVIDER": "vercel_blob",
                },
                clear=True,
            ):
                with patch("api.settings._resolve_repo_env_path", return_value=env_path, create=True):
                    settings = ApiSettings.from_env()

        self.assertEqual(settings.postgres_admin_url, "postgresql://admin-from-dotenv")
        self.assertEqual(settings.postgres_pooled_url, "postgresql://pooled-from-os")
        self.assertEqual(settings.storage_provider, "vercel_blob")
        self.assertEqual(settings.blob_read_write_token, "blob-token-from-dotenv")

    def test_create_app_can_boot_from_repo_dotenv_backed_local_settings(self) -> None:
        runtime_root = Path(tempfile.mkdtemp(prefix="job-cost-api-runtime-"))
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".env"
                env_path.write_text(
                    "\n".join(
                        [
                            "JOB_COST_API_DATABASE_PROVIDER=sqlite",
                            f"JOB_COST_API_DATABASE_PATH={(runtime_root / 'lineage.db').as_posix()}",
                            "JOB_COST_API_STORAGE_PROVIDER=local",
                            f"JOB_COST_API_UPLOAD_ROOT={(runtime_root / 'uploads').as_posix()}",
                            f"JOB_COST_API_EXPORT_ROOT={(runtime_root / 'exports').as_posix()}",
                        ]
                    ),
                    encoding="utf-8",
                )

                with patch.dict(os.environ, {}, clear=True):
                    with patch("api.settings._resolve_repo_env_path", return_value=env_path, create=True):
                        app = create_app()
        finally:
            shutil.rmtree(runtime_root, ignore_errors=True)

        self.assertEqual(app.title, "Job Cost Tool API")

    def test_create_app_missing_postgres_url_mentions_local_env_loading(self) -> None:
        missing_env_path = Path(tempfile.gettempdir()) / "job-cost-tool-missing.env"
        with patch.dict(os.environ, {}, clear=True):
            with patch("api.settings._resolve_repo_env_path", return_value=missing_env_path, create=True):
                with self.assertRaisesRegex(
                    ValueError,
                    r"JOB_COST_API_POSTGRES_POOLED_URL.*\.env|process environment",
                ):
                    create_app()

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
