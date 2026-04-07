"""Persistence-facing repository for trusted-profile versions, drafts, observations, and bootstrap."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterator

from core.config import ConfigLoader, ProfileManager
from core.models.lineage import (
    Organization,
    TemplateArtifact,
    TrustedProfile,
    TrustedProfileDraft,
    TrustedProfileObservation,
    TrustedProfileSyncExport,
    TrustedProfileVersion,
)
from infrastructure.persistence.sqlite_lineage_store import SqliteLineageStore
from services.lineage_service import build_template_artifact, canonicalize_json


@dataclass(frozen=True, slots=True)
class MaterializedTrustedProfileBundle:
    """Resolved filesystem profile bundle plus deterministic persisted payloads."""

    trusted_profile: TrustedProfile
    bundle_payload: dict[str, object]
    canonical_bundle_json: str
    content_hash: str
    template_artifact_ref: str | None
    template_file_hash: str | None
    template_artifact: TemplateArtifact | None


@dataclass(frozen=True, slots=True)
class ResolvedPublishedTrustedProfile:
    """Current persisted published version selected for web processing."""

    organization: Organization
    trusted_profile: TrustedProfile
    trusted_profile_version: TrustedProfileVersion


class TrustedProfileAuthoringRepository:
    """Repository seam for persisted trusted-profile authoring records and bootstrap."""

    _BUNDLE_FILE_MAP = {
        "labor_mapping": "labor_mapping.json",
        "equipment_mapping": "equipment_mapping.json",
        "phase_mapping": "phase_mapping.json",
        "vendor_normalization": "vendor_normalization.json",
        "input_model": "input_model.json",
        "review_rules": "review_rules.json",
        "rates": "rates.json",
        "labor_slots": "target_labor_classifications.json",
        "equipment_slots": "target_equipment_classifications.json",
        "recap_template_map": "recap_template_map.json",
    }

    def __init__(
        self,
        *,
        lineage_store: SqliteLineageStore,
        profile_manager: ProfileManager | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._profile_manager = profile_manager or ProfileManager()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def bootstrap_filesystem_profiles(self) -> list[TrustedProfileVersion]:
        """Materialize current filesystem profiles into persisted published versions."""
        organization = self._ensure_default_organization()
        bootstrapped_versions: list[TrustedProfileVersion] = []

        for profile_metadata in self._profile_manager.list_profiles():
            profile_name = str(profile_metadata.get("profile_name") or "").strip()
            if not profile_name:
                continue
            profile_dir = self._profile_manager.get_profile_dir(profile_name)
            if profile_dir is None:
                continue

            materialized_bundle = self._materialize_filesystem_profile(
                organization=organization,
                profile_metadata=profile_metadata,
                profile_dir=profile_dir,
            )
            existing_versions = self._lineage_store.list_trusted_profile_versions(
                materialized_bundle.trusted_profile.trusted_profile_id
            )
            equivalent_version = next(
                (
                    version
                    for version in existing_versions
                    if version.content_hash == materialized_bundle.content_hash
                ),
                None,
            )
            if equivalent_version is None:
                next_version_number = self._lineage_store.get_next_trusted_profile_version_number(
                    materialized_bundle.trusted_profile.trusted_profile_id
                )
                equivalent_version = self._lineage_store.get_or_create_trusted_profile_version(
                    TrustedProfileVersion(
                        trusted_profile_version_id=self._build_trusted_profile_version_id(
                            organization_id=organization.organization_id,
                            profile_name=materialized_bundle.trusted_profile.profile_name,
                            version_number=next_version_number,
                        ),
                        organization_id=organization.organization_id,
                        trusted_profile_id=materialized_bundle.trusted_profile.trusted_profile_id,
                        version_number=next_version_number,
                        bundle_payload=materialized_bundle.bundle_payload,
                        canonical_bundle_json=materialized_bundle.canonical_bundle_json,
                        content_hash=materialized_bundle.content_hash,
                        template_artifact_id=(
                            materialized_bundle.template_artifact.template_artifact_id
                            if materialized_bundle.template_artifact
                            else None
                        ),
                        template_artifact_ref=materialized_bundle.template_artifact_ref,
                        template_file_hash=materialized_bundle.template_file_hash,
                        source_kind="filesystem_bootstrap",
                        created_at=self._now_provider(),
                    )
                )

            trusted_profile = self._lineage_store.set_current_published_version(
                materialized_bundle.trusted_profile.trusted_profile_id,
                equivalent_version.trusted_profile_version_id,
            )
            if trusted_profile.current_published_version_id != equivalent_version.trusted_profile_version_id:
                raise ValueError("Failed to persist current published trusted-profile version.")
            bootstrapped_versions.append(equivalent_version)

        return bootstrapped_versions

    def list_trusted_profiles(self) -> list[TrustedProfile]:
        """List logical trusted profiles after ensuring filesystem bootstrap exists."""
        organization = self._ensure_default_organization()
        profiles = self._lineage_store.list_trusted_profiles(organization.organization_id)
        if profiles:
            return profiles
        self.bootstrap_filesystem_profiles()
        return self._lineage_store.list_trusted_profiles(organization.organization_id)

    def get_trusted_profile(self, trusted_profile_id: str) -> TrustedProfile:
        """Fetch one logical trusted profile by id."""
        try:
            return self._lineage_store.get_trusted_profile(trusted_profile_id)
        except KeyError:
            self.bootstrap_filesystem_profiles()
            return self._lineage_store.get_trusted_profile(trusted_profile_id)

    def get_current_published_version(self, trusted_profile_id: str) -> TrustedProfileVersion:
        """Fetch the current published version for one logical trusted profile."""
        trusted_profile = self._repair_trusted_profile_current_version(
            self.get_trusted_profile(trusted_profile_id)
        )
        current_version_id = str(trusted_profile.current_published_version_id or "").strip()
        if not current_version_id:
            raise ValueError(
                f"TrustedProfile '{trusted_profile.profile_name}' does not have a current published version."
            )
        try:
            return self._lineage_store.get_trusted_profile_version(current_version_id)
        except KeyError as exc:
            raise ValueError(
                f"TrustedProfile '{trusted_profile.profile_name}' references missing published version "
                f"'{current_version_id}'."
            ) from exc

    def get_trusted_profile_version(self, trusted_profile_version_id: str) -> TrustedProfileVersion:
        """Fetch one immutable published trusted-profile version by id."""
        return self._lineage_store.get_trusted_profile_version(trusted_profile_version_id)

    def resolve_current_published_profile(
        self,
        profile_name: str | None = None,
    ) -> ResolvedPublishedTrustedProfile:
        """Resolve one logical profile to its persisted current published version for web processing."""
        organization = self._ensure_default_organization()
        resolved_profile_name = self._resolve_selected_profile_name(profile_name)
        trusted_profile = self._repair_trusted_profile_current_version(
            self._get_or_bootstrap_trusted_profile_by_name(
                organization_id=organization.organization_id,
                profile_name=resolved_profile_name,
            )
        )
        current_version_id = str(trusted_profile.current_published_version_id or "").strip()
        if not current_version_id:
            raise ValueError(
                f"Trusted profile '{resolved_profile_name}' does not have a current published version."
            )
        try:
            trusted_profile_version = self._lineage_store.get_trusted_profile_version(current_version_id)
        except KeyError as exc:
            raise ValueError(
                f"Trusted profile '{resolved_profile_name}' references missing published version "
                f"'{current_version_id}'."
            ) from exc
        return ResolvedPublishedTrustedProfile(
            organization=organization,
            trusted_profile=trusted_profile,
            trusted_profile_version=trusted_profile_version,
        )

    @contextmanager
    def materialize_published_version_bundle(
        self,
        trusted_profile_version: TrustedProfileVersion,
    ) -> Iterator[Path]:
        """Materialize one persisted published version into a temporary config bundle for processing."""
        with TemporaryDirectory(prefix="trusted-profile-version-") as temp_dir:
            materialized_dir = Path(temp_dir).resolve()
            self._write_materialized_bundle(materialized_dir, trusted_profile_version)
            yield materialized_dir

    def get_open_draft(self, trusted_profile_id: str) -> TrustedProfileDraft:
        """Fetch the single open draft for one logical trusted profile."""
        return self._lineage_store.get_open_trusted_profile_draft(trusted_profile_id)

    def get_draft(self, trusted_profile_draft_id: str) -> TrustedProfileDraft:
        """Fetch one mutable draft by id."""
        return self._lineage_store.get_trusted_profile_draft(trusted_profile_draft_id)

    def create_open_draft(
        self,
        trusted_profile_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> TrustedProfileDraft:
        """Create or reuse the single open draft copied from the current published version."""
        base_version = self.get_current_published_version(trusted_profile_id)
        created_at = self._now_provider()
        return self._lineage_store.get_or_create_trusted_profile_draft(
            TrustedProfileDraft(
                trusted_profile_draft_id=f"trusted-profile-draft:{trusted_profile_id}",
                organization_id=base_version.organization_id,
                trusted_profile_id=trusted_profile_id,
                base_trusted_profile_version_id=base_version.trusted_profile_version_id,
                bundle_payload=base_version.bundle_payload,
                canonical_bundle_json=base_version.canonical_bundle_json,
                content_hash=base_version.content_hash,
                template_artifact_id=base_version.template_artifact_id,
                template_artifact_ref=base_version.template_artifact_ref,
                template_file_hash=base_version.template_file_hash,
                created_by_user_id=created_by_user_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    def serialize_bundle_payload(
        self,
        bundle_payload: dict[str, object],
        *,
        template_artifact_ref: str | None,
        template_file_hash: str | None,
    ) -> tuple[dict[str, object], str, str]:
        """Return normalized bundle payload plus deterministic JSON and content hash."""
        canonical_bundle_json = json.dumps(bundle_payload, ensure_ascii=True)
        normalized_bundle_payload = json.loads(canonical_bundle_json)
        content_hash = hashlib.sha256(
            canonicalize_json(
                self._build_hash_payload(
                    bundle_payload=normalized_bundle_payload,
                    template_artifact_ref=template_artifact_ref,
                    template_file_hash=template_file_hash,
                )
            ).encode("utf-8")
        ).hexdigest()
        return normalized_bundle_payload, canonical_bundle_json, content_hash

    def save_draft_bundle(
        self,
        trusted_profile_draft_id: str,
        bundle_payload: dict[str, object],
    ) -> TrustedProfileDraft:
        """Persist one updated draft bundle with refreshed deterministic identity fields."""
        existing_draft = self.get_draft(trusted_profile_draft_id)
        normalized_bundle_payload, canonical_bundle_json, content_hash = self.serialize_bundle_payload(
            bundle_payload,
            template_artifact_ref=existing_draft.template_artifact_ref,
            template_file_hash=existing_draft.template_file_hash,
        )
        updated_draft = replace(
            existing_draft,
            bundle_payload=normalized_bundle_payload,
            canonical_bundle_json=canonical_bundle_json,
            content_hash=content_hash,
            updated_at=self._now_provider(),
        )
        return self._lineage_store.save_trusted_profile_draft(updated_draft)

    def publish_draft(
        self,
        trusted_profile_draft_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> TrustedProfileVersion:
        """Publish one validated draft into an immutable version and advance the current pointer."""
        draft = self.get_draft(trusted_profile_draft_id)
        trusted_profile = self.get_trusted_profile(draft.trusted_profile_id)
        normalized_bundle_payload, canonical_bundle_json, content_hash = self.serialize_bundle_payload(
            draft.bundle_payload,
            template_artifact_ref=draft.template_artifact_ref,
            template_file_hash=draft.template_file_hash,
        )
        existing_versions = self._lineage_store.list_trusted_profile_versions(trusted_profile.trusted_profile_id)
        equivalent_version = next(
            (version for version in existing_versions if version.content_hash == content_hash),
            None,
        )
        if equivalent_version is None:
            version_number = self._lineage_store.get_next_trusted_profile_version_number(
                trusted_profile.trusted_profile_id
            )
            equivalent_version = self._lineage_store.get_or_create_trusted_profile_version(
                TrustedProfileVersion(
                    trusted_profile_version_id=self._build_trusted_profile_version_id(
                        organization_id=trusted_profile.organization_id,
                        profile_name=trusted_profile.profile_name,
                        version_number=version_number,
                    ),
                    organization_id=trusted_profile.organization_id,
                    trusted_profile_id=trusted_profile.trusted_profile_id,
                    version_number=version_number,
                    bundle_payload=normalized_bundle_payload,
                    canonical_bundle_json=canonical_bundle_json,
                    content_hash=content_hash,
                    template_artifact_id=draft.template_artifact_id,
                    template_artifact_ref=draft.template_artifact_ref,
                    template_file_hash=draft.template_file_hash,
                    source_kind="published_from_draft",
                    base_trusted_profile_version_id=draft.base_trusted_profile_version_id,
                    created_by_user_id=created_by_user_id,
                    created_at=self._now_provider(),
                )
            )
        self._lineage_store.set_current_published_version(
            trusted_profile.trusted_profile_id,
            equivalent_version.trusted_profile_version_id,
        )
        self._lineage_store.delete_trusted_profile_draft(trusted_profile_draft_id)
        return equivalent_version

    def upsert_observation(
        self,
        observation: TrustedProfileObservation,
    ) -> TrustedProfileObservation:
        """Persist one observation keyed by profile/domain/raw key."""
        return self._lineage_store.upsert_trusted_profile_observation(observation)

    def get_observation(
        self,
        trusted_profile_id: str,
        observation_domain: str,
        canonical_raw_key: str,
    ) -> TrustedProfileObservation | None:
        """Fetch one observation when it already exists for a trusted profile/domain/key."""
        try:
            return self._lineage_store.get_trusted_profile_observation(
                trusted_profile_id,
                observation_domain,
                canonical_raw_key,
            )
        except KeyError:
            return None

    def list_observations(
        self,
        trusted_profile_id: str,
        *,
        observation_domain: str | None = None,
        unresolved_only: bool = False,
        unmerged_only: bool = False,
    ) -> list[TrustedProfileObservation]:
        """List persisted observations for one logical trusted profile."""
        return self._lineage_store.list_trusted_profile_observations(
            trusted_profile_id,
            observation_domain=observation_domain,
            unresolved_only=unresolved_only,
            unmerged_only=unmerged_only,
        )

    def mark_observation_draft_applied(
        self,
        trusted_profile_id: str,
        observation_domain: str,
        canonical_raw_key: str,
        *,
        applied_at: datetime | None = None,
    ) -> TrustedProfileObservation:
        """Record that an observation has been merged into the current open draft."""
        observation = self.get_observation(trusted_profile_id, observation_domain, canonical_raw_key)
        if observation is None:
            raise KeyError(
                f"TrustedProfileObservation '{trusted_profile_id}:{observation_domain}:{canonical_raw_key}' "
                "was not found."
            )
        return self.upsert_observation(
            replace(
                observation,
                draft_applied_at=applied_at or self._now_provider(),
            )
        )

    def mark_observation_resolved(
        self,
        trusted_profile_id: str,
        observation_domain: str,
        canonical_raw_key: str,
        *,
        resolved_at: datetime | None = None,
    ) -> TrustedProfileObservation:
        """Record that an observation is now resolved by trusted profile content."""
        observation = self.get_observation(trusted_profile_id, observation_domain, canonical_raw_key)
        if observation is None:
            raise KeyError(
                f"TrustedProfileObservation '{trusted_profile_id}:{observation_domain}:{canonical_raw_key}' "
                "was not found."
            )
        resolved_timestamp = resolved_at or self._now_provider()
        return self.upsert_observation(
            replace(
                observation,
                is_resolved=True,
                resolved_at=resolved_timestamp,
            )
        )

    def record_sync_export(
        self,
        sync_export: TrustedProfileSyncExport,
    ) -> TrustedProfileSyncExport:
        """Persist one sync-export audit record."""
        return self._lineage_store.create_trusted_profile_sync_export(sync_export)

    def get_sync_export(self, trusted_profile_sync_export_id: str) -> TrustedProfileSyncExport:
        """Fetch one persisted desktop-sync export audit record by id."""
        return self._lineage_store.get_trusted_profile_sync_export(trusted_profile_sync_export_id)

    def _get_or_bootstrap_trusted_profile_by_name(
        self,
        *,
        organization_id: str,
        profile_name: str,
    ) -> TrustedProfile:
        """Resolve one logical profile from persistence, seeding filesystem profiles only when absent."""
        try:
            return self._lineage_store.get_trusted_profile_by_name(
                organization_id=organization_id,
                profile_name=profile_name,
            )
        except KeyError:
            self.bootstrap_filesystem_profiles()
            return self._lineage_store.get_trusted_profile_by_name(
                organization_id=organization_id,
                profile_name=profile_name,
            )

    def _repair_trusted_profile_current_version(
        self,
        trusted_profile: TrustedProfile,
    ) -> TrustedProfile:
        """Repair incomplete bootstrap state for one logical trusted profile when needed."""
        current_version_id = str(trusted_profile.current_published_version_id or "").strip()
        if current_version_id:
            try:
                self._lineage_store.get_trusted_profile_version(current_version_id)
                return trusted_profile
            except KeyError:
                pass

        # Bootstrap is idempotent and already reuses equivalent versions by content hash, so it is
        # safe to use here to repair older local databases that have a logical profile row without a
        # current published version linkage.
        self.bootstrap_filesystem_profiles()
        return self._lineage_store.get_trusted_profile(trusted_profile.trusted_profile_id)

    def _materialize_filesystem_profile(
        self,
        *,
        organization: Organization,
        profile_metadata: dict[str, object],
        profile_dir: Path,
    ) -> MaterializedTrustedProfileBundle:
        """Load one filesystem profile into a persisted bundle payload plus template identity."""
        loader = ConfigLoader(
            config_dir=profile_dir.resolve(),
            legacy_config_dir=self._get_legacy_config_dir(),
        )
        profile_name = str(profile_metadata.get("profile_name") or "").strip()
        trusted_profile = self._lineage_store.get_or_create_trusted_profile(
            TrustedProfile(
                trusted_profile_id=f"trusted-profile:{organization.organization_id}:{profile_name}",
                organization_id=organization.organization_id,
                profile_name=profile_name,
                display_name=str(profile_metadata.get("display_name") or profile_name),
                source_kind="seeded" if profile_name.casefold() == "default" else "filesystem_bootstrap",
                bundle_ref=str(profile_dir),
                description=str(profile_metadata.get("description") or ""),
                version_label=str(profile_metadata.get("version") or "") or None,
                created_at=self._now_provider(),
            )
        )

        template_artifact, template_artifact_ref, template_file_hash = self._resolve_template_artifact(
            organization=organization,
            profile_dir=profile_dir,
            profile_metadata=profile_metadata,
            loader=loader,
        )
        bundle_payload = self._build_bundle_payload(
            profile_metadata=profile_metadata,
            loader=loader,
            template_artifact_ref=template_artifact_ref,
            template_file_hash=template_file_hash,
        )
        canonical_bundle_json = json.dumps(bundle_payload, ensure_ascii=True)
        content_hash = hashlib.sha256(
            canonicalize_json(
                self._build_hash_payload(
                    bundle_payload=bundle_payload,
                    template_artifact_ref=template_artifact_ref,
                    template_file_hash=template_file_hash,
                )
            ).encode("utf-8")
        ).hexdigest()
        return MaterializedTrustedProfileBundle(
            trusted_profile=trusted_profile,
            bundle_payload=json.loads(canonical_bundle_json),
            canonical_bundle_json=canonical_bundle_json,
            content_hash=content_hash,
            template_artifact_ref=template_artifact_ref,
            template_file_hash=template_file_hash,
            template_artifact=template_artifact,
        )

    def _resolve_template_artifact(
        self,
        *,
        organization: Organization,
        profile_dir: Path,
        profile_metadata: dict[str, object],
        loader: ConfigLoader,
    ) -> tuple[TemplateArtifact | None, str | None, str | None]:
        """Resolve one profile template into persisted identity fields."""
        template_path = self._resolve_template_path(profile_dir, profile_metadata, loader)
        if template_path is None:
            return None, None, None

        template_bytes = template_path.read_bytes()
        template_file_hash = hashlib.sha256(template_bytes).hexdigest()
        template_artifact = self._lineage_store.get_or_create_template_artifact(
            build_template_artifact(
                template_artifact_id=f"template-artifact:{organization.organization_id}:{template_file_hash}",
                organization_id=organization.organization_id,
                original_filename=template_path.name,
                content_bytes=template_bytes,
                created_at=self._now_provider(),
            )
        )
        return template_artifact, template_path.name, template_file_hash

    def _build_bundle_payload(
        self,
        *,
        profile_metadata: dict[str, object],
        loader: ConfigLoader,
        template_artifact_ref: str | None,
        template_file_hash: str | None,
    ) -> dict[str, object]:
        """Build the persisted trusted-profile bundle payload."""
        return {
            "behavioral_bundle": {
                "phase_mapping": loader.get_phase_mapping(),
                "labor_mapping": loader.get_labor_mapping(),
                "equipment_mapping": loader.get_equipment_mapping(),
                "vendor_normalization": loader.get_vendor_normalization(),
                "input_model": loader.get_input_model(),
                "review_rules": loader.get_review_rules(),
                "rates": loader.get_rates(),
                "labor_slots": loader.get_labor_slots(),
                "equipment_slots": loader.get_equipment_slots(),
                "recap_template_map": loader.get_recap_template_map(),
                "template": {
                    "template_artifact_ref": template_artifact_ref,
                    "template_file_hash": template_file_hash,
                    "template_filename": str(profile_metadata.get("template_filename") or "") or None,
                },
            },
            "traceability": {
                "trusted_profile": {
                    "profile_name": str(profile_metadata.get("profile_name") or ""),
                    "display_name": str(profile_metadata.get("display_name") or ""),
                    "description": str(profile_metadata.get("description") or ""),
                    "version": str(profile_metadata.get("version") or ""),
                    "template_filename": str(profile_metadata.get("template_filename") or ""),
                }
            },
        }

    def _build_hash_payload(
        self,
        *,
        bundle_payload: dict[str, object],
        template_artifact_ref: str | None,
        template_file_hash: str | None,
    ) -> dict[str, object]:
        """Build the deterministic version/draft hash payload including template identity."""
        behavioral_bundle = dict(bundle_payload.get("behavioral_bundle", {}))
        template_payload = dict(behavioral_bundle.get("template", {}))
        template_payload["template_artifact_ref"] = template_artifact_ref
        template_payload["template_file_hash"] = template_file_hash
        behavioral_bundle["template"] = template_payload
        return behavioral_bundle

    def _write_materialized_bundle(
        self,
        target_dir: Path,
        trusted_profile_version: TrustedProfileVersion,
    ) -> None:
        """Write a persisted published version back into the config bundle file layout used by processing."""
        bundle_payload = trusted_profile_version.bundle_payload
        behavioral_bundle = bundle_payload.get("behavioral_bundle", {})
        if not isinstance(behavioral_bundle, dict):
            raise ValueError(
                f"Trusted profile version '{trusted_profile_version.trusted_profile_version_id}' has invalid "
                "behavioral bundle payload."
            )

        traceability = bundle_payload.get("traceability", {})
        trusted_profile_trace = (
            traceability.get("trusted_profile", {}) if isinstance(traceability, dict) else {}
        )
        if not isinstance(trusted_profile_trace, dict):
            trusted_profile_trace = {}

        target_dir.mkdir(parents=True, exist_ok=True)
        profile_json = {
            "profile_name": str(trusted_profile_trace.get("profile_name") or ""),
            "display_name": str(trusted_profile_trace.get("display_name") or ""),
            "description": str(trusted_profile_trace.get("description") or ""),
            "version": str(trusted_profile_trace.get("version") or ""),
            "template_filename": self._resolve_materialized_template_filename(
                trusted_profile_version=trusted_profile_version,
                trusted_profile_trace=trusted_profile_trace,
                behavioral_bundle=behavioral_bundle,
            ),
            "is_active": False,
        }
        (target_dir / "profile.json").write_text(json.dumps(profile_json, indent=2), encoding="utf-8")

        for bundle_key, file_name in self._BUNDLE_FILE_MAP.items():
            payload = behavioral_bundle.get(bundle_key, {})
            normalized_payload = dict(payload) if isinstance(payload, dict) else {}
            (target_dir / file_name).write_text(
                json.dumps(normalized_payload, indent=2),
                encoding="utf-8",
            )

        template_artifact_id = str(trusted_profile_version.template_artifact_id or "").strip()
        if not template_artifact_id:
            raise FileNotFoundError(
                f"Trusted profile version '{trusted_profile_version.trusted_profile_version_id}' does not include "
                "a template artifact."
            )
        template_artifact = self._lineage_store.get_template_artifact(template_artifact_id)
        if not str(trusted_profile_version.template_file_hash or "").strip():
            raise ValueError(
                f"Trusted profile version '{trusted_profile_version.trusted_profile_version_id}' is missing "
                "template file hash identity."
            )
        if template_artifact.content_hash != trusted_profile_version.template_file_hash:
            raise ValueError(
                f"Trusted profile version '{trusted_profile_version.trusted_profile_version_id}' has a template "
                "artifact whose content hash does not match the recorded template file hash."
            )
        template_filename = str(profile_json["template_filename"]).strip() or template_artifact.original_filename
        (target_dir / template_filename).write_bytes(template_artifact.content_bytes)

    def _resolve_materialized_template_filename(
        self,
        *,
        trusted_profile_version: TrustedProfileVersion,
        trusted_profile_trace: dict[str, object],
        behavioral_bundle: dict[str, object],
    ) -> str:
        """Choose the stable template filename used when materializing a published bundle."""
        template_payload = behavioral_bundle.get("template", {})
        if not isinstance(template_payload, dict):
            template_payload = {}
        for candidate in (
            template_payload.get("template_filename"),
            trusted_profile_trace.get("template_filename"),
            trusted_profile_version.template_artifact_ref,
        ):
            candidate_text = str(candidate or "").strip()
            if candidate_text:
                return candidate_text
        if trusted_profile_version.template_artifact_id:
            return self._lineage_store.get_template_artifact(
                trusted_profile_version.template_artifact_id
            ).original_filename
        raise FileNotFoundError(
            f"Trusted profile version '{trusted_profile_version.trusted_profile_version_id}' is missing "
            "template filename metadata."
        )

    def _resolve_selected_profile_name(self, profile_name: str | None) -> str:
        """Normalize the selected profile name, falling back to the current active profile when needed."""
        resolved_profile_name = str(profile_name or "").strip()
        if resolved_profile_name:
            return resolved_profile_name
        active_profile_name = str(self._profile_manager.get_active_profile_name() or "").strip()
        if active_profile_name:
            return active_profile_name
        raise ValueError("A trusted profile name is required for published-version resolution.")

    def _resolve_template_path(
        self,
        profile_dir: Path,
        profile_metadata: dict[str, object],
        loader: ConfigLoader,
    ) -> Path | None:
        """Resolve the template workbook path for one filesystem profile when available."""
        template_filename = str(profile_metadata.get("template_filename") or "").strip()
        if template_filename:
            template_path = (profile_dir / template_filename).resolve()
            if template_path.is_file():
                return template_path

        recap_map = loader.get_recap_template_map()
        configured_path = str(recap_map.get("default_template_path") or "").strip()
        if configured_path:
            template_path = Path(configured_path).expanduser().resolve()
            if template_path.is_file():
                return template_path

        return None

    def _ensure_default_organization(self) -> Organization:
        """Ensure the single seeded organization boundary exists."""
        created_at = self._now_provider()
        return self._lineage_store.ensure_organization(
            organization_id="org-default",
            slug="default-org",
            display_name="Default Organization",
            created_at=created_at,
            is_seeded=True,
        )

    def _get_legacy_config_dir(self) -> Path | None:
        """Reuse the configured shared-config root when a custom profile manager is supplied."""
        legacy_config_dir = getattr(self._profile_manager, "_legacy_config_root", None)
        if isinstance(legacy_config_dir, Path):
            return legacy_config_dir
        return None

    def _build_trusted_profile_version_id(
        self,
        *,
        organization_id: str,
        profile_name: str,
        version_number: int,
    ) -> str:
        """Build a deterministic trusted-profile version id."""
        return f"trusted-profile-version:{organization_id}:{profile_name}:v{version_number}"
