"""Backend authoring service for Phase 2A trusted-profile settings parity."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from uuid import uuid4

from core.config import ConfigLoader, ProfileManager
from core.models import Record
from core.models.lineage import (
    TrustedProfile,
    TrustedProfileDraft,
    TrustedProfileObservation,
    TrustedProfileSyncExport,
    TrustedProfileVersion,
)
from infrastructure.storage import RuntimeStorage, StoredArtifact
from services.profile_bundle_helpers import (
    canonicalize_equipment_mapping_key,
    canonicalize_labor_mapping_key,
    build_classification_bundle_edit_result,
    build_default_omit_phase_options,
    build_default_omit_rule_rows,
    build_default_omit_rules_config,
    build_equipment_mapping_config,
    build_equipment_mapping_rows,
    build_equipment_rate_rows,
    build_labor_mapping_config,
    build_labor_mapping_rows,
    build_labor_rate_rows,
    build_rates_config,
    derive_labor_mapping_key,
    merge_observed_equipment_raw_values,
    merge_observed_labor_raw_values,
)
from services.profile_authoring_errors import ProfileAuthoringConflictError
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository


_EDITABLE_DOMAIN_KEYS = (
    "review_rules",
    "labor_mapping",
    "equipment_mapping",
    "labor_slots",
    "equipment_slots",
    "rates",
)
_DEFERRED_DOMAIN_KEYS = (
    "vendor_normalization",
    "phase_mapping",
    "input_model",
    "recap_template_map",
)
_OBSERVATION_DOMAIN_LABOR = "labor_mapping"
_OBSERVATION_DOMAIN_EQUIPMENT = "equipment_mapping"


@dataclass(frozen=True, slots=True)
class PublishedProfileDetail:
    """Read-only published trusted-profile detail for authoring entry."""

    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None
    current_published_version_id: str
    current_published_version_number: int
    current_published_content_hash: str
    template_artifact_ref: str | None
    template_file_hash: str | None
    template_filename: str | None
    open_draft_id: str | None
    deferred_domains: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DraftEditorState:
    """Editor-ready mutable draft state for the approved Phase 2A domains."""

    trusted_profile_draft_id: str
    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None
    current_published_version_id: str
    current_published_version_number: int
    current_published_content_hash: str
    base_trusted_profile_version_id: str | None
    draft_content_hash: str
    template_artifact_ref: str | None
    template_file_hash: str | None
    template_filename: str | None
    default_omit_rules: list[dict[str, str]]
    default_omit_phase_options: list[dict[str, str]]
    labor_mappings: list[dict[str, Any]]
    equipment_mappings: list[dict[str, Any]]
    labor_slots: list[dict[str, Any]]
    equipment_slots: list[dict[str, Any]]
    labor_rates: list[dict[str, str]]
    equipment_rates: list[dict[str, str]]
    deferred_domains: dict[str, Any]
    validation_errors: list[str]


@dataclass(frozen=True, slots=True)
class ProfileSyncExportResult:
    """Persisted desktop-sync export plus its download-ready artifact metadata."""

    trusted_profile_sync_export_id: str
    trusted_profile_version_id: str
    trusted_profile_id: str
    profile_name: str
    display_name: str
    version_number: int
    archive_filename: str
    artifact_file_hash: str | None
    created_at: datetime
    stored_artifact: StoredArtifact


class ProfileAuthoringService:
    """Orchestrate persisted published profile inspection, draft edits, validation, and publish."""

    def __init__(
        self,
        *,
        repository: TrustedProfileAuthoringRepository,
        profile_manager: ProfileManager | None = None,
        artifact_store: RuntimeStorage | None = None,
        now_provider: Callable | None = None,
    ) -> None:
        self._repository = repository
        self._profile_manager = profile_manager or ProfileManager()
        self._artifact_store = artifact_store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def get_profile_detail(self, trusted_profile_id: str) -> PublishedProfileDetail:
        """Return read-only current published profile detail."""
        trusted_profile = self._repository.get_trusted_profile(trusted_profile_id)
        published_version = self._repository.get_current_published_version(trusted_profile_id)
        draft_id = self._get_open_draft_id(trusted_profile_id)
        return self._build_profile_detail(
            trusted_profile=trusted_profile,
            published_version=published_version,
            open_draft_id=draft_id,
        )

    def create_trusted_profile(
        self,
        *,
        profile_name: str,
        display_name: str,
        description: str = "",
        seed_trusted_profile_id: str | None = None,
        created_by_user_id: str | None = None,
    ) -> PublishedProfileDetail:
        """Create one new trusted profile seeded from an existing published profile."""
        normalized_profile_name = self._profile_manager.validate_profile_name(profile_name)
        normalized_display_name = str(display_name or "").strip()
        if not normalized_display_name:
            raise ValueError("Display name is required when creating a trusted profile.")
        self._validate_new_profile_identity(
            profile_name=normalized_profile_name,
            display_name=normalized_display_name,
        )
        seed_profile_id = seed_trusted_profile_id or self._default_seed_trusted_profile_id()
        trusted_profile, published_version = self._repository.create_trusted_profile_from_published_clone(
            profile_name=normalized_profile_name,
            display_name=normalized_display_name,
            description=description,
            seed_trusted_profile_id=seed_profile_id,
            created_by_user_id=created_by_user_id,
        )
        return self._build_profile_detail(
            trusted_profile=trusted_profile,
            published_version=published_version,
            open_draft_id=None,
        )

    def archive_trusted_profile(self, trusted_profile_id: str) -> None:
        """Archive one user-created trusted profile without deleting published lineage."""
        trusted_profile = self._repository.get_trusted_profile(trusted_profile_id)
        if trusted_profile.archived_at is not None:
            raise ValueError(f"Trusted profile '{trusted_profile.display_name}' is already archived.")
        if trusted_profile.source_kind != "published_clone":
            raise ValueError("Only user-created trusted profiles can be archived in web settings.")
        if self._get_open_draft_or_none(trusted_profile_id) is not None:
            raise ValueError("Publish the open draft before archiving this trusted profile.")
        self._repository.archive_trusted_profile(trusted_profile_id)

    def unarchive_trusted_profile(self, trusted_profile_id: str) -> None:
        """Restore one archived user-created trusted profile to the active settings lists."""
        trusted_profile = self._repository.get_trusted_profile(trusted_profile_id)
        if trusted_profile.archived_at is None:
            raise ValueError(f"Trusted profile '{trusted_profile.display_name}' is already active.")
        if trusted_profile.source_kind != "published_clone":
            raise ValueError("Only user-created trusted profiles can be restored from web settings.")
        self._validate_unarchived_display_name(trusted_profile)
        self._repository.unarchive_trusted_profile(trusted_profile_id)

    def create_or_open_draft(
        self,
        trusted_profile_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> DraftEditorState:
        """Create or reuse the single mutable draft for one logical profile."""
        draft = self._repository.create_open_draft(
            trusted_profile_id,
            created_by_user_id=created_by_user_id,
        )
        return self.get_draft_state(draft.trusted_profile_draft_id)

    def get_draft_state(self, trusted_profile_draft_id: str) -> DraftEditorState:
        """Return full editor-ready state for one trusted-profile draft."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        trusted_profile = self._repository.get_trusted_profile(draft.trusted_profile_id)
        published_version = self._repository.get_current_published_version(draft.trusted_profile_id)
        validation_errors = self.validate_draft(trusted_profile_draft_id)
        return self._build_draft_state(
            trusted_profile=trusted_profile,
            published_version=published_version,
            draft=draft,
            validation_errors=validation_errors,
        )

    def update_default_omit_rules(
        self,
        trusted_profile_draft_id: str,
        rows: list[dict[str, str]],
    ) -> DraftEditorState:
        """Replace the draft default-omit rules and return refreshed state."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        bundle = self._copy_behavioral_bundle(draft.bundle_payload)
        bundle["review_rules"] = build_default_omit_rules_config(bundle["review_rules"], rows)
        updated_draft = self._save_validated_bundle(draft, bundle)
        return self.get_draft_state(updated_draft.trusted_profile_draft_id)

    def update_labor_mappings(
        self,
        trusted_profile_draft_id: str,
        rows: list[dict[str, str]],
    ) -> DraftEditorState:
        """Replace the draft labor mappings and return refreshed state."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        bundle = self._copy_behavioral_bundle(draft.bundle_payload)
        bundle["labor_mapping"] = build_labor_mapping_config(
            bundle["labor_mapping"],
            rows,
            valid_targets=self._active_classifications(bundle["labor_slots"]),
        )
        updated_draft = self._save_validated_bundle(draft, bundle)
        return self.get_draft_state(updated_draft.trusted_profile_draft_id)

    def update_equipment_mappings(
        self,
        trusted_profile_draft_id: str,
        rows: list[dict[str, str]],
    ) -> DraftEditorState:
        """Replace the draft equipment mappings and return refreshed state."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        bundle = self._copy_behavioral_bundle(draft.bundle_payload)
        bundle["equipment_mapping"] = build_equipment_mapping_config(
            bundle["equipment_mapping"],
            rows,
            valid_targets=self._active_classifications(bundle["equipment_slots"]),
        )
        updated_draft = self._save_validated_bundle(draft, bundle)
        return self.get_draft_state(updated_draft.trusted_profile_draft_id)

    def update_classifications(
        self,
        trusted_profile_draft_id: str,
        *,
        labor_slots: list[dict[str, Any]],
        equipment_slots: list[dict[str, Any]],
    ) -> DraftEditorState:
        """Replace labor/equipment slot tables and propagate supported dependent updates."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        bundle = self._copy_behavioral_bundle(draft.bundle_payload)
        current_labor_slots = self._slot_rows(bundle["labor_slots"])
        current_equipment_slots = self._slot_rows(bundle["equipment_slots"])
        current_labor_mapping_rows = build_labor_mapping_rows(bundle["labor_mapping"])
        current_equipment_mapping_rows = build_equipment_mapping_rows(bundle["equipment_mapping"])
        current_labor_rate_rows = build_labor_rate_rows(
            bundle["rates"],
            self._active_classifications(bundle["labor_slots"]),
        )
        current_equipment_rate_rows = build_equipment_rate_rows(
            bundle["rates"],
            self._active_classifications(bundle["equipment_slots"]),
        )
        edit_result = build_classification_bundle_edit_result(
            existing_labor_slots=current_labor_slots,
            updated_labor_slots=labor_slots,
            existing_equipment_slots=current_equipment_slots,
            updated_equipment_slots=equipment_slots,
            labor_mapping_rows=current_labor_mapping_rows,
            equipment_mapping_rows=current_equipment_mapping_rows,
            labor_rate_rows=current_labor_rate_rows,
            equipment_rate_rows=current_equipment_rate_rows,
            labor_mapping_config=bundle["labor_mapping"],
            equipment_mapping_config=bundle["equipment_mapping"],
            rates_config=bundle["rates"],
            recap_template_map=bundle["recap_template_map"],
        )
        bundle["labor_slots"] = edit_result.labor_slots_config
        bundle["equipment_slots"] = edit_result.equipment_slots_config
        bundle["labor_mapping"] = edit_result.labor_mapping_config
        bundle["equipment_mapping"] = edit_result.equipment_mapping_config
        bundle["rates"] = edit_result.rates_config
        bundle["recap_template_map"] = edit_result.recap_template_map
        updated_draft = self._save_validated_bundle(draft, bundle)
        return self.get_draft_state(updated_draft.trusted_profile_draft_id)

    def update_rates(
        self,
        trusted_profile_draft_id: str,
        *,
        labor_rows: list[dict[str, str]],
        equipment_rows: list[dict[str, str]],
    ) -> DraftEditorState:
        """Replace the draft rates payload and return refreshed state."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        bundle = self._copy_behavioral_bundle(draft.bundle_payload)
        bundle["rates"] = build_rates_config(
            bundle["rates"],
            labor_rows,
            equipment_rows,
            valid_labor_targets=self._active_classifications(bundle["labor_slots"]),
            valid_equipment_targets=self._active_classifications(bundle["equipment_slots"]),
        )
        updated_draft = self._save_validated_bundle(draft, bundle)
        return self.get_draft_state(updated_draft.trusted_profile_draft_id)

    def validate_draft(self, trusted_profile_draft_id: str) -> list[str]:
        """Validate whole-draft consistency and return any validation errors."""
        draft = self._repository.get_draft(trusted_profile_draft_id)
        return self._validate_bundle(draft.bundle_payload)

    def publish_draft(
        self,
        trusted_profile_draft_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> PublishedProfileDetail:
        """Validate and publish a draft into a new immutable current version."""
        validation_errors = self.validate_draft(trusted_profile_draft_id)
        if validation_errors:
            raise ValueError(validation_errors[0])
        draft = self._repository.get_draft(trusted_profile_draft_id)
        published_version = self._repository.publish_draft(
            trusted_profile_draft_id,
            created_by_user_id=created_by_user_id,
        )
        self._mark_resolved_observations_for_bundle(
            draft.trusted_profile_id,
            published_version.bundle_payload,
        )
        trusted_profile = self._repository.get_trusted_profile(draft.trusted_profile_id)
        return self._build_profile_detail(
            trusted_profile=trusted_profile,
            published_version=published_version,
            open_draft_id=None,
        )

    def discard_draft(self, trusted_profile_draft_id: str) -> None:
        """Discard one mutable draft without changing any published version."""
        self._repository.discard_draft(trusted_profile_draft_id)

    def create_desktop_sync_export(
        self,
        trusted_profile_version_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> ProfileSyncExportResult:
        """Build and persist a manual desktop-sync archive from one immutable published version."""
        if self._artifact_store is None:
            raise ValueError("artifact_store is required to create desktop-sync exports.")

        published_version = self._repository.get_trusted_profile_version(trusted_profile_version_id)
        trusted_profile = self._repository.get_trusted_profile(published_version.trusted_profile_id)
        archive_root_name = self._build_sync_archive_root_name(
            trusted_profile.profile_name,
            published_version.version_number,
        )
        archive_filename = f"{archive_root_name}.zip"
        manifest_payload = self._build_sync_manifest(
            trusted_profile=trusted_profile,
            published_version=published_version,
        )
        archive_bytes = self._build_sync_archive_bytes(
            published_version=published_version,
            archive_root_name=archive_root_name,
            manifest_payload=manifest_payload,
        )
        artifact_file_hash = hashlib.sha256(archive_bytes).hexdigest()
        stored_artifact = self._artifact_store.save_profile_sync_export(
            trusted_profile_version_id=published_version.trusted_profile_version_id,
            original_filename=archive_filename,
            content_bytes=archive_bytes,
            content_type="application/zip",
        )
        sync_export = self._repository.record_sync_export(
            TrustedProfileSyncExport(
                trusted_profile_sync_export_id=(
                    f"trusted-profile-sync-export:{published_version.trusted_profile_version_id}:{uuid4().hex}"
                ),
                organization_id=trusted_profile.organization_id,
                trusted_profile_version_id=published_version.trusted_profile_version_id,
                artifact_storage_ref=stored_artifact.storage_ref,
                artifact_file_hash=artifact_file_hash,
                manifest_json=json.dumps(manifest_payload, indent=2, sort_keys=True, ensure_ascii=True),
                created_by_user_id=created_by_user_id,
                created_at=self._now_provider(),
            )
        )
        return ProfileSyncExportResult(
            trusted_profile_sync_export_id=sync_export.trusted_profile_sync_export_id,
            trusted_profile_version_id=published_version.trusted_profile_version_id,
            trusted_profile_id=trusted_profile.trusted_profile_id,
            profile_name=trusted_profile.profile_name,
            display_name=trusted_profile.display_name,
            version_number=published_version.version_number,
            archive_filename=stored_artifact.original_filename,
            artifact_file_hash=sync_export.artifact_file_hash,
            created_at=sync_export.created_at,
            stored_artifact=stored_artifact,
        )

    def resolve_desktop_sync_export_payload(
        self,
        trusted_profile_sync_export_id: str,
    ) -> StoredArtifact:
        """Resolve one persisted desktop-sync archive through the configured artifact storage seam."""
        if self._artifact_store is None:
            raise ValueError("artifact_store is required to resolve desktop-sync exports.")
        sync_export = self._repository.get_sync_export(trusted_profile_sync_export_id)
        return self._artifact_store.get_profile_sync_export(sync_export.artifact_storage_ref)

    def capture_unmapped_observations(
        self,
        trusted_profile_id: str,
        *,
        processing_run_id: str,
        records: list[Record],
    ) -> None:
        """Persist observed unmapped labor/equipment values and merge unresolved draft placeholders."""
        if not records:
            return

        published_version = self._repository.get_current_published_version(trusted_profile_id)
        published_bundle = self._behavioral_bundle(published_version.bundle_payload)
        draft = self._get_open_draft_or_none(trusted_profile_id)
        draft_bundle = self._behavioral_bundle(draft.bundle_payload) if draft else None

        for candidate in self._collect_observation_candidates(records):
            domain = candidate["domain"]
            canonical_raw_key = candidate["canonical_raw_key"]
            raw_display_value = candidate["raw_display_value"]

            published_state = self._mapping_presence_state(
                published_bundle,
                domain=domain,
                canonical_raw_key=canonical_raw_key,
            )
            existing_observation = self._repository.get_observation(
                trusted_profile_id,
                domain,
                canonical_raw_key,
            )
            if existing_observation and existing_observation.is_resolved:
                continue
            if published_state == "resolved":
                self._upsert_observation(
                    trusted_profile_id=trusted_profile_id,
                    domain=domain,
                    canonical_raw_key=canonical_raw_key,
                    raw_display_value=raw_display_value,
                    processing_run_id=processing_run_id,
                    is_resolved=True,
                )
                continue

            draft_state = (
                self._mapping_presence_state(
                    draft_bundle,
                    domain=domain,
                    canonical_raw_key=canonical_raw_key,
                )
                if draft_bundle is not None
                else "absent"
            )
            if draft_state == "resolved":
                self._upsert_observation(
                    trusted_profile_id=trusted_profile_id,
                    domain=domain,
                    canonical_raw_key=canonical_raw_key,
                    raw_display_value=raw_display_value,
                    processing_run_id=processing_run_id,
                )
                continue

            observation = self._upsert_observation(
                trusted_profile_id=trusted_profile_id,
                domain=domain,
                canonical_raw_key=canonical_raw_key,
                raw_display_value=raw_display_value,
                processing_run_id=processing_run_id,
            )
            if published_state == "unresolved" or draft_state == "unresolved":
                continue

            if draft is None:
                draft = self._repository.create_open_draft(trusted_profile_id)
                draft_bundle = self._behavioral_bundle(draft.bundle_payload)

            updated_bundle, did_merge = self._merge_observation_into_draft_bundle(
                draft_bundle,
                domain=domain,
                raw_display_value=raw_display_value,
            )
            if not did_merge:
                continue

            draft = self._save_validated_bundle(draft, updated_bundle)
            draft_bundle = self._behavioral_bundle(draft.bundle_payload)
            self._repository.mark_observation_draft_applied(
                trusted_profile_id,
                domain,
                canonical_raw_key,
                applied_at=observation.last_seen_at,
            )

    def _save_validated_bundle(
        self,
        draft: TrustedProfileDraft,
        behavioral_bundle: dict[str, Any],
    ) -> TrustedProfileDraft:
        """Persist a draft bundle only after whole-draft validation succeeds."""
        updated_bundle_payload = self._replace_behavioral_bundle(draft.bundle_payload, behavioral_bundle)
        validation_errors = self._validate_bundle(updated_bundle_payload)
        if validation_errors:
            raise ValueError(validation_errors[0])
        return self._repository.save_draft_bundle(
            draft.trusted_profile_draft_id,
            updated_bundle_payload,
        )

    def _collect_observation_candidates(self, records: list[Record]) -> list[dict[str, str]]:
        """Collect unique unmapped labor/equipment observation candidates from processed records."""
        candidates_by_key: dict[tuple[str, str], dict[str, str]] = {}
        for record in records:
            labor_candidate = self._build_labor_observation_candidate(record)
            if labor_candidate is not None:
                candidates_by_key[(labor_candidate["domain"], labor_candidate["canonical_raw_key"])] = labor_candidate
            equipment_candidate = self._build_equipment_observation_candidate(record)
            if equipment_candidate is not None:
                candidates_by_key[(equipment_candidate["domain"], equipment_candidate["canonical_raw_key"])] = equipment_candidate
        return list(candidates_by_key.values())

    def _build_labor_observation_candidate(self, record: Record) -> dict[str, str] | None:
        """Build one unmapped labor observation candidate when the record is still unresolved."""
        record_type = str(record.record_type_normalized or record.record_type or "").strip().casefold()
        if record_type != "labor":
            return None
        if str(record.recap_labor_classification or "").strip():
            return None

        raw_value = str(record.labor_class_raw or "").strip()
        if not raw_value:
            return None

        canonical_raw_key = derive_labor_mapping_key(
            raw_value,
            union_code=record.union_code,
            allow_union_prefix=not record.uses_fallback_labor_mapping_source(),
        )
        if not canonical_raw_key:
            return None
        return {
            "domain": _OBSERVATION_DOMAIN_LABOR,
            "canonical_raw_key": canonical_raw_key,
            "raw_display_value": canonical_raw_key,
        }

    def _build_equipment_observation_candidate(self, record: Record) -> dict[str, str] | None:
        """Build one unmapped equipment observation candidate when the record is still unresolved."""
        record_type = str(record.record_type_normalized or record.record_type or "").strip().casefold()
        if record_type != "equipment":
            return None
        if str(record.equipment_category or "").strip():
            return None

        raw_key = str(record.equipment_mapping_key or "").strip()
        canonical_raw_key = canonicalize_equipment_mapping_key(raw_key)
        if not canonical_raw_key:
            return None
        return {
            "domain": _OBSERVATION_DOMAIN_EQUIPMENT,
            "canonical_raw_key": canonical_raw_key,
            "raw_display_value": canonical_raw_key,
        }

    def _mapping_presence_state(
        self,
        behavioral_bundle: dict[str, Any] | None,
        *,
        domain: str,
        canonical_raw_key: str,
    ) -> str:
        """Return whether a mapping key is absent, unresolved, or resolved in one bundle."""
        if behavioral_bundle is None:
            return "absent"
        if domain == _OBSERVATION_DOMAIN_LABOR:
            rows = build_labor_mapping_rows(behavioral_bundle["labor_mapping"])
            row_key = "raw_value"
            target_key = "target_classification"
        elif domain == _OBSERVATION_DOMAIN_EQUIPMENT:
            rows = build_equipment_mapping_rows(behavioral_bundle["equipment_mapping"])
            row_key = "raw_description"
            target_key = "target_category"
        else:
            raise ValueError(f"Unsupported observation domain '{domain}'.")

        for row in rows:
            if str(row.get(row_key, "")).strip().casefold() != canonical_raw_key.casefold():
                continue
            if str(row.get(target_key, "")).strip():
                return "resolved"
            return "unresolved"
        return "absent"

    def _upsert_observation(
        self,
        *,
        trusted_profile_id: str,
        domain: str,
        canonical_raw_key: str,
        raw_display_value: str,
        processing_run_id: str,
        is_resolved: bool = False,
    ) -> TrustedProfileObservation:
        """Create or refresh one persisted observation row keyed by profile/domain/raw key."""
        trusted_profile = self._repository.get_trusted_profile(trusted_profile_id)
        existing_observation = self._repository.get_observation(
            trusted_profile_id,
            domain,
            canonical_raw_key,
        )
        observed_at = self._now_provider() if self._now_provider is not None else None
        if observed_at is None:
            raise ValueError("Observation capture requires a current timestamp.")
        resolved = bool(existing_observation and existing_observation.is_resolved) or is_resolved
        resolved_at = (
            existing_observation.resolved_at
            if existing_observation and existing_observation.resolved_at
            else observed_at if resolved else None
        )
        return self._repository.upsert_observation(
            TrustedProfileObservation(
                trusted_profile_observation_id=existing_observation.trusted_profile_observation_id
                if existing_observation
                else self._build_observation_id(trusted_profile_id, domain, canonical_raw_key),
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile_id,
                observation_domain=domain,
                canonical_raw_key=canonical_raw_key,
                raw_display_value=raw_display_value,
                first_seen_processing_run_id=existing_observation.first_seen_processing_run_id
                if existing_observation
                else processing_run_id,
                last_seen_processing_run_id=processing_run_id,
                first_seen_at=existing_observation.first_seen_at if existing_observation else observed_at,
                last_seen_at=observed_at,
                draft_applied_at=existing_observation.draft_applied_at if existing_observation else None,
                is_resolved=resolved,
                resolved_at=resolved_at,
            )
        )

    def _merge_observation_into_draft_bundle(
        self,
        behavioral_bundle: dict[str, Any],
        *,
        domain: str,
        raw_display_value: str,
    ) -> tuple[dict[str, Any], bool]:
        """Merge exactly one unresolved observed row into the appropriate mapping domain."""
        updated_bundle = self._copy_behavioral_bundle({"behavioral_bundle": behavioral_bundle})
        if domain == _OBSERVATION_DOMAIN_LABOR:
            updated_mapping, did_update = merge_observed_labor_raw_values(
                updated_bundle["labor_mapping"],
                [raw_display_value],
            )
            updated_bundle["labor_mapping"] = updated_mapping
            return updated_bundle, did_update
        if domain == _OBSERVATION_DOMAIN_EQUIPMENT:
            updated_mapping, did_update = merge_observed_equipment_raw_values(
                updated_bundle["equipment_mapping"],
                [raw_display_value],
            )
            updated_bundle["equipment_mapping"] = updated_mapping
            return updated_bundle, did_update
        raise ValueError(f"Unsupported observation domain '{domain}'.")

    def _mark_resolved_observations_for_bundle(
        self,
        trusted_profile_id: str,
        bundle_payload: dict[str, Any],
    ) -> None:
        """Mark observations resolved when the newly published bundle now contains mapped targets."""
        behavioral_bundle = self._behavioral_bundle(bundle_payload)
        resolved_at = self._now_provider() if self._now_provider is not None else None
        if resolved_at is None:
            raise ValueError("Observation resolution requires a current timestamp.")
        for observation in self._repository.list_observations(trusted_profile_id, unresolved_only=True):
            mapping_state = self._mapping_presence_state(
                behavioral_bundle,
                domain=observation.observation_domain,
                canonical_raw_key=observation.canonical_raw_key,
            )
            if mapping_state == "resolved":
                self._repository.mark_observation_resolved(
                    trusted_profile_id,
                    observation.observation_domain,
                    observation.canonical_raw_key,
                    resolved_at=resolved_at,
                )

    def _get_open_draft_or_none(self, trusted_profile_id: str) -> TrustedProfileDraft | None:
        """Return the current open draft when present without widening control flow around KeyError."""
        try:
            return self._repository.get_open_draft(trusted_profile_id)
        except KeyError:
            return None

    def _default_seed_trusted_profile_id(self) -> str:
        """Resolve the default seed trusted profile for explicit create-profile flows."""
        active_profile_name = str(self._profile_manager.get_active_profile_name() or "").strip()
        resolved = self._repository.resolve_current_published_profile(active_profile_name or None)
        return resolved.trusted_profile.trusted_profile_id

    def _validate_new_profile_identity(self, *, profile_name: str, display_name: str) -> None:
        """Validate one new trusted-profile identity against current persisted state."""
        all_profiles = self._repository.list_trusted_profiles(include_archived=True)
        field_errors: dict[str, list[str]] = {}
        if any(existing.profile_name.casefold() == profile_name.casefold() for existing in all_profiles):
            field_errors["profile_name"] = [
                f"Trusted profile key '{profile_name}' already exists. Choose a different stable profile key."
            ]
        if any(
            existing.archived_at is None
            and existing.display_name.strip().casefold() == display_name.casefold()
            for existing in all_profiles
        ):
            field_errors["display_name"] = [
                f"Display name '{display_name}' is already in use by another active trusted profile."
            ]
        if field_errors:
            if "profile_name" in field_errors and "display_name" in field_errors:
                message = "Choose a unique profile key and display name before creating this trusted profile."
            elif "profile_name" in field_errors:
                message = field_errors["profile_name"][0]
            else:
                message = field_errors["display_name"][0]
            raise ProfileAuthoringConflictError(
                message,
                error_code="trusted_profile_identity_conflict",
                field_errors=field_errors,
            )

    def _validate_unarchived_display_name(self, trusted_profile: TrustedProfile) -> None:
        """Reject restoring an archived profile when its active display name slot is no longer available."""
        active_profiles = self._repository.list_trusted_profiles()
        conflicting_active = next(
            (
                existing
                for existing in active_profiles
                if existing.trusted_profile_id != trusted_profile.trusted_profile_id
                and existing.display_name.strip().casefold() == trusted_profile.display_name.strip().casefold()
            ),
            None,
        )
        if conflicting_active is None:
            return
        raise ProfileAuthoringConflictError(
            (
                f"Display name '{trusted_profile.display_name}' is already in use by active trusted profile "
                f"'{conflicting_active.display_name}'."
            ),
            error_code="trusted_profile_restore_conflict",
            field_errors={
                "display_name": [
                    (
                        f"Restore is blocked until the active display name '{trusted_profile.display_name}' "
                        "is no longer in use."
                    )
                ]
            },
        )

    def _build_observation_id(
        self,
        trusted_profile_id: str,
        domain: str,
        canonical_raw_key: str,
    ) -> str:
        """Build a deterministic observation id from the trusted profile, domain, and raw key."""
        digest = hashlib.sha256(f"{trusted_profile_id}|{domain}|{canonical_raw_key}".encode("utf-8")).hexdigest()[:16]
        return f"trusted-profile-observation:{digest}"

    def _build_profile_detail(
        self,
        *,
        trusted_profile: TrustedProfile,
        published_version: TrustedProfileVersion,
        open_draft_id: str | None,
    ) -> PublishedProfileDetail:
        """Build read-only published profile detail."""
        behavioral_bundle = self._behavioral_bundle(published_version.bundle_payload)
        template_payload = self._template_payload(behavioral_bundle)
        return PublishedProfileDetail(
            trusted_profile_id=trusted_profile.trusted_profile_id,
            profile_name=trusted_profile.profile_name,
            display_name=trusted_profile.display_name,
            description=trusted_profile.description,
            version_label=trusted_profile.version_label,
            current_published_version_id=published_version.trusted_profile_version_id,
            current_published_version_number=published_version.version_number,
            current_published_content_hash=published_version.content_hash,
            template_artifact_ref=published_version.template_artifact_ref,
            template_file_hash=published_version.template_file_hash,
            template_filename=str(template_payload.get("template_filename") or "") or None,
            open_draft_id=open_draft_id,
            deferred_domains=self._deferred_domains(behavioral_bundle),
        )

    def _build_sync_manifest(
        self,
        *,
        trusted_profile: TrustedProfile,
        published_version: TrustedProfileVersion,
    ) -> dict[str, Any]:
        """Build the deterministic manifest stored in a desktop-sync archive."""
        behavioral_bundle = self._behavioral_bundle(published_version.bundle_payload)
        template_payload = self._template_payload(behavioral_bundle)
        template_reference = (
            str(published_version.template_artifact_ref or "").strip()
            or str(template_payload.get("template_artifact_ref") or "").strip()
            or str(template_payload.get("template_filename") or "").strip()
        )
        template_file_hash = str(published_version.template_file_hash or "").strip()
        if not template_reference:
            raise ValueError(
                f"Trusted profile version '{published_version.trusted_profile_version_id}' is missing a stable "
                "template reference."
            )
        if not template_file_hash:
            raise ValueError(
                f"Trusted profile version '{published_version.trusted_profile_version_id}' is missing template "
                "file hash identity."
            )
        return {
            "trusted_profile_version_id": published_version.trusted_profile_version_id,
            "version_number": published_version.version_number,
            "published_at": published_version.created_at.isoformat(),
            "trusted_profile_id": trusted_profile.trusted_profile_id,
            "profile_name": trusted_profile.profile_name,
            "display_name": trusted_profile.display_name,
            "content_hash": published_version.content_hash,
            "template_file_hash": template_file_hash,
            "template_artifact_ref": template_reference,
            "template_filename": str(template_payload.get("template_filename") or "") or None,
            "source_kind": published_version.source_kind,
            "base_trusted_profile_version_id": published_version.base_trusted_profile_version_id,
        }

    def _build_sync_archive_bytes(
        self,
        *,
        published_version: TrustedProfileVersion,
        archive_root_name: str,
        manifest_payload: dict[str, Any],
    ) -> bytes:
        """Materialize one published version into a deterministic desktop-sync archive."""
        manifest_json = json.dumps(manifest_payload, indent=2, sort_keys=True, ensure_ascii=True)
        with TemporaryDirectory(prefix="job-cost-profile-sync-") as temp_dir:
            archive_source_dir = Path(temp_dir).resolve() / archive_root_name
            with self._repository.materialize_published_version_bundle(published_version) as materialized_dir:
                archive_source_dir.mkdir(parents=True, exist_ok=True)
                for source_path in sorted(materialized_dir.iterdir(), key=lambda item: item.name):
                    target_path = archive_source_dir / source_path.name
                    if source_path.is_file():
                        target_path.write_bytes(source_path.read_bytes())
                (archive_source_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                for source_path in sorted(archive_source_dir.rglob("*"), key=lambda item: item.as_posix()):
                    if not source_path.is_file():
                        continue
                    relative_path = source_path.relative_to(archive_source_dir.parent)
                    archive.writestr(
                        self._build_zip_info(relative_path.as_posix()),
                        source_path.read_bytes(),
                    )
            return buffer.getvalue()

    def _build_sync_archive_root_name(self, profile_name: str, version_number: int) -> str:
        """Return the deterministic versioned folder/archive name used for desktop sync exports."""
        normalized_slug = re.sub(r"[^a-z0-9._-]+", "-", str(profile_name or "").strip().lower()).strip("._-")
        if not normalized_slug:
            normalized_slug = "trusted-profile"
        return f"{normalized_slug}__v{version_number}"

    def _build_zip_info(self, archive_member_name: str) -> zipfile.ZipInfo:
        """Build deterministic zip metadata for one archive member."""
        zip_info = zipfile.ZipInfo(archive_member_name)
        zip_info.date_time = (1980, 1, 1, 0, 0, 0)
        zip_info.compress_type = zipfile.ZIP_DEFLATED
        return zip_info

    def _build_draft_state(
        self,
        *,
        trusted_profile: TrustedProfile,
        published_version: TrustedProfileVersion,
        draft: TrustedProfileDraft,
        validation_errors: list[str],
    ) -> DraftEditorState:
        """Build editor-ready draft state."""
        behavioral_bundle = self._behavioral_bundle(draft.bundle_payload)
        phase_catalog = self._phase_catalog_rows()
        default_omit_rules = build_default_omit_rule_rows(
            behavioral_bundle["review_rules"],
            phase_options=build_default_omit_phase_options(
                catalog_phase_rows=phase_catalog,
                saved_rule_rows=behavioral_bundle["review_rules"].get("default_omit_rules", []),
            ),
        )
        phase_options = build_default_omit_phase_options(
            catalog_phase_rows=phase_catalog,
            saved_rule_rows=behavioral_bundle["review_rules"].get("default_omit_rules", []),
        )
        labor_classifications = self._active_classifications(behavioral_bundle["labor_slots"])
        equipment_classifications = self._active_classifications(behavioral_bundle["equipment_slots"])
        template_payload = self._template_payload(behavioral_bundle)
        return DraftEditorState(
            trusted_profile_draft_id=draft.trusted_profile_draft_id,
            trusted_profile_id=trusted_profile.trusted_profile_id,
            profile_name=trusted_profile.profile_name,
            display_name=trusted_profile.display_name,
            description=trusted_profile.description,
            version_label=trusted_profile.version_label,
            current_published_version_id=published_version.trusted_profile_version_id,
            current_published_version_number=published_version.version_number,
            current_published_content_hash=published_version.content_hash,
            base_trusted_profile_version_id=draft.base_trusted_profile_version_id,
            draft_content_hash=draft.content_hash,
            template_artifact_ref=draft.template_artifact_ref,
            template_file_hash=draft.template_file_hash,
            template_filename=str(template_payload.get("template_filename") or "") or None,
            default_omit_rules=default_omit_rules,
            default_omit_phase_options=phase_options,
            labor_mappings=build_labor_mapping_rows(behavioral_bundle["labor_mapping"]),
            equipment_mappings=build_equipment_mapping_rows(behavioral_bundle["equipment_mapping"]),
            labor_slots=self._slot_rows(behavioral_bundle["labor_slots"]),
            equipment_slots=self._slot_rows(behavioral_bundle["equipment_slots"]),
            labor_rates=build_labor_rate_rows(behavioral_bundle["rates"], labor_classifications),
            equipment_rates=build_equipment_rate_rows(behavioral_bundle["rates"], equipment_classifications),
            deferred_domains=self._deferred_domains(behavioral_bundle),
            validation_errors=list(validation_errors),
        )

    def _validate_bundle(self, bundle_payload: dict[str, Any]) -> list[str]:
        """Validate the full editable slice of one bundle payload."""
        behavioral_bundle = self._behavioral_bundle(bundle_payload)
        validation_errors: list[str] = []

        try:
            phase_options = build_default_omit_phase_options(
                catalog_phase_rows=self._phase_catalog_rows(),
                saved_rule_rows=behavioral_bundle["review_rules"].get("default_omit_rules", []),
            )
            build_default_omit_rules_config(
                behavioral_bundle["review_rules"],
                build_default_omit_rule_rows(
                    behavioral_bundle["review_rules"],
                    phase_options=phase_options,
                ),
            )
        except ValueError as exc:
            validation_errors.append(str(exc))

        labor_classifications = self._active_classifications(behavioral_bundle["labor_slots"])
        equipment_classifications = self._active_classifications(behavioral_bundle["equipment_slots"])

        try:
            build_labor_mapping_config(
                behavioral_bundle["labor_mapping"],
                build_labor_mapping_rows(behavioral_bundle["labor_mapping"]),
                valid_targets=labor_classifications,
            )
        except ValueError as exc:
            validation_errors.append(str(exc))

        try:
            build_equipment_mapping_config(
                behavioral_bundle["equipment_mapping"],
                build_equipment_mapping_rows(behavioral_bundle["equipment_mapping"]),
                valid_targets=equipment_classifications,
            )
        except ValueError as exc:
            validation_errors.append(str(exc))

        try:
            build_classification_bundle_edit_result(
                existing_labor_slots=self._slot_rows(behavioral_bundle["labor_slots"]),
                updated_labor_slots=self._slot_rows(behavioral_bundle["labor_slots"]),
                existing_equipment_slots=self._slot_rows(behavioral_bundle["equipment_slots"]),
                updated_equipment_slots=self._slot_rows(behavioral_bundle["equipment_slots"]),
                labor_mapping_rows=build_labor_mapping_rows(behavioral_bundle["labor_mapping"]),
                equipment_mapping_rows=build_equipment_mapping_rows(behavioral_bundle["equipment_mapping"]),
                labor_rate_rows=build_labor_rate_rows(behavioral_bundle["rates"], labor_classifications),
                equipment_rate_rows=build_equipment_rate_rows(behavioral_bundle["rates"], equipment_classifications),
                labor_mapping_config=behavioral_bundle["labor_mapping"],
                equipment_mapping_config=behavioral_bundle["equipment_mapping"],
                rates_config=behavioral_bundle["rates"],
                recap_template_map=behavioral_bundle["recap_template_map"],
            )
        except ValueError as exc:
            validation_errors.append(str(exc))

        try:
            build_rates_config(
                behavioral_bundle["rates"],
                build_labor_rate_rows(behavioral_bundle["rates"], labor_classifications),
                build_equipment_rate_rows(behavioral_bundle["rates"], equipment_classifications),
                valid_labor_targets=labor_classifications,
                valid_equipment_targets=equipment_classifications,
            )
        except ValueError as exc:
            validation_errors.append(str(exc))

        if not str(self._template_payload(behavioral_bundle).get("template_file_hash") or "").strip():
            validation_errors.append("Published profile bundle is missing template identity.")

        return validation_errors

    def _behavioral_bundle(self, bundle_payload: dict[str, Any]) -> dict[str, Any]:
        """Return one copy of the editable behavioral bundle from the persisted payload."""
        behavioral_bundle = bundle_payload.get("behavioral_bundle", {})
        if not isinstance(behavioral_bundle, dict):
            raise ValueError("Trusted profile bundle is missing a behavioral bundle payload.")
        return {
            "review_rules": dict(behavioral_bundle.get("review_rules", {})),
            "labor_mapping": dict(behavioral_bundle.get("labor_mapping", {})),
            "equipment_mapping": dict(behavioral_bundle.get("equipment_mapping", {})),
            "labor_slots": dict(behavioral_bundle.get("labor_slots", {})),
            "equipment_slots": dict(behavioral_bundle.get("equipment_slots", {})),
            "rates": dict(behavioral_bundle.get("rates", {})),
            "vendor_normalization": dict(behavioral_bundle.get("vendor_normalization", {})),
            "phase_mapping": dict(behavioral_bundle.get("phase_mapping", {})),
            "input_model": dict(behavioral_bundle.get("input_model", {})),
            "recap_template_map": dict(behavioral_bundle.get("recap_template_map", {})),
            "template": dict(behavioral_bundle.get("template", {})),
        }

    def _copy_behavioral_bundle(self, bundle_payload: dict[str, Any]) -> dict[str, Any]:
        """Return a mutable copy of the editable behavioral bundle."""
        return self._behavioral_bundle(bundle_payload)

    def _replace_behavioral_bundle(
        self,
        existing_bundle_payload: dict[str, Any],
        behavioral_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace the stored behavioral bundle while preserving traceability payloads."""
        next_bundle_payload = dict(existing_bundle_payload)
        next_bundle_payload["behavioral_bundle"] = behavioral_bundle
        return next_bundle_payload

    def _active_classifications(self, slot_config: dict[str, Any]) -> list[str]:
        """Return configured active classification labels from a slot config payload."""
        classifications = slot_config.get("classifications", [])
        if isinstance(classifications, list) and classifications:
            return [str(item).strip() for item in classifications if str(item).strip()]
        return [
            str(slot.get("label") or "").strip()
            for slot in self._slot_rows(slot_config)
            if slot.get("active") and str(slot.get("label") or "").strip()
        ]

    def _slot_rows(self, slot_config: dict[str, Any]) -> list[dict[str, Any]]:
        """Return editable slot rows from a stored slot config payload."""
        raw_slots = slot_config.get("slots", [])
        if not isinstance(raw_slots, list):
            return []
        return [
            {
                "slot_id": str(slot.get("slot_id") or "").strip(),
                "label": str(slot.get("label") or "").strip(),
                "active": bool(slot.get("active")),
            }
            for slot in raw_slots
            if isinstance(slot, dict)
        ]

    def _deferred_domains(self, behavioral_bundle: dict[str, Any]) -> dict[str, Any]:
        """Return the read-only deferred domains from a behavioral bundle."""
        return {key: behavioral_bundle[key] for key in _DEFERRED_DOMAIN_KEYS}

    def _template_payload(self, behavioral_bundle: dict[str, Any]) -> dict[str, Any]:
        """Return the template identity payload from a behavioral bundle."""
        template_payload = behavioral_bundle.get("template", {})
        return dict(template_payload) if isinstance(template_payload, dict) else {}

    def _phase_catalog_rows(self) -> list[dict[str, Any]]:
        """Load the shared phase catalog used for default-omit editing."""
        try:
            loader = ConfigLoader(
                config_dir=self._profile_manager.get_active_profile_dir(),
                legacy_config_dir=self._get_legacy_config_dir(),
            )
            phase_catalog = loader.get_phase_catalog()
        except Exception:
            return []
        phases = phase_catalog.get("phases", []) if isinstance(phase_catalog, dict) else []
        return list(phases) if isinstance(phases, list) else []

    def _get_legacy_config_dir(self) -> Path | None:
        """Reuse the configured shared-config root when a custom profile manager is supplied."""
        legacy_config_dir = getattr(self._profile_manager, "_legacy_config_root", None)
        if isinstance(legacy_config_dir, Path):
            return legacy_config_dir
        return None

    def _get_open_draft_id(self, trusted_profile_id: str) -> str | None:
        """Return the current open draft id when present."""
        try:
            return self._repository.get_open_draft(trusted_profile_id).trusted_profile_draft_id
        except KeyError:
            return None
