"""Persistence-facing repository for trusted-profile records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable

from core.models.lineage import (
    TrustedProfile,
    TrustedProfileDraft,
    TrustedProfileObservation,
    TrustedProfileVersion,
)
from infrastructure.persistence import LineageStore
from services.lineage_service import canonicalize_json
from services.profile_authoring_errors import ProfileAuthoringPersistenceConflictError


class TrustedProfileAuthoringRepository:
    """Repository seam for persisted trusted-profile rows, versions, drafts, and observations."""

    def __init__(
        self,
        *,
        lineage_store: LineageStore,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def list_trusted_profiles(
        self,
        organization_id: str,
        *,
        include_archived: bool = False,
    ) -> list[TrustedProfile]:
        """List persisted trusted profiles for one organization."""
        return self._lineage_store.list_trusted_profiles_for_organization(
            organization_id,
            include_archived=include_archived,
        )

    def get_trusted_profile(self, organization_id: str, trusted_profile_id: str) -> TrustedProfile:
        """Fetch one persisted trusted profile by id."""
        return self._lineage_store.get_trusted_profile_for_organization(
            organization_id=organization_id,
            trusted_profile_id=trusted_profile_id,
        )

    def get_trusted_profile_by_name(
        self,
        organization_id: str,
        profile_name: str,
    ) -> TrustedProfile:
        """Fetch one persisted trusted profile by organization and stable name."""
        return self._lineage_store.get_trusted_profile_by_name(
            organization_id=organization_id,
            profile_name=profile_name,
        )

    def get_or_create_trusted_profile(self, trusted_profile: TrustedProfile) -> TrustedProfile:
        """Persist one trusted-profile row when it does not already exist."""
        return self._lineage_store.get_or_create_trusted_profile(trusted_profile)

    def set_current_published_version(
        self,
        trusted_profile_id: str,
        trusted_profile_version_id: str,
    ) -> TrustedProfile:
        """Advance one trusted profile's current published version pointer."""
        return self._lineage_store.set_current_published_version(
            trusted_profile_id,
            trusted_profile_version_id,
        )

    def get_current_published_version(
        self,
        organization_id: str,
        trusted_profile_id: str,
    ) -> TrustedProfileVersion:
        """Fetch the current published version for one persisted trusted profile."""
        trusted_profile = self.get_trusted_profile(organization_id, trusted_profile_id)
        current_version_id = str(trusted_profile.current_published_version_id or "").strip()
        if not current_version_id:
            raise ValueError(
                f"TrustedProfile '{trusted_profile.profile_name}' does not have a current published version."
            )
        try:
            return self._lineage_store.get_trusted_profile_version_for_organization(
                organization_id=organization_id,
                trusted_profile_version_id=current_version_id,
            )
        except KeyError as exc:
            raise ValueError(
                f"TrustedProfile '{trusted_profile.profile_name}' references missing published version "
                f"'{current_version_id}'."
            ) from exc

    def get_trusted_profile_version(
        self,
        organization_id: str,
        trusted_profile_version_id: str,
    ) -> TrustedProfileVersion:
        """Fetch one immutable published trusted-profile version by id."""
        return self._lineage_store.get_trusted_profile_version_for_organization(
            organization_id=organization_id,
            trusted_profile_version_id=trusted_profile_version_id,
        )

    def get_or_create_trusted_profile_version(
        self,
        trusted_profile_version: TrustedProfileVersion,
    ) -> TrustedProfileVersion:
        """Persist one published trusted-profile version when it does not already exist."""
        return self._lineage_store.get_or_create_trusted_profile_version(trusted_profile_version)

    def list_trusted_profile_versions(self, trusted_profile_id: str) -> list[TrustedProfileVersion]:
        """List persisted published versions for one trusted profile."""
        return self._lineage_store.list_trusted_profile_versions(trusted_profile_id)

    def get_next_trusted_profile_version_number(self, trusted_profile_id: str) -> int:
        """Return the next published version number for one trusted profile."""
        return self._lineage_store.get_next_trusted_profile_version_number(trusted_profile_id)

    def get_open_draft(self, organization_id: str, trusted_profile_id: str) -> TrustedProfileDraft:
        """Fetch the single open draft for one logical trusted profile."""
        return self._lineage_store.get_open_trusted_profile_draft_for_organization(
            organization_id=organization_id,
            trusted_profile_id=trusted_profile_id,
        )

    def get_draft(self, organization_id: str, trusted_profile_draft_id: str) -> TrustedProfileDraft:
        """Fetch one mutable draft by id."""
        return self._lineage_store.get_trusted_profile_draft_for_organization(
            organization_id=organization_id,
            trusted_profile_draft_id=trusted_profile_draft_id,
        )

    def create_open_draft(
        self,
        organization_id: str,
        trusted_profile_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> TrustedProfileDraft:
        """Create or reuse the single open draft copied from the current published version."""
        base_version = self.get_current_published_version(organization_id, trusted_profile_id)
        created_at = self._now_provider()
        return self._lineage_store.get_or_create_trusted_profile_draft(
            TrustedProfileDraft(
                trusted_profile_draft_id=f"trusted-profile-draft:{trusted_profile_id}",
                organization_id=base_version.organization_id,
                trusted_profile_id=trusted_profile_id,
                draft_revision=1,
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

    def archive_trusted_profile(self, organization_id: str, trusted_profile_id: str) -> TrustedProfile:
        """Archive one logical trusted profile without deleting published lineage."""
        trusted_profile = self.get_trusted_profile(organization_id, trusted_profile_id)
        if trusted_profile.archived_at is not None:
            return trusted_profile
        return self._lineage_store.archive_trusted_profile(
            trusted_profile_id,
            archived_at=self._now_provider(),
        )

    def unarchive_trusted_profile(self, organization_id: str, trusted_profile_id: str) -> TrustedProfile:
        """Restore one archived logical trusted profile to the active settings lists."""
        trusted_profile = self.get_trusted_profile(organization_id, trusted_profile_id)
        if trusted_profile.archived_at is None:
            return trusted_profile
        return self._lineage_store.unarchive_trusted_profile(trusted_profile_id)

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
        organization_id: str,
        trusted_profile_draft_id: str,
        bundle_payload: dict[str, object],
        *,
        expected_draft_revision: int,
    ) -> TrustedProfileDraft:
        """Persist one updated draft bundle with refreshed deterministic identity fields."""
        existing_draft = self.get_draft(organization_id, trusted_profile_draft_id)
        if existing_draft.draft_revision != expected_draft_revision:
            raise ProfileAuthoringPersistenceConflictError(
                f"Trusted profile draft '{trusted_profile_draft_id}' has stale revision {expected_draft_revision}.",
                field_errors={
                    "expected_draft_revision": [
                        "Refresh the draft and retry with the latest revision before saving.",
                    ]
                },
            )
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
            draft_revision=expected_draft_revision + 1,
            updated_at=self._now_provider(),
        )
        return self._lineage_store.save_trusted_profile_draft(
            updated_draft,
            expected_draft_revision=expected_draft_revision,
        )

    def publish_draft(
        self,
        organization_id: str,
        trusted_profile_draft_id: str,
        *,
        expected_draft_revision: int,
        created_by_user_id: str | None = None,
    ) -> TrustedProfileVersion:
        """Publish one validated draft into an immutable version and advance the current pointer."""
        try:
            draft = self.get_draft(organization_id, trusted_profile_draft_id)
        except KeyError as exc:
            if not self._draft_id_matches_organization(trusted_profile_draft_id, organization_id):
                raise
            raise ProfileAuthoringPersistenceConflictError(
                f"Trusted profile draft '{trusted_profile_draft_id}' could not be published because it is stale.",
                field_errors={
                    "expected_draft_revision": [
                        "Refresh the draft and retry with the latest revision before publishing.",
                    ]
                },
            ) from exc
        normalized_bundle_payload, canonical_bundle_json, content_hash = self.serialize_bundle_payload(
            draft.bundle_payload,
            template_artifact_ref=draft.template_artifact_ref,
            template_file_hash=draft.template_file_hash,
        )
        return self._lineage_store.publish_trusted_profile_draft(
            organization_id=organization_id,
            trusted_profile_draft_id=trusted_profile_draft_id,
            expected_draft_revision=expected_draft_revision,
            canonical_bundle_json=canonical_bundle_json,
            content_hash=content_hash,
            template_artifact_id=draft.template_artifact_id,
            template_artifact_ref=draft.template_artifact_ref,
            template_file_hash=draft.template_file_hash,
            created_by_user_id=created_by_user_id,
            created_at=self._now_provider(),
        )

    def discard_draft(self, organization_id: str, trusted_profile_draft_id: str) -> None:
        """Discard one mutable draft without affecting published lineage."""
        self.get_draft(organization_id, trusted_profile_draft_id)
        self._lineage_store.delete_trusted_profile_draft(trusted_profile_draft_id)

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

    @staticmethod
    def _draft_id_matches_organization(trusted_profile_draft_id: str, organization_id: str) -> bool:
        """Return whether one trusted-profile draft id is shaped like it belongs to one organization."""
        return trusted_profile_draft_id.startswith(
            f"trusted-profile-draft:trusted-profile:{organization_id}:"
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
