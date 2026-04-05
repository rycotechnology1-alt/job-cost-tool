"""Tests for the minimal API runtime settings seam."""

from __future__ import annotations

import unittest
from pathlib import Path

from api.settings import ApiSettings


class ApiSettingsTests(unittest.TestCase):
    """Verify phase-1 API defaults stay simple and locally runnable."""

    def test_from_env_uses_phase1_local_defaults(self) -> None:
        settings = ApiSettings.from_env({})

        self.assertEqual(settings.database_path, str(Path("runtime/api") / "lineage.db"))
        self.assertEqual(settings.upload_root, Path("runtime/api/uploads"))
        self.assertEqual(settings.export_root, Path("runtime/api/exports"))
        self.assertEqual(settings.engine_version, "dev-local")

    def test_with_overrides_preserves_simple_explicit_runtime_values(self) -> None:
        settings = ApiSettings.from_env({}).with_overrides(
            database_path=":memory:",
            upload_root="tests/runtime/uploads",
            export_root="tests/runtime/exports",
            engine_version="engine-test",
        )

        self.assertEqual(settings.database_path, ":memory:")
        self.assertEqual(settings.upload_root, Path("tests/runtime/uploads"))
        self.assertEqual(settings.export_root, Path("tests/runtime/exports"))
        self.assertEqual(settings.engine_version, "engine-test")


if __name__ == "__main__":
    unittest.main()
