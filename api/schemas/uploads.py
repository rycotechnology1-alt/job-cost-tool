"""Source-document upload API contracts."""

from __future__ import annotations

from datetime import datetime

from api.schemas.common import ApiModel


class SourceUploadResponse(ApiModel):
    """Metadata returned after persisting one uploaded source document."""

    upload_id: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    storage_ref: str
    expires_at: datetime | None


class BlobUploadRegistrationRequest(ApiModel):
    """Metadata for one PDF already uploaded directly to blob storage."""

    storage_ref: str
    original_filename: str
    content_type: str
    file_size_bytes: int
