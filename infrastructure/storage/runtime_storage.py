"""Storage contracts for phase-1 uploaded source documents and export artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredUpload:
    """Uploaded source document stored for later processing-run creation."""

    upload_id: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    storage_ref: str
    file_path: Path
    created_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Persisted export artifact resolved through the runtime storage seam."""

    storage_ref: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    file_path: Path


@dataclass(frozen=True, slots=True)
class StoredSourceDocument:
    """Durable source document resolved through the runtime storage seam."""

    storage_ref: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    file_path: Path


class ExpiredUploadError(FileNotFoundError):
    """Raised when a cached upload expired and must be uploaded again."""


class RuntimeStorage(Protocol):
    """Storage seam for uploaded source documents and generated export artifacts."""

    def save_upload(
        self,
        *,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredUpload:
        """Persist one uploaded source document and return its runtime reference."""

    def get_upload(self, upload_id: str) -> StoredUpload:
        """Resolve one uploaded source document by upload id."""

    def save_source_document(
        self,
        *,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredSourceDocument:
        """Persist one durable source document and return its runtime reference."""

    def get_source_document(self, storage_ref: str) -> StoredSourceDocument:
        """Resolve one durable source document by storage reference."""

    def register_blob_upload(
        self,
        *,
        storage_ref: str,
        original_filename: str,
        content_type: str,
        file_size_bytes: int,
    ) -> StoredUpload:
        """Register one upload that was already written to shared blob storage."""

    def cleanup_expired_uploads(self) -> int:
        """Delete expired uploaded source documents and return the number removed."""

    def save_export_artifact(
        self,
        *,
        processing_run_id: str,
        session_revision: int,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredArtifact:
        """Persist one generated export artifact and return its runtime reference."""

    def get_export_artifact(self, storage_ref: str) -> StoredArtifact:
        """Resolve one previously stored export artifact by storage reference."""

    def delete_export_artifact(self, storage_ref: str) -> None:
        """Delete one previously stored export artifact by storage reference."""
