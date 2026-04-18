"""Read-only trusted-profile listing for the phase-1 web workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.request_context import RequestContext
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository
from services.trusted_profile_provisioning_service import TrustedProfileProvisioningService


@dataclass(frozen=True, slots=True)
class TrustedProfileSummary:
    """Minimal read-only trusted-profile metadata for web selection and inspection."""

    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None
    template_filename: str | None
    source_kind: str
    current_published_version_number: int
    has_open_draft: bool
    is_active_profile: bool
    archived_at: datetime | None = None


class TrustedProfileService:
    """Expose the available trusted profiles without expanding into profile management."""

    def __init__(
        self,
        *,
        repository: TrustedProfileAuthoringRepository,
        trusted_profile_provisioning_service: TrustedProfileProvisioningService,
    ) -> None:
        self._repository = repository
        self._trusted_profile_provisioning_service = trusted_profile_provisioning_service

    def list_trusted_profiles(
        self,
        *,
        include_archived: bool = False,
        request_context: RequestContext | None = None,
    ) -> list[TrustedProfileSummary]:
        """Return read-only summaries for the available trusted profiles."""
        active_profile_name = self._trusted_profile_provisioning_service.get_selected_profile_name(
            request_context=request_context
        )
        return [
            self._to_summary(
                profile,
                active_profile_name,
                request_context=request_context,
            )
            for profile in self._trusted_profile_provisioning_service.list_trusted_profiles(
                include_archived=include_archived,
                request_context=request_context,
            )
        ]

    def _to_summary(
        self,
        trusted_profile,
        active_profile_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> TrustedProfileSummary:
        """Normalize one persisted trusted profile into the phase-1 API shape."""
        current_published_version = self._trusted_profile_provisioning_service.get_current_published_version(
            trusted_profile.trusted_profile_id,
            request_context=request_context,
        )
        behavioral_bundle = current_published_version.bundle_payload.get("behavioral_bundle", {})
        template_payload = behavioral_bundle.get("template", {}) if isinstance(behavioral_bundle, dict) else {}
        return TrustedProfileSummary(
            trusted_profile_id=trusted_profile.trusted_profile_id,
            profile_name=trusted_profile.profile_name,
            display_name=trusted_profile.display_name,
            description=trusted_profile.description,
            version_label=trusted_profile.version_label,
            template_filename=str(template_payload.get("template_filename") or "") or None,
            source_kind=trusted_profile.source_kind,
            current_published_version_number=current_published_version.version_number,
            has_open_draft=self._has_open_draft(
                trusted_profile.organization_id,
                trusted_profile.trusted_profile_id,
            ),
            is_active_profile=trusted_profile.profile_name == active_profile_name,
            archived_at=trusted_profile.archived_at,
        )

    def _has_open_draft(self, organization_id: str, trusted_profile_id: str) -> bool:
        """Return whether one logical trusted profile currently has an open draft."""
        try:
            self._repository.get_open_draft(organization_id, trusted_profile_id)
            return True
        except KeyError:
            return False
