"""Service tests for Phase 2A profile authoring behavior."""

from __future__ import annotations

import json
import shutil
import unittest
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from core.config import ConfigLoader, ProfileManager
from core.models import Record
from infrastructure.persistence import SqliteLineageStore
from infrastructure.storage import LocalRuntimeFileStore
from services.processing_run_service import ProcessingRunService
from services.profile_authoring_errors import ProfileAuthoringConflictError
from services.profile_authoring_service import ProfileAuthoringService
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository


TEST_ROOT = Path("tests/_profile_authoring_tmp")


class ProfileAuthoringServiceTests(unittest.TestCase):
    """Verify draft lifecycle, helper-backed edits, and immutable publish behavior."""

    def setUp(self) -> None:
        ConfigLoader.clear_runtime_caches()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        (TEST_ROOT / "profiles" / "default").mkdir(parents=True, exist_ok=True)
        (TEST_ROOT / "legacy_config").mkdir(parents=True, exist_ok=True)
        self.settings_path = TEST_ROOT / "app_settings.json"
        self.created_at = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
        self.source_document_path = TEST_ROOT / "sample_report.pdf"
        self.source_document_path.write_bytes(b"sample pdf bytes")

        self._write_profile_bundle(
            profile_name="default",
            display_name="Default Profile",
            description="Default profile",
            version="1.0",
            labor_target="Default Journeyman",
        )
        self._write_json(self.settings_path, {"active_profile": "default"})
        self._write_json(
            TEST_ROOT / "legacy_config" / "phase_catalog.json",
            {"phases": [{"phase_code": "20", "phase_name": "Labor"}]},
        )

        self.profile_manager = ProfileManager(
            profiles_root=TEST_ROOT / "profiles",
            settings_path=self.settings_path,
            legacy_config_root=TEST_ROOT / "legacy_config",
        )
        self.lineage_store = SqliteLineageStore()
        self.repository = TrustedProfileAuthoringRepository(
            lineage_store=self.lineage_store,
            profile_manager=self.profile_manager,
            now_provider=lambda: self.created_at,
        )
        self.artifact_store = LocalRuntimeFileStore(
            upload_root=TEST_ROOT / "runtime" / "uploads",
            export_root=TEST_ROOT / "runtime" / "exports",
        )
        self.service = ProfileAuthoringService(
            repository=self.repository,
            profile_manager=self.profile_manager,
            artifact_store=self.artifact_store,
            now_provider=lambda: self.created_at,
        )
        self.processing_run_service = ProcessingRunService(
            lineage_store=self.lineage_store,
            profile_manager=self.profile_manager,
            engine_version="engine-1",
            now_provider=lambda: self.created_at,
        )

    def tearDown(self) -> None:
        self.lineage_store.close()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        ConfigLoader.clear_runtime_caches()

    def test_get_profile_detail_returns_current_published_version_and_deferred_domains(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"

        detail = self.service.get_profile_detail(trusted_profile_id)

        self.assertEqual(detail.profile_name, "default")
        self.assertEqual(detail.current_published_version_number, 1)
        self.assertEqual(detail.template_artifact_ref, "recap_template.xlsx")
        self.assertIn("phase_mapping", detail.deferred_domains)
        self.assertIsNone(detail.open_draft_id)

    def test_create_or_open_draft_returns_editor_state_for_phase_2a_domains(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"

        first_state = self.service.create_or_open_draft(trusted_profile_id)
        second_state = self.service.create_or_open_draft(trusted_profile_id)

        self.assertEqual(first_state.trusted_profile_draft_id, second_state.trusted_profile_draft_id)
        self.assertEqual(first_state.current_published_version_number, 1)
        self.assertEqual(first_state.default_omit_phase_options[0]["phase_code"], "20")
        self.assertEqual(first_state.labor_mappings[0]["target_classification"], "Default Journeyman")
        self.assertEqual(first_state.labor_slots[0]["slot_id"], "labor_1")
        self.assertEqual(first_state.validation_errors, [])

    def test_create_trusted_profile_seeds_second_profile_and_keeps_default_profile_independent(self) -> None:
        default_profile_id = "trusted-profile:org-default:default"
        default_detail = self.service.get_profile_detail(default_profile_id)

        created_detail = self.service.create_trusted_profile(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile_id,
        )
        draft_state = self.service.create_or_open_draft(created_detail.trusted_profile_id)
        self.service.update_default_omit_rules(
            draft_state.trusted_profile_draft_id,
            [{"phase_code": "20", "phase_name": "Labor"}],
        )
        published_detail = self.service.publish_draft(draft_state.trusted_profile_draft_id)
        default_after = self.service.get_profile_detail(default_profile_id)

        self.assertEqual(created_detail.profile_name, "field-team")
        self.assertEqual(created_detail.current_published_version_number, 1)
        self.assertEqual(draft_state.current_published_version_number, 1)
        self.assertEqual(published_detail.current_published_version_number, 2)
        self.assertEqual(
            self.repository.get_current_published_version(created_detail.trusted_profile_id).version_number,
            2,
        )
        self.assertEqual(
            self.repository.get_current_published_version(default_profile_id).version_number,
            default_detail.current_published_version_number,
        )
        self.assertEqual(default_after.current_published_version_id, default_detail.current_published_version_id)
        self.assertEqual(default_after.open_draft_id, default_detail.open_draft_id)

    def test_create_trusted_profile_rejects_duplicate_key_and_duplicate_active_display_name(self) -> None:
        default_profile_id = "trusted-profile:org-default:default"
        self.service.create_trusted_profile(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile_id,
        )

        with self.assertRaises(ProfileAuthoringConflictError):
            self.service.create_trusted_profile(
                profile_name="FIELD-TEAM",
                display_name="Different Display",
                description="Duplicate key differing only by case",
                seed_trusted_profile_id=default_profile_id,
            )

        with self.assertRaises(ProfileAuthoringConflictError):
            self.service.create_trusted_profile(
                profile_name="field-team-2",
                display_name="Field Team",
                description="Duplicate display name",
                seed_trusted_profile_id=default_profile_id,
            )

    def test_archive_trusted_profile_hides_user_created_profile_and_preserves_published_version(self) -> None:
        default_profile_id = "trusted-profile:org-default:default"
        created_detail = self.service.create_trusted_profile(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile_id,
        )

        self.service.archive_trusted_profile(created_detail.trusted_profile_id)

        active_profiles = {profile.profile_name for profile in self.repository.list_trusted_profiles()}
        archived_profile = self.repository.get_trusted_profile(created_detail.trusted_profile_id)

        self.assertNotIn("field-team", active_profiles)
        self.assertIsNotNone(archived_profile.archived_at)
        self.assertEqual(
            self.repository.get_current_published_version(created_detail.trusted_profile_id).version_number,
            1,
        )
        with self.assertRaises(ValueError):
            self.service.create_or_open_draft(created_detail.trusted_profile_id)

    def test_unarchive_trusted_profile_restores_archived_profile_to_active_listing(self) -> None:
        default_profile_id = "trusted-profile:org-default:default"
        created_detail = self.service.create_trusted_profile(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile_id,
        )
        self.service.archive_trusted_profile(created_detail.trusted_profile_id)

        self.service.unarchive_trusted_profile(created_detail.trusted_profile_id)

        active_profiles = {profile.profile_name for profile in self.repository.list_trusted_profiles()}
        restored_profile = self.repository.get_trusted_profile(created_detail.trusted_profile_id)

        self.assertIn("field-team", active_profiles)
        self.assertIsNone(restored_profile.archived_at)

    def test_unarchive_trusted_profile_rejects_display_name_conflict_with_active_profile(self) -> None:
        default_profile_id = "trusted-profile:org-default:default"
        created_detail = self.service.create_trusted_profile(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile_id,
        )
        self.service.archive_trusted_profile(created_detail.trusted_profile_id)
        self.service.create_trusted_profile(
            profile_name="field-team-2",
            display_name="Field Team",
            description="Replacement trusted profile",
            seed_trusted_profile_id=default_profile_id,
        )

        with self.assertRaises(ProfileAuthoringConflictError):
            self.service.unarchive_trusted_profile(created_detail.trusted_profile_id)

    def test_update_classifications_propagates_mapping_rate_and_recap_targets(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        draft_state = self.service.create_or_open_draft(trusted_profile_id)

        updated_state = self.service.update_classifications(
            draft_state.trusted_profile_draft_id,
            labor_slots=[
                {"slot_id": "labor_1", "label": "Updated Journeyman", "active": True},
            ],
            equipment_slots=draft_state.equipment_slots,
        )

        self.assertEqual(updated_state.labor_slots[0]["label"], "Updated Journeyman")
        self.assertEqual(updated_state.labor_mappings[0]["target_classification"], "Updated Journeyman")
        self.assertEqual(updated_state.labor_rates[0]["classification"], "Updated Journeyman")
        self.assertIn(
            "Updated Journeyman",
            updated_state.deferred_domains["recap_template_map"]["labor_rows"],
        )

    def test_publish_creates_new_version_updates_current_pointer_and_preserves_prior_version(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        original_detail = self.service.get_profile_detail(trusted_profile_id)
        draft_state = self.service.create_or_open_draft(trusted_profile_id)

        self.service.update_default_omit_rules(
            draft_state.trusted_profile_draft_id,
            [{"phase_code": "20", "phase_name": "Labor"}],
        )
        published_detail = self.service.publish_draft(draft_state.trusted_profile_draft_id)

        versions = self.lineage_store.list_trusted_profile_versions(trusted_profile_id)
        previous_version = self.lineage_store.get_trusted_profile_version(
            original_detail.current_published_version_id
        )
        current_profile = self.lineage_store.get_trusted_profile(trusted_profile_id)

        self.assertEqual(len(versions), 2)
        self.assertNotEqual(
            published_detail.current_published_version_id,
            original_detail.current_published_version_id,
        )
        self.assertEqual(
            current_profile.current_published_version_id,
            published_detail.current_published_version_id,
        )
        self.assertEqual(previous_version.version_number, 1)
        self.assertEqual(previous_version.bundle_payload["behavioral_bundle"]["review_rules"]["default_omit_rules"], [])
        with self.assertRaises(KeyError):
            self.repository.get_draft(draft_state.trusted_profile_draft_id)

    def test_discard_draft_removes_open_draft_without_changing_current_published_version(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        original_detail = self.service.get_profile_detail(trusted_profile_id)
        draft_state = self.service.create_or_open_draft(trusted_profile_id)

        self.service.discard_draft(draft_state.trusted_profile_draft_id)

        refreshed_detail = self.service.get_profile_detail(trusted_profile_id)

        self.assertEqual(
            refreshed_detail.current_published_version_id,
            original_detail.current_published_version_id,
        )
        self.assertEqual(
            refreshed_detail.current_published_version_number,
            original_detail.current_published_version_number,
        )
        self.assertIsNone(refreshed_detail.open_draft_id)
        with self.assertRaises(KeyError):
            self.repository.get_draft(draft_state.trusted_profile_draft_id)

    def test_draft_changes_do_not_affect_processing_until_publish(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        draft_state = self.service.create_or_open_draft(trusted_profile_id)
        self.service.update_classifications(
            draft_state.trusted_profile_draft_id,
            labor_slots=[
                {"slot_id": "labor_1", "label": "Published Later Journeyman", "active": True},
            ],
            equipment_slots=draft_state.equipment_slots,
        )
        parsed_record = self._make_labor_record(raw_description="Line item")

        with patch("services.review_workflow_service.parse_pdf", return_value=[parsed_record]):
            before_publish = self.processing_run_service.create_processing_run(self.source_document_path)

        self.assertEqual(
            before_publish.run_records[0].canonical_record["recap_labor_classification"],
            "Default Journeyman",
        )

        self.service.publish_draft(draft_state.trusted_profile_draft_id)

        with patch("services.review_workflow_service.parse_pdf", return_value=[parsed_record]):
            after_publish = self.processing_run_service.create_processing_run(self.source_document_path)

        self.assertEqual(
            after_publish.run_records[0].canonical_record["recap_labor_classification"],
            "Published Later Journeyman",
        )
        self.assertNotEqual(
            before_publish.processing_run.trusted_profile_version_id,
            after_publish.processing_run.trusted_profile_version_id,
        )

    def test_unresolved_labor_observation_creates_draft_and_merges_one_blank_observed_row(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        published_before = self.repository.get_current_published_version(trusted_profile_id)
        processing_run_id = self._create_reference_processing_run_id()

        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=processing_run_id,
            records=[self._make_unmapped_labor_record(raw_description="Labor line", union_code="104", labor_class_raw="EO")],
        )

        draft = self.repository.get_open_draft(trusted_profile_id)
        draft_state = self.service.get_draft_state(draft.trusted_profile_draft_id)
        observations = self.repository.list_observations(trusted_profile_id)
        published_after = self.repository.get_current_published_version(trusted_profile_id)

        self.assertEqual(published_before.bundle_payload, published_after.bundle_payload)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].canonical_raw_key, "104/EO")
        self.assertIsNotNone(observations[0].draft_applied_at)
        self.assertIn(
            {
                "raw_value": "104/EO",
                "target_classification": "",
                "notes": "",
                "is_observed": True,
                "is_required_for_recent_processing": True,
            },
            draft_state.labor_mappings,
        )

    def test_repeated_same_observation_does_not_duplicate_draft_rows(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        record = self._make_unmapped_labor_record(raw_description="Labor line", union_code="104", labor_class_raw="EO")
        first_processing_run_id = self._create_reference_processing_run_id()
        second_processing_run_id = self._create_reference_processing_run_id()

        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=first_processing_run_id,
            records=[record],
        )
        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=second_processing_run_id,
            records=[record],
        )

        draft = self.repository.get_open_draft(trusted_profile_id)
        draft_state = self.service.get_draft_state(draft.trusted_profile_draft_id)
        observations = self.repository.list_observations(
            trusted_profile_id,
            observation_domain="labor_mapping",
        )

        self.assertEqual(len([row for row in draft_state.labor_mappings if row["raw_value"] == "104/EO"]), 1)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].first_seen_processing_run_id, first_processing_run_id)
        self.assertEqual(observations[0].last_seen_processing_run_id, second_processing_run_id)

    def test_published_mapping_prevents_observation_draft_merge(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        processing_run_id = self._create_reference_processing_run_id()

        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=processing_run_id,
            records=[self._make_unmapped_labor_record(raw_description="Labor line", union_code="103", labor_class_raw="J")],
        )

        observations = self.repository.list_observations(
            trusted_profile_id,
            observation_domain="labor_mapping",
        )

        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].is_resolved)
        with self.assertRaises(KeyError):
            self.repository.get_open_draft(trusted_profile_id)

    def test_observation_after_publish_creates_fresh_draft_from_current_published_version(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        initial_draft = self.service.create_or_open_draft(trusted_profile_id)
        self.service.publish_draft(initial_draft.trusted_profile_draft_id)
        processing_run_id = self._create_reference_processing_run_id()

        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=processing_run_id,
            records=[self._make_unmapped_equipment_record(raw_description="627/2025 crane truck")],
        )

        new_draft = self.repository.get_open_draft(trusted_profile_id)
        draft_state = self.service.get_draft_state(new_draft.trusted_profile_draft_id)

        self.assertEqual(
            new_draft.base_trusted_profile_version_id,
            self.repository.get_current_published_version(trusted_profile_id).trusted_profile_version_id,
        )
        self.assertIn(
            {
                "raw_description": "CRANE TRUCK",
                "raw_pattern": "CRANE TRUCK",
                "target_category": "",
                "is_observed": True,
                "is_required_for_recent_processing": True,
            },
            draft_state.equipment_mappings,
        )

    def test_unmapped_equipment_rows_surface_required_priority_and_prediction_metadata(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        processing_run_id = self._create_reference_processing_run_id()

        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=processing_run_id,
            records=[self._make_unmapped_equipment_record(raw_description="pickup")],
        )

        draft = self.repository.get_open_draft(trusted_profile_id)
        draft_state = self.service.get_draft_state(draft.trusted_profile_draft_id)
        predicted_row = next(
            row for row in draft_state.equipment_mappings if row["raw_description"] == "PICKUP"
        )

        self.assertTrue(predicted_row["is_observed"])
        self.assertTrue(predicted_row["is_required_for_recent_processing"])
        self.assertEqual(predicted_row["prediction_target"], "Pick-up Truck")
        self.assertEqual(predicted_row["prediction_confidence_label"], "Likely match")

    def test_discard_draft_preserves_observations_and_future_processing_can_recreate_it(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        first_processing_run_id = self._create_reference_processing_run_id()
        record = self._make_unmapped_labor_record(
            raw_description="Labor line",
            union_code="104",
            labor_class_raw="EO",
        )

        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=first_processing_run_id,
            records=[record],
        )
        initial_draft = self.repository.get_open_draft(trusted_profile_id)

        self.service.discard_draft(initial_draft.trusted_profile_draft_id)

        observations_after_discard = self.repository.list_observations(
            trusted_profile_id,
            observation_domain="labor_mapping",
        )
        self.assertEqual(len(observations_after_discard), 1)
        self.assertFalse(observations_after_discard[0].is_resolved)
        with self.assertRaises(KeyError):
            self.repository.get_open_draft(trusted_profile_id)

        second_processing_run_id = self._create_reference_processing_run_id()
        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=second_processing_run_id,
            records=[record],
        )

        recreated_draft = self.repository.get_open_draft(trusted_profile_id)
        recreated_state = self.service.get_draft_state(recreated_draft.trusted_profile_draft_id)

        self.assertEqual(recreated_draft.trusted_profile_draft_id, initial_draft.trusted_profile_draft_id)
        self.assertIn(
            {
                "raw_value": "104/EO",
                "target_classification": "",
                "notes": "",
                "is_observed": True,
                "is_required_for_recent_processing": True,
            },
            recreated_state.labor_mappings,
        )

    def test_future_observations_do_not_recreate_blank_row_after_mapping_is_published(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        first_processing_run_id = self._create_reference_processing_run_id()
        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=first_processing_run_id,
            records=[self._make_unmapped_labor_record(raw_description="Labor line", union_code="104", labor_class_raw="EO")],
        )
        draft = self.repository.get_open_draft(trusted_profile_id)
        self.service.update_labor_mappings(
            draft.trusted_profile_draft_id,
            [
                {
                    "raw_value": "103/J",
                    "target_classification": "Default Journeyman",
                    "notes": "",
                },
                {
                    "raw_value": "104/EO",
                    "target_classification": "Default Journeyman",
                    "notes": "resolved",
                    "is_observed": True,
                },
            ],
        )
        self.service.publish_draft(draft.trusted_profile_draft_id)

        second_processing_run_id = self._create_reference_processing_run_id()
        self.service.capture_unmapped_observations(
            trusted_profile_id,
            processing_run_id=second_processing_run_id,
            records=[self._make_unmapped_labor_record(raw_description="Labor line", union_code="104", labor_class_raw="EO")],
        )

        observations = self.repository.list_observations(
            trusted_profile_id,
            observation_domain="labor_mapping",
        )
        current_version = self.repository.get_current_published_version(trusted_profile_id)

        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0].is_resolved)
        self.assertEqual(
            current_version.bundle_payload["behavioral_bundle"]["labor_mapping"]["raw_mappings"]["104/EO"],
            "Default Journeyman",
        )
        with self.assertRaises(KeyError):
            self.repository.get_open_draft(trusted_profile_id)

    def test_create_desktop_sync_export_builds_archive_from_exact_published_version_and_manifest(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        draft_state = self.service.create_or_open_draft(trusted_profile_id)
        self.service.update_default_omit_rules(
            draft_state.trusted_profile_draft_id,
            [{"phase_code": "20", "phase_name": "Labor"}],
        )
        published_detail = self.service.publish_draft(draft_state.trusted_profile_draft_id)

        export_result = self.service.create_desktop_sync_export(published_detail.current_published_version_id)

        self.assertEqual(export_result.archive_filename, "default__v2.zip")
        self.assertTrue(export_result.stored_artifact.file_path.is_file())

        with zipfile.ZipFile(BytesIO(export_result.stored_artifact.file_path.read_bytes())) as archive:
            names = set(archive.namelist())
            self.assertIn("default__v2/profile.json", names)
            self.assertIn("default__v2/review_rules.json", names)
            self.assertIn("default__v2/recap_template.xlsx", names)
            self.assertIn("default__v2/manifest.json", names)

            manifest = json.loads(archive.read("default__v2/manifest.json").decode("utf-8"))
            review_rules = json.loads(archive.read("default__v2/review_rules.json").decode("utf-8"))
            template_bytes = archive.read("default__v2/recap_template.xlsx")

        self.assertEqual(manifest["trusted_profile_version_id"], published_detail.current_published_version_id)
        self.assertEqual(manifest["version_number"], 2)
        self.assertEqual(manifest["profile_name"], "default")
        self.assertEqual(manifest["display_name"], "Default Profile")
        self.assertEqual(manifest["content_hash"], published_detail.current_published_content_hash)
        self.assertEqual(manifest["template_file_hash"], published_detail.template_file_hash)
        self.assertEqual(manifest["template_artifact_ref"], "recap_template.xlsx")
        self.assertEqual(review_rules["default_omit_rules"], [{"phase_code": "20"}])
        self.assertEqual(template_bytes, b"template")

    def test_create_desktop_sync_export_fails_when_template_artifact_identity_is_missing(self) -> None:
        trusted_profile_id = "trusted-profile:org-default:default"
        current_version = self.repository.get_current_published_version(trusted_profile_id)
        self.lineage_store._connection.execute(
            """
            UPDATE trusted_profile_versions
            SET template_artifact_id = NULL
            WHERE trusted_profile_version_id = ?
            """,
            (current_version.trusted_profile_version_id,),
        )
        self.lineage_store._connection.commit()

        with self.assertRaises(FileNotFoundError):
            self.service.create_desktop_sync_export(current_version.trusted_profile_version_id)

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
                    {"raw_value": "103/J", "target_classification": labor_target, "notes": ""},
                ],
            },
        )
        self._write_json(
            profile_dir / "equipment_mapping.json",
            {"raw_mappings": {"pickup truck": "Pick-up Truck"}, "saved_mappings": [{"raw_description": "pickup truck", "target_category": "Pick-up Truck"}]},
        )
        self._write_json(profile_dir / "phase_mapping.json", {"20": "LABOR"})
        self._write_json(profile_dir / "vendor_normalization.json", {})
        self._write_json(profile_dir / "input_model.json", {"report_type": "vista_job_cost", "section_headers": {}})
        self._write_json(
            profile_dir / "target_labor_classifications.json",
            {
                "slots": [{"slot_id": "labor_1", "label": labor_target, "active": True}],
                "classifications": [labor_target],
            },
        )
        self._write_json(
            profile_dir / "target_equipment_classifications.json",
            {
                "slots": [{"slot_id": "equipment_1", "label": "Pick-up Truck", "active": True}],
                "classifications": ["Pick-up Truck"],
            },
        )
        self._write_json(
            profile_dir / "rates.json",
            {
                "labor_rates": {
                    labor_target: {
                        "standard_rate": 100.0,
                    }
                },
                "equipment_rates": {"Pick-up Truck": {"rate": 75.0}},
            },
        )
        self._write_json(profile_dir / "review_rules.json", {"default_omit_rules": []})
        self._write_json(
            profile_dir / "recap_template_map.json",
            {
                "worksheet_name": "Recap",
                "header_fields": {},
                "labor_rows": {labor_target: {"hours": "A1", "rate": "B1", "amount": "C1"}},
                "equipment_rows": {"Pick-up Truck": {"hours": "D1", "rate": "E1", "amount": "F1"}},
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
            recap_labor_classification=None,
        )

    def _make_unmapped_equipment_record(self, *, raw_description: str) -> Record:
        return Record(
            record_type="equipment",
            phase_code="20",
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
            equipment_mapping_key="CRANE TRUCK" if "crane truck" in raw_description.lower() else None,
        )

    def _create_reference_processing_run_id(self) -> str:
        with patch(
            "services.review_workflow_service.parse_pdf",
            return_value=[self._make_labor_record(raw_description="Reference line")],
        ):
            result = self.processing_run_service.create_processing_run(self.source_document_path)
        return result.processing_run.processing_run_id

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
