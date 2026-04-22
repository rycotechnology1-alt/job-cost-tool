"""Export API contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.schemas.common import ApiModel


class ExportCreateRequest(ApiModel):
    """Request body for generating one export from an exact review-session revision."""

    session_revision: int = Field(ge=0)


class ExportArtifactResponse(ApiModel):
    """Metadata returned after generating one exact-revision export artifact."""

    export_artifact_id: str
    session_revision: int
    artifact_kind: str
    file_hash: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    download_url: str
