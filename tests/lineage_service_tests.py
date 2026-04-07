"""Regression tests for phase-1 lineage rules and initial persistence schema."""

from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from core.models import Record
from core.models.lineage import PendingRecordEdit, ProcessingRun
from services.lineage_service import (
    append_review_edit_batch,
    build_export_artifact,
    build_profile_snapshot,
    build_record_key,
    build_run_records,
    build_template_artifact,
    create_review_session,
)


SCHEMA_PATH = Path("infrastructure/persistence/phase1_lineage_schema.sql")


class LineageServiceTests(unittest.TestCase):
    """Verify immutable lineage helpers and schema contracts before API work begins."""

    def setUp(self) -> None:
        self.created_at = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)

    def test_build_profile_snapshot_uses_canonical_hashing_for_reordered_payloads(self) -> None:
        snapshot_a = build_profile_snapshot(
            profile_snapshot_id="snap-1",
            organization_id="org-1",
            trusted_profile_id="profile-1",
            bundle_payload={
                "rates": {"labor_rates": {"103 Journeyman": {"standard_rate": 1.0}}},
                "phase_mapping": {"29 .999": "LABOR"},
            },
            engine_version="engine-1",
            created_at=self.created_at,
            template_file_hash="template-hash",
        )
        snapshot_b = build_profile_snapshot(
            profile_snapshot_id="snap-2",
            organization_id="org-1",
            trusted_profile_id="profile-1",
            bundle_payload={
                "phase_mapping": {"29 .999": "LABOR"},
                "rates": {"labor_rates": {"103 Journeyman": {"standard_rate": 1.0}}},
            },
            engine_version="engine-1",
            created_at=self.created_at,
            template_file_hash="template-hash",
        )

        self.assertEqual(snapshot_a.content_hash, snapshot_b.content_hash)

    def test_build_profile_snapshot_preserves_ordered_bundle_payload_for_order_sensitive_configs(self) -> None:
        snapshot = build_profile_snapshot(
            profile_snapshot_id="snap-1",
            organization_id="org-1",
            trusted_profile_id="profile-1",
            bundle_payload={
                "recap_template_map": {
                    "labor_rows": {
                        "103 General FM": {"st_hours": "B12"},
                        "103 Foreman": {"st_hours": "B13"},
                        "103 Journeyman": {"st_hours": "B14"},
                    }
                }
            },
            engine_version="engine-1",
            created_at=self.created_at,
            template_file_hash="template-hash",
        )

        labor_rows = snapshot.bundle_payload["recap_template_map"]["labor_rows"]
        self.assertEqual(list(labor_rows.keys()), ["103 General FM", "103 Foreman", "103 Journeyman"])

    def test_build_profile_snapshot_can_hash_behavioral_bundle_separately_from_traceability(self) -> None:
        snapshot_a = build_profile_snapshot(
            profile_snapshot_id="snap-1",
            organization_id="org-1",
            trusted_profile_id=None,
            bundle_payload={
                "behavioral_bundle": {"rates": {"labor_rates": {"A": {"standard_rate": 1.0}}}},
                "traceability": {"trusted_profile": {"profile_name": "default", "description": "Profile A"}},
            },
            hash_payload={"rates": {"labor_rates": {"A": {"standard_rate": 1.0}}}},
            engine_version="engine-1",
            created_at=self.created_at,
        )
        snapshot_b = build_profile_snapshot(
            profile_snapshot_id="snap-2",
            organization_id="org-1",
            trusted_profile_id=None,
            bundle_payload={
                "behavioral_bundle": {"rates": {"labor_rates": {"A": {"standard_rate": 1.0}}}},
                "traceability": {"trusted_profile": {"profile_name": "alternate", "description": "Profile B"}},
            },
            hash_payload={"rates": {"labor_rates": {"A": {"standard_rate": 1.0}}}},
            engine_version="engine-1",
            created_at=self.created_at,
        )

        self.assertEqual(snapshot_a.content_hash, snapshot_b.content_hash)
        self.assertNotEqual(snapshot_a.canonical_bundle_json, snapshot_b.canonical_bundle_json)

    def test_build_template_artifact_uses_exact_content_hash(self) -> None:
        artifact = build_template_artifact(
            template_artifact_id="template-1",
            organization_id="org-1",
            original_filename="recap_template.xlsx",
            content_bytes=b"template-bytes-v1",
            created_at=self.created_at,
        )

        self.assertEqual(artifact.original_filename, "recap_template.xlsx")
        self.assertEqual(artifact.file_size_bytes, len(b"template-bytes-v1"))
        self.assertEqual(artifact.content_hash, sha256(b"template-bytes-v1").hexdigest())

    def test_build_run_records_uses_run_scoped_order_based_record_keys(self) -> None:
        base_record = Record(
            record_type="labor",
            phase_code="20",
            raw_description="Labor line",
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized="J",
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="source line",
            record_type_normalized="labor",
        )
        run_records = build_run_records(
            organization_id="org-1",
            processing_run_id="run-1",
            records=[
                base_record,
                replace(base_record, raw_description="Second line", source_line_text="second line"),
            ],
            created_at=self.created_at,
        )

        self.assertEqual([record.record_key for record in run_records], ["record-0", "record-1"])
        self.assertEqual(run_records[0].run_record_id, "run-1:record-0")
        self.assertEqual(run_records[0].source_line_text, "source line")
        self.assertEqual(run_records[1].canonical_record["raw_description"], "Second line")

    def test_record_keys_restart_for_new_runs(self) -> None:
        self.assertEqual(build_record_key(0), "record-0")
        self.assertEqual(build_record_key(1), "record-1")
        with self.assertRaisesRegex(ValueError, "record_index"):
            build_record_key(-1)

    def test_review_session_revisions_advance_once_per_accepted_batch(self) -> None:
        session = create_review_session(
            review_session_id="session-1",
            organization_id="org-1",
            processing_run_id="run-1",
            created_at=self.created_at,
            created_by_user_id="user-1",
        )

        updated_session, persisted_edits = append_review_edit_batch(
            review_session=session,
            pending_edits=[
                PendingRecordEdit(record_key="record-0", changed_fields={"is_omitted": True}),
                PendingRecordEdit(record_key="record-1", changed_fields={"vendor_name_normalized": "Acme"}),
            ],
            created_at=self.created_at,
            created_by_user_id="user-1",
        )

        reopened_session, second_batch = append_review_edit_batch(
            review_session=updated_session,
            pending_edits=[
                PendingRecordEdit(record_key="record-0", changed_fields={"is_omitted": False}),
            ],
            created_at=self.created_at,
            created_by_user_id="user-1",
        )

        self.assertEqual(session.current_revision, 0)
        self.assertEqual(updated_session.current_revision, 1)
        self.assertEqual(reopened_session.current_revision, 2)
        self.assertEqual({edit.session_revision for edit in persisted_edits}, {1})
        self.assertEqual(second_batch[0].session_revision, 2)

    def test_review_edit_batch_rejects_duplicate_record_keys_and_empty_changes(self) -> None:
        session = create_review_session(
            review_session_id="session-1",
            organization_id="org-1",
            processing_run_id="run-1",
            created_at=self.created_at,
        )

        with self.assertRaisesRegex(ValueError, "Duplicate record_key"):
            append_review_edit_batch(
                review_session=session,
                pending_edits=[
                    PendingRecordEdit(record_key="record-0", changed_fields={"is_omitted": True}),
                    PendingRecordEdit(record_key="record-0", changed_fields={"is_omitted": False}),
                ],
                created_at=self.created_at,
            )

        with self.assertRaisesRegex(ValueError, "at least one changed field"):
            append_review_edit_batch(
                review_session=session,
                pending_edits=[PendingRecordEdit(record_key="record-0", changed_fields={})],
                created_at=self.created_at,
            )

    def test_export_artifact_must_reference_exact_known_session_revision(self) -> None:
        run = ProcessingRun(
            processing_run_id="run-1",
            organization_id="org-1",
            source_document_id="doc-1",
            profile_snapshot_id="snap-1",
            status="completed",
            engine_version="engine-1",
            aggregate_blockers=(),
            created_at=self.created_at,
            trusted_profile_id="profile-1",
        )
        session = replace(
            create_review_session(
                review_session_id="session-1",
                organization_id="org-1",
                processing_run_id="run-1",
                created_at=self.created_at,
            ),
            current_revision=2,
        )

        artifact = build_export_artifact(
            export_artifact_id="export-1",
            organization_id="org-1",
            processing_run=run,
            review_session=session,
            session_revision=2,
            artifact_kind="recap_workbook",
            storage_ref="artifacts/export-1.xlsx",
            created_at=self.created_at,
            created_by_user_id="user-1",
            file_hash="hash-1",
        )

        self.assertEqual(artifact.session_revision, 2)
        with self.assertRaisesRegex(ValueError, "current revision"):
            build_export_artifact(
                export_artifact_id="export-2",
                organization_id="org-1",
                processing_run=run,
                review_session=session,
                session_revision=3,
                artifact_kind="recap_workbook",
                storage_ref="artifacts/export-2.xlsx",
                created_at=self.created_at,
            )

    def test_phase1_schema_creates_expected_tables_and_constraints(self) -> None:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(schema_sql)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            expected_tables = {
                "organizations",
                "users",
                "trusted_profiles",
                "trusted_profile_versions",
                "trusted_profile_drafts",
                "trusted_profile_observations",
                "trusted_profile_sync_exports",
                "template_artifacts",
                "profile_snapshots",
                "source_documents",
                "processing_runs",
                "run_records",
                "review_sessions",
                "reviewed_record_edits",
                "export_artifacts",
            }
            self.assertTrue(expected_tables.issubset(tables))

            connection.execute(
                "INSERT INTO organizations (organization_id, slug, display_name, created_at) VALUES (?, ?, ?, ?)",
                ("org-1", "seeded-org", "Seeded Org", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO users (user_id, organization_id, email, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
                ("user-1", "org-1", "user@example.com", "User", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO trusted_profiles (trusted_profile_id, organization_id, profile_name, display_name, source_kind, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("profile-1", "org-1", "default", "Default", "seeded", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO template_artifacts (template_artifact_id, organization_id, content_hash, original_filename, content_bytes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("template-1", "org-1", "template-hash", "recap_template.xlsx", sqlite3.Binary(b'template'), "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO profile_snapshots (profile_snapshot_id, organization_id, trusted_profile_id, content_hash, bundle_json, engine_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("snap-1", "org-1", "profile-1", "hash-1", "{}", "engine-1", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO source_documents (source_document_id, organization_id, original_filename, file_hash, storage_ref, content_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("doc-1", "org-1", "report.pdf", "file-hash", "storage/report.pdf", "application/pdf", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO processing_runs (processing_run_id, organization_id, source_document_id, profile_snapshot_id, trusted_profile_id, status, engine_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("run-1", "org-1", "doc-1", "snap-1", "profile-1", "completed", "engine-1", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO run_records (run_record_id, organization_id, processing_run_id, record_key, record_index, canonical_record_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-1:record-0", "org-1", "run-1", "record-0", 0, "{}", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO review_sessions (review_session_id, organization_id, processing_run_id, current_revision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("session-1", "org-1", "run-1", 1, "2026-04-05T12:00:00Z", "2026-04-05T12:00:00Z"),
            )
            connection.execute(
                "INSERT INTO reviewed_record_edits (reviewed_record_edit_id, organization_id, processing_run_id, review_session_id, record_key, session_revision, changed_fields_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("edit-1", "org-1", "run-1", "session-1", "record-0", 1, '{"is_omitted":true}', "2026-04-05T12:00:00Z"),
            )

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO run_records (run_record_id, organization_id, processing_run_id, record_key, record_index, canonical_record_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("run-1:record-0-dup", "org-1", "run-1", "record-0", 1, "{}", "2026-04-05T12:00:00Z"),
                )

            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO reviewed_record_edits (reviewed_record_edit_id, organization_id, processing_run_id, review_session_id, record_key, session_revision, changed_fields_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("edit-2", "org-1", "run-1", "session-1", "record-0", 0, '{"is_omitted":false}', "2026-04-05T12:00:00Z"),
                )
        finally:
            connection.close()
