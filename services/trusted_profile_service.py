"""Read-only trusted-profile listing for the phase-1 web workflow."""

from __future__ import annotations

from dataclasses import dataclass

from core.config import ProfileManager


@dataclass(frozen=True, slots=True)
class TrustedProfileSummary:
    """Minimal read-only trusted-profile metadata for web selection and inspection."""

    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None
    template_filename: str | None
    is_active_profile: bool


class TrustedProfileService:
    """Expose the available trusted profiles without expanding into profile management."""

    def __init__(self, profile_manager: ProfileManager | None = None) -> None:
        self._profile_manager = profile_manager or ProfileManager()

    def list_trusted_profiles(self) -> list[TrustedProfileSummary]:
        """Return read-only summaries for the available trusted profiles."""
        return [
            self._to_summary(profile_metadata)
            for profile_metadata in self._profile_manager.list_profiles()
        ]

    def _to_summary(self, profile_metadata: dict[str, object]) -> TrustedProfileSummary:
        """Normalize one profile metadata record into the phase-1 API shape."""
        profile_name = str(profile_metadata.get("profile_name") or "").strip()
        return TrustedProfileSummary(
            trusted_profile_id=f"trusted-profile:org-default:{profile_name}",
            profile_name=profile_name,
            display_name=str(profile_metadata.get("display_name") or profile_name),
            description=str(profile_metadata.get("description") or ""),
            version_label=str(profile_metadata.get("version") or "") or None,
            template_filename=str(profile_metadata.get("template_filename") or "") or None,
            is_active_profile=bool(profile_metadata.get("is_active_profile", False)),
        )
