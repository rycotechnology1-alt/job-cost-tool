"""Trusted-profile API contracts."""

from __future__ import annotations

from datetime import datetime

from api.schemas.common import ApiModel


class TrustedProfileResponse(ApiModel):
    """Read-only trusted-profile metadata for phase-1 browser selection."""

    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None = None
    template_filename: str | None = None
    source_kind: str
    current_published_version_number: int
    has_open_draft: bool
    is_active_profile: bool
    archived_at: datetime | None = None
