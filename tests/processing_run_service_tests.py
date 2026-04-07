"""Service-level tests for trusted-profile snapshot resolution and immutable processing runs."""

from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from core.config import ConfigLoader, ProfileManager
from core.models import Record
from infrastructure.persistence.sqlite_lineage_store import SqliteLineageStore
from services.processing_run_service import ProcessingRunService


TEST_ROOT = Path("tests/_processing_run_tmp")


class ProcessingRunServiceTests(unittest.TestCase):
    """Verify selected-profile lineage integrity and behavioral snapshot reuse rules."""

    def setUp(self) -> None:
        ConfigLoader.clear_runtime_caches()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        (TEST_ROOT / "profiles" / "default").mkdir(parents=True, exist_ok=True)
        (TEST_ROOT / "legacy_config").mkdir(parents=True, exist_ok=True)
        self.settings_path = TEST_ROOT / "app_settings.json"
        self.source_document_path = TEST_ROOT / "sample_report.pdf"
        self.source_document_path.write_bytes(b"sample pdf bytes")
        self.created_at = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)

        self._write_profile_bundle(
            profile_name="default",
            display_name="Default Profile",
            description="Default test profile",
            version="1.0",
            labor_target="Default Journeyman",
        )
        self._write_json(self.settings_path, {"active_profile": "default"})
        self._write_json(TEST_ROOT / "legacy_config" / "phase_catalog.json", {"phases": []})

        self.profile_manager = ProfileManager(
            profiles_root=TEST_ROOT / "profiles",
            settings_path=self.settings_path,
            legacy_config_root=TEST_ROOT / "legacy_config",
        )
        self.lineage_store = SqliteLineageStore()

    def tearDown(self) -> None:
        self.lineage_store.close()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        ConfigLoader.clear_runtime_caches()

    def test_processing_with_non_active_profile_uses_selected_profile_bundle_for_run_records(self) -> None:
        self._clone_profile(
            source_profile_name="default",
            profile_name="selected_profile",
            display_name="Selected Profile",
            description="Non-active selected profile",
            version="2.0",
            labor_target="Selected Journeyman",
        )
        service = self._build_service()
        parsed_record = self._make_labor_record(raw_description="Selected profile labor line")

        with patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[parsed_record],
        ):
            result = service.create_processing_run(
                self.source_document_path,
                profile_name="selected_profile",
            )

        persisted_run = self.lineage_store.get_processing_run(result.processing_run.processing_run_id)
        persisted_records = self.lineage_store.list_run_records(result.processing_run.processing_run_id)

        self.assertEqual(result.trusted_profile.profile_name, "selected_profile")
        self.assertEqual(
            persisted_run.trusted_profile_id,
            result.trusted_profile.trusted_profile_id,
        )
        self.assertTrue(persisted_run.trusted_profile_version_id)
        self.assertEqual(
            result.profile_snapshot.trusted_profile_version_id,
            persisted_run.trusted_profile_version_id,
        )
        self.assertEqual(
            result.profile_snapshot.bundle_payload["behavioral_bundle"]["labor_mapping"]["raw_mappings"]["103/J"],
            "Selected Journeyman",
        )
        self.assertEqual(
            persisted_records[0].canonical_record["recap_labor_classification"],
            "Selected Journeyman",
        )
        self.assertEqual(
            persisted_records[0].canonical_record["recap_labor_slot_id"],
            "labor_1",
        )

    def test_identical_behavioral_bundles_with_different_metadata_reuse_same_snapshot(self) -> None:
        self._clone_profile(
            source_profile_name="default",
            profile_name="same_behavior",
            display_name="Different Display Name",
            description="Different description",
            version="9.9",
            labor_target="Default Journeyman",
        )
        service = self._build_service()

        default_org, default_profile, default_snapshot = service.resolve_trusted_profile_snapshot()
        cloned_org, cloned_profile, cloned_snapshot = service.resolve_trusted_profile_snapshot("same_behavior")

        self.assertEqual(default_org.organization_id, cloned_org.organization_id)
        self.assertNotEqual(default_profile.trusted_profile_id, cloned_profile.trusted_profile_id)
        self.assertEqual(default_snapshot.profile_snapshot_id, cloned_snapshot.profile_snapshot_id)
        self.assertEqual(default_snapshot.content_hash, cloned_snapshot.content_hash)

    def test_web_processing_uses_persisted_published_version_even_if_filesystem_bundle_later_differs(self) -> None:
        service = self._build_service()
        parsed_record = self._make_labor_record(raw_description="Behavioral change line")

        with patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[parsed_record],
        ):
            first_result = service.create_processing_run(self.source_document_path)
            self._write_json(
                TEST_ROOT / "profiles" / "default" / "rates.json",
                {
                    "labor_rates": {
                        "Default Journeyman": {
                            "standard_rate": 125.0,
                        }
                    },
                    "equipment_rates": {},
                },
            )
            second_result = service.create_processing_run(self.source_document_path)

        first_records = self.lineage_store.list_run_records(first_result.processing_run.processing_run_id)
        second_records = self.lineage_store.list_run_records(second_result.processing_run.processing_run_id)
        trusted_profile = self.lineage_store.get_trusted_profile(first_result.trusted_profile.trusted_profile_id)
        persisted_versions = self.lineage_store.list_trusted_profile_versions(trusted_profile.trusted_profile_id)

        self.assertEqual(first_result.processing_run.trusted_profile_id, second_result.processing_run.trusted_profile_id)
        self.assertEqual(
            first_result.processing_run.trusted_profile_version_id,
            second_result.processing_run.trusted_profile_version_id,
        )
        self.assertEqual(first_result.profile_snapshot.profile_snapshot_id, second_result.profile_snapshot.profile_snapshot_id)
        self.assertEqual(first_result.profile_snapshot.content_hash, second_result.profile_snapshot.content_hash)
        self.assertNotEqual(first_result.processing_run.processing_run_id, second_result.processing_run.processing_run_id)
        self.assertEqual([record.record_key for record in first_records], ["record-0"])
        self.assertEqual([record.record_key for record in second_records], ["record-0"])
        self.assertEqual(first_records[0].canonical_record["raw_description"], "Behavioral change line")
        self.assertEqual(second_records[0].canonical_record["raw_description"], "Behavioral change line")
        self.assertEqual(len(persisted_versions), 1)
        self.assertEqual(len(self.lineage_store.list_processing_runs()), 2)

    def test_missing_current_published_version_is_repaired_from_filesystem_bootstrap(self) -> None:
        service = self._build_service()
        initial_result = service.resolve_trusted_profile_snapshot()
        self.lineage_store._connection.execute(
            """
            UPDATE trusted_profiles
            SET current_published_version_id = NULL
            WHERE trusted_profile_id = ?
            """,
            ("trusted-profile:org-default:default",),
        )
        self.lineage_store._connection.commit()

        with patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[self._make_labor_record(raw_description="Repaired profile labor line")],
        ):
            result = service.create_processing_run(self.source_document_path)

        repaired_profile = self.lineage_store.get_trusted_profile("trusted-profile:org-default:default")
        persisted_versions = self.lineage_store.list_trusted_profile_versions(repaired_profile.trusted_profile_id)

        self.assertEqual(len(persisted_versions), 1)
        self.assertEqual(
            repaired_profile.current_published_version_id,
            initial_result[2].trusted_profile_version_id,
        )
        self.assertEqual(
            result.processing_run.trusted_profile_version_id,
            initial_result[2].trusted_profile_version_id,
        )

    def test_processing_run_captures_unmapped_labor_observation_without_changing_run_snapshot(self) -> None:
        service = self._build_service()
        parsed_record = self._make_unmapped_labor_record(raw_description="Labor line", union_code="104", labor_class_raw="EO")

        with patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[parsed_record],
        ):
            first_result = service.create_processing_run(self.source_document_path)
            second_result = service.create_processing_run(self.source_document_path)

        observations = self.lineage_store.list_trusted_profile_observations(first_result.trusted_profile.trusted_profile_id)
        draft = self.lineage_store.get_open_trusted_profile_draft(first_result.trusted_profile.trusted_profile_id)

        self.assertEqual(first_result.processing_run.trusted_profile_version_id, second_result.processing_run.trusted_profile_version_id)
        self.assertEqual(first_result.profile_snapshot.profile_snapshot_id, second_result.profile_snapshot.profile_snapshot_id)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].canonical_raw_key, "104/EO")
        self.assertEqual(observations[0].first_seen_processing_run_id, first_result.processing_run.processing_run_id)
        self.assertEqual(observations[0].last_seen_processing_run_id, second_result.processing_run.processing_run_id)
        self.assertIn(
            {"raw_value": "104/EO", "target_classification": "", "notes": "", "is_observed": True},
            draft.bundle_payload["behavioral_bundle"]["labor_mapping"]["saved_mappings"],
        )

    def test_processing_run_captures_unmapped_equipment_observation_without_duplicating_draft_row(self) -> None:
        service = self._build_service()
        parsed_record = self._make_unmapped_equipment_record(raw_description="627/2025 crane truck")

        with patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[parsed_record],
        ):
            service.create_processing_run(self.source_document_path)
            service.create_processing_run(self.source_document_path)

        trusted_profile = self.lineage_store.get_trusted_profile("trusted-profile:org-default:default")
        observations = self.lineage_store.list_trusted_profile_observations(trusted_profile.trusted_profile_id)
        draft = self.lineage_store.get_open_trusted_profile_draft(trusted_profile.trusted_profile_id)
        saved_rows = draft.bundle_payload["behavioral_bundle"]["equipment_mapping"]["saved_mappings"]

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].canonical_raw_key, "CRANE TRUCK")
        self.assertEqual(
            len([row for row in saved_rows if row["raw_description"] == "CRANE TRUCK"]),
            1,
        )
        self.assertEqual(saved_rows[0]["is_observed"], True)

    def _build_service(self) -> ProcessingRunService:
        return ProcessingRunService(
            lineage_store=self.lineage_store,
            profile_manager=self.profile_manager,
            engine_version="engine-1",
            now_provider=lambda: self.created_at,
        )

    def _write_profile_bundle(
        self,
        *,
        profile_name: str,
        display_name: str,
        description: str,
        version: str,
        labor_target: str,
    ) -> None:
        profile_dir = TEST_ROOT / "profiles" / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            profile_dir / "profile.json",
            {
                "profile_name": profile_name,
                "display_name": display_name,
                "description": description,
                "version": version,
                "template_filename": "recap_template.xlsx",
                "is_active": False,
            },
        )
        self._write_json(
            profile_dir / "labor_mapping.json",
            {
                "raw_mappings": {"103/J": labor_target},
                "saved_mappings": [
                    {
                        "raw_value": "103/J",
                        "target_classification": labor_target,
                        "notes": "",
                    }
                ],
            },
        )
        self._write_json(
            profile_dir / "equipment_mapping.json",
            {"raw_mappings": {}, "saved_mappings": []},
        )
        self._write_json(profile_dir / "phase_mapping.json", {"20": "LABOR"})
        self._write_json(profile_dir / "vendor_normalization.json", {})
        self._write_json(
            profile_dir / "input_model.json",
            {"report_type": "vista_job_cost", "section_headers": {}},
        )
        self._write_json(
            profile_dir / "target_labor_classifications.json",
            {"classifications": [labor_target]},
        )
        self._write_json(
            profile_dir / "target_equipment_classifications.json",
            {"classifications": ["Pick-up Truck"]},
        )
        self._write_json(
            profile_dir / "rates.json",
            {"labor_rates": {}, "equipment_rates": {}},
        )
        self._write_json(
            profile_dir / "review_rules.json",
            {"default_omit_rules": []},
        )
        self._write_json(
            profile_dir / "recap_template_map.json",
            {
                "worksheet_name": "Recap",
                "header_fields": {},
                "labor_rows": {"Labor 1": {"hours": "A1", "rate": "B1", "amount": "C1"}},
                "equipment_rows": {"Equipment 1": {"hours": "D1", "rate": "E1", "amount": "F1"}},
                "materials_section": {"start_row": 1, "end_row": 1, "columns": {"name": "A", "amount": "B"}},
                "subcontractors_section": {
                    "start_row": 1,
                    "end_row": 1,
                    "columns": {"name": "A", "description": "B", "amount": "C"},
                },
                "permits_fees_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
                "police_detail_section": {"start_row": 1, "end_row": 1, "columns": {"description": "A", "amount": "B"}},
            },
        )
        (profile_dir / "recap_template.xlsx").write_bytes(b"template")

    def _clone_profile(
        self,
        *,
        source_profile_name: str,
        profile_name: str,
        display_name: str,
        description: str,
        version: str,
        labor_target: str,
    ) -> None:
        source_dir = TEST_ROOT / "profiles" / source_profile_name
        target_dir = TEST_ROOT / "profiles" / profile_name
        shutil.copytree(source_dir, target_dir)
        self._write_profile_bundle(
            profile_name=profile_name,
            display_name=display_name,
            description=description,
            version=version,
            labor_target=labor_target,
        )

    def _make_labor_record(self, *, raw_description: str) -> Record:
        return Record(
            record_type="labor",
            phase_code="20",
            raw_description=raw_description,
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code="103",
            labor_class_raw="J",
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=[],
            source_page=1,
            source_line_text="line one",
            record_type_normalized=None,
        )

    def _make_unmapped_labor_record(
        self,
        *,
        raw_description: str,
        union_code: str,
        labor_class_raw: str,
    ) -> Record:
        return Record(
            record_type="labor",
            phase_code="20",
            raw_description=raw_description,
            cost=100.0,
            hours=8.0,
            hour_type="ST",
            union_code=union_code,
            labor_class_raw=labor_class_raw,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=None,
            equipment_category=None,
            confidence=0.9,
            warnings=["Labor raw value is not mapped."],
            source_page=1,
            source_line_text="line one",
            record_type_normalized="labor",
        )

    def _make_unmapped_equipment_record(self, *, raw_description: str) -> Record:
        return Record(
            record_type="equipment",
            phase_code=None,
            raw_description=raw_description,
            cost=100.0,
            hours=8.0,
            hour_type=None,
            union_code=None,
            labor_class_raw=None,
            labor_class_normalized=None,
            vendor_name=None,
            equipment_description=raw_description,
            equipment_category=None,
            confidence=0.9,
            warnings=["Equipment raw value is not mapped."],
            source_page=1,
            source_line_text="line one",
            record_type_normalized="equipment",
            equipment_mapping_key="CRANE TRUCK",
        )

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
