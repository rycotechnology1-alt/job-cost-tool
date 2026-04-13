"""Repository tests for persisted trusted-profile versions, drafts, observations, and bootstrap."""

from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.config import ConfigLoader, ProfileManager
from core.models.lineage import TrustedProfile, TrustedProfileObservation, TrustedProfileSyncExport
from infrastructure.persistence.sqlite_lineage_store import SqliteLineageStore
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository


TEST_ROOT = Path("tests/_trusted_profile_authoring_tmp")


class TrustedProfileAuthoringRepositoryTests(unittest.TestCase):
    """Verify persisted trusted-profile authoring records and filesystem bootstrap behavior."""

    def setUp(self) -> None:
        ConfigLoader.clear_runtime_caches()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        (TEST_ROOT / "profiles" / "default").mkdir(parents=True, exist_ok=True)
        (TEST_ROOT / "profiles" / "alternate").mkdir(parents=True, exist_ok=True)
        (TEST_ROOT / "legacy_config").mkdir(parents=True, exist_ok=True)
        self.created_at = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
        self.settings_path = TEST_ROOT / "app_settings.json"

        self._write_profile_bundle(
            profile_name="default",
            display_name="Default Profile",
            description="Default profile",
            version="1.0",
            template_filename="recap_template.xlsx",
            labor_target="Default Journeyman",
            template_bytes=b"default template",
        )
        self._write_profile_bundle(
            profile_name="alternate",
            display_name="Alternate Profile",
            description="Alternate profile",
            version="2.0",
            template_filename="alternate_template.xlsx",
            labor_target="Alternate Journeyman",
            template_bytes=b"default template",
        )
        self._write_json(self.settings_path, {"active_profile": "default"})
        self._write_json(TEST_ROOT / "legacy_config" / "phase_catalog.json", {"phases": []})

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

    def tearDown(self) -> None:
        self.lineage_store.close()
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        ConfigLoader.clear_runtime_caches()

    def test_bootstrap_creates_logical_profiles_and_published_version_one(self) -> None:
        versions = self.repository.bootstrap_filesystem_profiles()
        profiles = self.repository.list_trusted_profiles()

        self.assertEqual(len(versions), 2)
        self.assertEqual([profile.profile_name for profile in profiles], ["alternate", "default"])

        default_profile = next(profile for profile in profiles if profile.profile_name == "default")
        default_version = self.repository.get_current_published_version(default_profile.trusted_profile_id)

        self.assertEqual(default_version.version_number, 1)
        self.assertEqual(default_profile.current_published_version_id, default_version.trusted_profile_version_id)
        self.assertEqual(
            default_version.bundle_payload["traceability"]["trusted_profile"]["display_name"],
            "Default Profile",
        )
        self.assertEqual(default_version.template_artifact_ref, "recap_template.xlsx")
        self.assertTrue(default_version.template_file_hash)
        self.assertEqual(
            default_version.bundle_payload["behavioral_bundle"]["template"]["template_artifact_ref"],
            "recap_template.xlsx",
        )
        self.assertEqual(
            default_version.bundle_payload["behavioral_bundle"]["template"]["template_id"],
            "recap-template",
        )
        self.assertIn("export_settings", default_version.bundle_payload["behavioral_bundle"])

    def test_bootstrap_is_idempotent_and_does_not_duplicate_equivalent_versions(self) -> None:
        first_versions = self.repository.bootstrap_filesystem_profiles()
        second_versions = self.repository.bootstrap_filesystem_profiles()

        profiles = self.repository.list_trusted_profiles()
        version_counts = {
            profile.profile_name: len(self.lineage_store.list_trusted_profile_versions(profile.trusted_profile_id))
            for profile in profiles
        }

        self.assertEqual(
            [version.trusted_profile_version_id for version in first_versions],
            [version.trusted_profile_version_id for version in second_versions],
        )
        self.assertEqual(version_counts, {"alternate": 1, "default": 1})

    def test_get_current_published_version_repairs_existing_profile_missing_linkage(self) -> None:
        organization = self.lineage_store.ensure_organization(
            organization_id="org-default",
            slug="default-org",
            display_name="Default Organization",
            created_at=self.created_at,
            is_seeded=True,
        )
        broken_profile = self.lineage_store.get_or_create_trusted_profile(
            TrustedProfile(
                trusted_profile_id="trusted-profile:org-default:default",
                organization_id=organization.organization_id,
                profile_name="default",
                display_name="Default Profile",
                source_kind="seeded",
                bundle_ref=str(TEST_ROOT / "profiles" / "default"),
                description="Default profile",
                version_label="1.0",
                created_at=self.created_at,
            )
        )

        repaired_version = self.repository.get_current_published_version(broken_profile.trusted_profile_id)
        repaired_profile = self.lineage_store.get_trusted_profile(broken_profile.trusted_profile_id)
        persisted_versions = self.lineage_store.list_trusted_profile_versions(broken_profile.trusted_profile_id)

        self.assertEqual(repaired_version.version_number, 1)
        self.assertEqual(len(persisted_versions), 1)
        self.assertEqual(
            repaired_profile.current_published_version_id,
            repaired_version.trusted_profile_version_id,
        )

    def test_get_current_published_version_reuses_equivalent_version_when_repairing_missing_linkage(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        original_version = self.repository.get_current_published_version(trusted_profile.trusted_profile_id)

        self.lineage_store._connection.execute(
            """
            UPDATE trusted_profiles
            SET current_published_version_id = NULL
            WHERE trusted_profile_id = ?
            """,
            (trusted_profile.trusted_profile_id,),
        )
        self.lineage_store._connection.commit()

        repaired_version = self.repository.get_current_published_version(trusted_profile.trusted_profile_id)
        persisted_versions = self.lineage_store.list_trusted_profile_versions(trusted_profile.trusted_profile_id)

        self.assertEqual(repaired_version.trusted_profile_version_id, original_version.trusted_profile_version_id)
        self.assertEqual(len(persisted_versions), 1)

    def test_template_identity_participates_in_published_version_hash(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        profiles = {profile.profile_name: profile for profile in self.repository.list_trusted_profiles()}

        default_version = self.repository.get_current_published_version(profiles["default"].trusted_profile_id)
        alternate_version = self.repository.get_current_published_version(profiles["alternate"].trusted_profile_id)

        self.assertNotEqual(default_version.content_hash, alternate_version.content_hash)
        self.assertEqual(default_version.template_file_hash, alternate_version.template_file_hash)
        self.assertNotEqual(default_version.template_artifact_ref, alternate_version.template_artifact_ref)

    def test_create_open_draft_copies_current_published_version_and_reuses_single_open_draft(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        current_version = self.repository.get_current_published_version(trusted_profile.trusted_profile_id)

        first_draft = self.repository.create_open_draft(trusted_profile.trusted_profile_id)
        second_draft = self.repository.create_open_draft(trusted_profile.trusted_profile_id)

        self.assertEqual(first_draft.trusted_profile_draft_id, second_draft.trusted_profile_draft_id)
        self.assertEqual(first_draft.base_trusted_profile_version_id, current_version.trusted_profile_version_id)
        self.assertEqual(first_draft.content_hash, current_version.content_hash)
        self.assertEqual(
            first_draft.bundle_payload["behavioral_bundle"]["labor_mapping"]["raw_mappings"]["103/J"],
            "Default Journeyman",
        )

    def test_create_trusted_profile_from_published_clone_creates_second_profile_with_initial_version(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        default_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        default_version = self.repository.get_current_published_version(default_profile.trusted_profile_id)

        cloned_profile, cloned_version = self.repository.create_trusted_profile_from_published_clone(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile.trusted_profile_id,
        )
        cloned_draft = self.repository.create_open_draft(cloned_profile.trusted_profile_id)

        profiles = {profile.profile_name: profile for profile in self.repository.list_trusted_profiles()}

        self.assertIn("field-team", profiles)
        self.assertEqual(cloned_profile.source_kind, "published_clone")
        self.assertEqual(cloned_version.version_number, 1)
        self.assertEqual(cloned_version.base_trusted_profile_version_id, default_version.trusted_profile_version_id)
        self.assertEqual(cloned_profile.current_published_version_id, cloned_version.trusted_profile_version_id)
        self.assertEqual(
            cloned_version.bundle_payload["traceability"]["trusted_profile"]["profile_name"],
            "field-team",
        )
        self.assertEqual(
            cloned_version.bundle_payload["traceability"]["trusted_profile"]["display_name"],
            "Field Team",
        )
        self.assertEqual(
            cloned_version.bundle_payload["traceability"]["trusted_profile"]["description"],
            "Second trusted profile",
        )
        self.assertEqual(
            cloned_version.bundle_payload["behavioral_bundle"]["labor_mapping"]["raw_mappings"]["103/J"],
            "Default Journeyman",
        )
        self.assertEqual(cloned_draft.base_trusted_profile_version_id, cloned_version.trusted_profile_version_id)
        self.assertEqual(
            self.repository.get_current_published_version(default_profile.trusted_profile_id).trusted_profile_version_id,
            default_version.trusted_profile_version_id,
        )

    def test_archive_trusted_profile_hides_user_created_profile_from_active_list_without_deleting_versions(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        default_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        cloned_profile, cloned_version = self.repository.create_trusted_profile_from_published_clone(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile.trusted_profile_id,
        )

        archived_profile = self.repository.archive_trusted_profile(cloned_profile.trusted_profile_id)
        active_profiles = {profile.profile_name for profile in self.repository.list_trusted_profiles()}
        all_profiles = {profile.profile_name for profile in self.repository.list_trusted_profiles(include_archived=True)}

        self.assertIsNotNone(archived_profile.archived_at)
        self.assertNotIn("field-team", active_profiles)
        self.assertIn("field-team", all_profiles)
        self.assertEqual(
            self.repository.get_current_published_version(cloned_profile.trusted_profile_id).trusted_profile_version_id,
            cloned_version.trusted_profile_version_id,
        )
        with self.assertRaises(ValueError):
            self.repository.resolve_current_published_profile("field-team")

    def test_unarchive_trusted_profile_restores_user_created_profile_to_active_list(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        default_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        cloned_profile, cloned_version = self.repository.create_trusted_profile_from_published_clone(
            profile_name="field-team",
            display_name="Field Team",
            description="Second trusted profile",
            seed_trusted_profile_id=default_profile.trusted_profile_id,
        )

        self.repository.archive_trusted_profile(cloned_profile.trusted_profile_id)
        restored_profile = self.repository.unarchive_trusted_profile(cloned_profile.trusted_profile_id)

        active_profiles = {profile.profile_name for profile in self.repository.list_trusted_profiles()}

        self.assertIsNone(restored_profile.archived_at)
        self.assertIn("field-team", active_profiles)
        self.assertEqual(
            self.repository.get_current_published_version(cloned_profile.trusted_profile_id).trusted_profile_version_id,
            cloned_version.trusted_profile_version_id,
        )

    def test_resolve_current_published_profile_reuses_persisted_version_without_refreshing_from_filesystem(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        initial_resolution = self.repository.resolve_current_published_profile("default")

        self._write_json(
            TEST_ROOT / "profiles" / "default" / "labor_mapping.json",
            {
                "raw_mappings": {"103/J": "Filesystem Changed Journeyman"},
                "saved_mappings": [
                    {
                        "raw_value": "103/J",
                        "target_classification": "Filesystem Changed Journeyman",
                        "notes": "",
                    }
                ],
            },
        )

        resolved_again = self.repository.resolve_current_published_profile("default")
        persisted_versions = self.lineage_store.list_trusted_profile_versions(
            initial_resolution.trusted_profile.trusted_profile_id
        )

        self.assertEqual(
            initial_resolution.trusted_profile_version.trusted_profile_version_id,
            resolved_again.trusted_profile_version.trusted_profile_version_id,
        )
        self.assertEqual(
            resolved_again.trusted_profile_version.bundle_payload["behavioral_bundle"]["labor_mapping"]["raw_mappings"]["103/J"],
            "Default Journeyman",
        )
        self.assertEqual(len(persisted_versions), 1)

    def test_materialize_published_version_bundle_writes_processing_bundle_from_persistence(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        current_version = self.repository.get_current_published_version(trusted_profile.trusted_profile_id)

        with self.repository.materialize_published_version_bundle(current_version) as materialized_dir:
            labor_mapping = json.loads((materialized_dir / "labor_mapping.json").read_text(encoding="utf-8"))
            profile_metadata = json.loads((materialized_dir / "profile.json").read_text(encoding="utf-8"))
            template_metadata = json.loads((materialized_dir / "template_metadata.json").read_text(encoding="utf-8"))
            export_settings = json.loads((materialized_dir / "export_settings.json").read_text(encoding="utf-8"))

            self.assertEqual(labor_mapping["raw_mappings"]["103/J"], "Default Journeyman")
            self.assertEqual(profile_metadata["template_filename"], "recap_template.xlsx")
            self.assertEqual(template_metadata["template_id"], "recap-template")
            self.assertIn("labor_minimum_hours", export_settings)
            self.assertTrue((materialized_dir / "recap_template.xlsx").is_file())

    def test_observation_upsert_is_idempotent_and_updates_last_seen_state(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )

        first_observation = self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="observation-1",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="labor_mapping",
                canonical_raw_key="103/J",
                raw_display_value="103/J",
                first_seen_at=self.created_at,
                last_seen_at=self.created_at,
            )
        )
        second_observation = self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="observation-2",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="labor_mapping",
                canonical_raw_key="103/J",
                raw_display_value="103/J",
                first_seen_at=self.created_at,
                last_seen_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
                is_resolved=True,
            )
        )

        observations = self.lineage_store.list_trusted_profile_observations(trusted_profile.trusted_profile_id)
        self.assertEqual(len(observations), 1)
        self.assertEqual(first_observation.trusted_profile_observation_id, second_observation.trusted_profile_observation_id)
        self.assertIsNone(second_observation.last_seen_processing_run_id)
        self.assertTrue(second_observation.is_resolved)

    def test_equipment_observation_upsert_reuses_one_row_per_canonical_key(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )

        first_observation = self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="equipment-observation-1",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="equipment_mapping",
                canonical_raw_key="FORD TRANSIT VAN",
                raw_display_value="FORD TRANSIT VAN",
                first_seen_at=self.created_at,
                last_seen_at=self.created_at,
            )
        )
        second_observation = self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="equipment-observation-2",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="equipment_mapping",
                canonical_raw_key="FORD TRANSIT VAN",
                raw_display_value="FORD TRANSIT VAN",
                first_seen_at=self.created_at,
                last_seen_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
            )
        )

        persisted = self.repository.get_observation(
            trusted_profile.trusted_profile_id,
            "equipment_mapping",
            "FORD TRANSIT VAN",
        )

        self.assertEqual(first_observation.trusted_profile_observation_id, second_observation.trusted_profile_observation_id)
        self.assertIsNone(persisted.first_seen_processing_run_id)
        self.assertIsNone(persisted.last_seen_processing_run_id)
        self.assertEqual(
            self.repository.list_observations(
                trusted_profile.trusted_profile_id,
                observation_domain="equipment_mapping",
            )[0].canonical_raw_key,
            "FORD TRANSIT VAN",
        )

    def test_list_observations_can_filter_to_unresolved_and_unmerged_rows(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )

        self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="observation-unmerged",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="labor_mapping",
                canonical_raw_key="104/EO",
                raw_display_value="104/EO",
                first_seen_at=self.created_at,
                last_seen_at=self.created_at,
            )
        )
        self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="observation-merged",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="equipment_mapping",
                canonical_raw_key="CRANE TRUCK",
                raw_display_value="CRANE TRUCK",
                first_seen_at=self.created_at,
                last_seen_at=self.created_at,
                draft_applied_at=self.created_at,
            )
        )
        self.repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id="observation-resolved",
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                observation_domain="equipment_mapping",
                canonical_raw_key="PICKUP TRUCK",
                raw_display_value="PICKUP TRUCK",
                first_seen_at=self.created_at,
                last_seen_at=self.created_at,
                is_resolved=True,
                resolved_at=self.created_at,
            )
        )

        unresolved = self.repository.list_observations(
            trusted_profile.trusted_profile_id,
            unresolved_only=True,
        )
        unmerged = self.repository.list_observations(
            trusted_profile.trusted_profile_id,
            unresolved_only=True,
            unmerged_only=True,
        )

        self.assertEqual(
            [(item.observation_domain, item.canonical_raw_key) for item in unresolved],
            [("equipment_mapping", "CRANE TRUCK"), ("labor_mapping", "104/EO")],
        )
        self.assertEqual(
            [(item.observation_domain, item.canonical_raw_key) for item in unmerged],
            [("labor_mapping", "104/EO")],
        )

    def test_sync_export_record_is_persisted(self) -> None:
        self.repository.bootstrap_filesystem_profiles()
        trusted_profile = next(
            profile for profile in self.repository.list_trusted_profiles() if profile.profile_name == "default"
        )
        current_version = self.repository.get_current_published_version(trusted_profile.trusted_profile_id)

        sync_export = self.repository.record_sync_export(
            TrustedProfileSyncExport(
                trusted_profile_sync_export_id="sync-export-1",
                organization_id=trusted_profile.organization_id,
                trusted_profile_version_id=current_version.trusted_profile_version_id,
                artifact_storage_ref="artifacts/default__v1.zip",
                artifact_file_hash="artifact-hash-1",
                manifest_json='{"version_number":1}',
                created_at=self.created_at,
            )
        )

        persisted = self.lineage_store.get_trusted_profile_sync_export(sync_export.trusted_profile_sync_export_id)
        self.assertEqual(persisted.artifact_storage_ref, "artifacts/default__v1.zip")
        self.assertEqual(persisted.artifact_file_hash, "artifact-hash-1")

    def _write_profile_bundle(
        self,
        *,
        profile_name: str,
        display_name: str,
        description: str,
        version: str,
        template_filename: str,
        labor_target: str,
        template_bytes: bytes,
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
                "template_filename": template_filename,
                "is_active": False,
            },
        )
        self._write_json(
            profile_dir / "labor_mapping.json",
            {
                "raw_mappings": {"103/J": labor_target},
                "saved_mappings": [
                    {"raw_value": "103/J", "target_classification": labor_target, "notes": ""}
                ],
            },
        )
        self._write_json(profile_dir / "equipment_mapping.json", {"raw_mappings": {}, "saved_mappings": []})
        self._write_json(profile_dir / "phase_mapping.json", {"20": "LABOR"})
        self._write_json(profile_dir / "vendor_normalization.json", {})
        self._write_json(
            profile_dir / "input_model.json",
            {"report_type": "vista_job_cost", "section_headers": {}},
        )
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
        self._write_json(profile_dir / "rates.json", {"labor_rates": {}, "equipment_rates": {}})
        self._write_json(profile_dir / "review_rules.json", {"default_omit_rules": []})
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
        (profile_dir / template_filename).write_bytes(template_bytes)

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
