"""Regression tests for SQLite lineage-store bootstrap behavior."""

from __future__ import annotations

import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.persistence import SqliteLineageStore


TEST_ROOT = Path("tests/_sqlite_lineage_store_tmp")


class SqliteLineageStoreTests(unittest.TestCase):
    """Verify local SQLite bootstrap stays safe across repeated opens."""

    def setUp(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.database_path = TEST_ROOT / "lineage.db"
        self.created_at = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)

    def test_reopening_initialized_local_database_does_not_fail_or_drop_existing_data(self) -> None:
        first_store = SqliteLineageStore(self.database_path)
        try:
            organization = first_store.ensure_organization(
                organization_id="org-default",
                slug="default-org",
                display_name="Default Organization",
                created_at=self.created_at,
                is_seeded=True,
            )
            self.assertEqual(organization.organization_id, "org-default")
        finally:
            first_store.close()

        second_store = SqliteLineageStore(self.database_path)
        try:
            reopened_organization = second_store.ensure_organization(
                organization_id="org-default",
                slug="default-org",
                display_name="Default Organization",
                created_at=self.created_at,
                is_seeded=True,
            )
            self.assertEqual(reopened_organization.organization_id, "org-default")
            row = second_store._connection.execute(
                "SELECT COUNT(*) FROM organizations WHERE organization_id = ?",
                ("org-default",),
            ).fetchone()
            self.assertEqual(row[0], 1)
        finally:
            second_store.close()


if __name__ == "__main__":
    unittest.main()
