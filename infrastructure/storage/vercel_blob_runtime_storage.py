"""Shared Vercel Blob-backed runtime storage for hosted uploads and artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol
from uuid import uuid4

from .runtime_storage import ExpiredUploadError, RuntimeStorage, StoredArtifact, StoredUpload


class BlobObjectClient(Protocol):
    """Minimal shared-blob client used by the hosted runtime storage adapter."""

    def put_bytes(
        self,
        *,
        pathname: str,
        content_bytes: bytes,
        content_type: str,
    ) -> None:
        """Persist one blob object by pathname."""

    def get_bytes(self, pathname: str) -> bytes:
        """Load one blob object by pathname."""

    def delete_path(self, pathname: str) -> None:
        """Delete one blob object by pathname when it exists."""

    def list_paths(self, *, prefix: str) -> list[str]:
        """List stored blob pathnames by prefix."""


class VercelBlobObjectClient:
    """Small wrapper around the Vercel Blob Python SDK."""

    def __init__(self, *, read_write_token: str) -> None:
        token = str(read_write_token or "").strip()
        if not token:
            raise ValueError("BLOB_READ_WRITE_TOKEN is required when storage_provider=vercel_blob.")
        self._token = token

    def put_bytes(
        self,
        *,
        pathname: str,
        content_bytes: bytes,
        content_type: str,
    ) -> None:
        blob = self._blob_module()
        blob.put(
            pathname,
            content_bytes,
            access="private",
            content_type=content_type,
            add_random_suffix=False,
            overwrite=True,
            token=self._token,
        )

    def get_bytes(self, pathname: str) -> bytes:
        blob = self._blob_module()
        result = blob.get(
            pathname,
            access="private",
            token=self._token,
            use_cache=False,
        )
        content = result.content
        if isinstance(content, bytes):
            return content
        return bytes(content)

    def delete_path(self, pathname: str) -> None:
        blob = self._blob_module()
        blob.delete(pathname, token=self._token)

    def list_paths(self, *, prefix: str) -> list[str]:
        blob = self._blob_module()
        cursor: str | None = None
        collected_paths: list[str] = []
        while True:
            result = blob.list_objects(prefix=prefix, cursor=cursor, token=self._token)
            collected_paths.extend(item.pathname for item in result.blobs)
            if not result.has_more:
                break
            cursor = result.cursor
        return collected_paths

    def _blob_module(self):
        try:
            from vercel import blob
        except ImportError as exc:  # pragma: no cover - exercised by runtime configuration
            raise RuntimeError(
                "The 'vercel' package is required when storage_provider=vercel_blob."
            ) from exc
        return blob


class VercelBlobRuntimeStorage(RuntimeStorage):
    """Persist hosted uploads and artifacts in shared Vercel Blob storage."""

    def __init__(
        self,
        *,
        blob_client: BlobObjectClient | None = None,
        read_write_token: str | None = None,
        upload_root: str | Path,
        export_root: str | Path,
        upload_retention_hours: int | float = 24,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._blob_client = blob_client or VercelBlobObjectClient(
            read_write_token=str(read_write_token or "").strip()
        )
        self._upload_root = Path(upload_root).expanduser().resolve()
        self._export_root = Path(export_root).expanduser().resolve()
        self._upload_retention_hours = float(upload_retention_hours)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._upload_root.mkdir(parents=True, exist_ok=True)
        self._export_root.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self,
        *,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredUpload:
        """Persist one uploaded source document in shared blob storage."""
        filename = self._normalize_filename(original_filename)
        if not content_bytes:
            raise ValueError("Uploaded source document must not be empty.")

        upload_id = uuid4().hex
        storage_ref = f"uploads/{upload_id}/{filename}"
        created_at = self._normalize_timestamp(self._now_provider())
        metadata = {
            "upload_id": upload_id,
            "original_filename": filename,
            "content_type": str(content_type or "application/octet-stream"),
            "file_size_bytes": len(content_bytes),
            "storage_ref": storage_ref,
            "filename": filename,
            "created_at": created_at.isoformat(),
            "expires_at": self._expires_at(created_at).isoformat() if self._upload_retention_hours > 0 else None,
        }
        self._blob_client.put_bytes(
            pathname=storage_ref,
            content_bytes=content_bytes,
            content_type=metadata["content_type"],
        )
        self._write_metadata_blob(
            pathname=self._metadata_path_for_upload(upload_id),
            metadata=metadata,
        )
        file_path = self._materialize_cache_file(
            root=self._upload_root,
            pathname=storage_ref,
            content_bytes=content_bytes,
            metadata=metadata,
        )
        return StoredUpload(
            upload_id=upload_id,
            original_filename=filename,
            content_type=metadata["content_type"],
            file_size_bytes=len(content_bytes),
            storage_ref=storage_ref,
            file_path=file_path,
            created_at=created_at,
        )

    def get_upload(self, upload_id: str) -> StoredUpload:
        """Resolve one previously uploaded source document by upload id."""
        normalized_upload_id = str(upload_id or "").strip()
        if not normalized_upload_id:
            raise ValueError("upload_id is required.")

        metadata = self._read_metadata_blob(self._metadata_path_for_upload(normalized_upload_id))
        created_at = self._metadata_timestamp(metadata, "created_at")
        if self._is_upload_expired(metadata):
            self._delete_cached_path(self._upload_root, str(metadata["storage_ref"]))
            raise ExpiredUploadError(
                "The uploaded PDF expired from temporary storage. Reselect and upload the PDF again before processing."
            )
        content_bytes = self._blob_client.get_bytes(str(metadata["storage_ref"]))
        file_path = self._materialize_cache_file(
            root=self._upload_root,
            pathname=str(metadata["storage_ref"]),
            content_bytes=content_bytes,
            metadata=metadata,
        )
        return StoredUpload(
            upload_id=str(metadata["upload_id"]),
            original_filename=str(metadata["original_filename"]),
            content_type=str(metadata["content_type"]),
            file_size_bytes=int(metadata["file_size_bytes"]),
            storage_ref=str(metadata["storage_ref"]),
            file_path=file_path,
            created_at=created_at,
        )

    def register_blob_upload(
        self,
        *,
        storage_ref: str,
        original_filename: str,
        content_type: str,
        file_size_bytes: int,
    ) -> StoredUpload:
        """Register one browser-uploaded source document already stored in shared blob storage."""
        normalized_storage_ref = self._normalize_storage_ref(storage_ref, expected_prefix="uploads/")
        filename = self._normalize_filename(original_filename)
        if Path(normalized_storage_ref).suffix.lower() != ".pdf":
            raise ValueError("Blob upload registration only supports PDF files.")
        if str(content_type or "").strip().lower() != "application/pdf":
            raise ValueError("Blob upload registration only supports application/pdf content.")
        if int(file_size_bytes) <= 0:
            raise ValueError("Blob upload registration requires a positive file size.")

        storage_ref_parts = Path(normalized_storage_ref).parts
        if len(storage_ref_parts) < 3:
            raise FileNotFoundError(f"Storage reference '{storage_ref}' was not found.")
        if storage_ref_parts[-1] != filename:
            raise ValueError("Blob upload registration filename must match the storage reference.")

        content_bytes = self._blob_client.get_bytes(normalized_storage_ref)
        if not self._is_pdf_bytes(content_bytes):
            raise ValueError("Blob upload registration requires a real PDF payload.")

        upload_id = storage_ref_parts[1]
        created_at = self._normalize_timestamp(self._now_provider())
        metadata = {
            "upload_id": upload_id,
            "original_filename": filename,
            "content_type": "application/pdf",
            "file_size_bytes": len(content_bytes),
            "storage_ref": normalized_storage_ref,
            "filename": filename,
            "created_at": created_at.isoformat(),
            "expires_at": self._expires_at(created_at).isoformat() if self._upload_retention_hours > 0 else None,
        }
        self._write_metadata_blob(
            pathname=self._metadata_path_for_upload(upload_id),
            metadata=metadata,
        )
        return StoredUpload(
            upload_id=upload_id,
            original_filename=filename,
            content_type=metadata["content_type"],
            file_size_bytes=len(content_bytes),
            storage_ref=normalized_storage_ref,
            file_path=self._upload_root / Path(normalized_storage_ref),
            created_at=created_at,
        )

    def cleanup_expired_uploads(self) -> int:
        """Delete expired uploaded source documents from shared blob storage explicitly."""
        deleted_count = 0
        for metadata_path in self._blob_client.list_paths(prefix="uploads/"):
            if not metadata_path.endswith("/metadata.json"):
                continue
            try:
                metadata = self._read_metadata_blob(metadata_path)
            except FileNotFoundError:
                continue
            if not self._is_upload_expired(metadata):
                continue
            self._blob_client.delete_path(str(metadata["storage_ref"]))
            self._blob_client.delete_path(metadata_path)
            self._delete_cached_path(self._upload_root, str(metadata["storage_ref"]))
            deleted_count += 1
        return deleted_count

    def save_export_artifact(
        self,
        *,
        processing_run_id: str,
        session_revision: int,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredArtifact:
        """Persist one export artifact in shared blob storage."""
        filename = self._normalize_filename(original_filename) or "recap-export.xlsx"
        if not content_bytes:
            raise ValueError("Export artifact content_bytes must not be empty.")
        if session_revision < 0:
            raise ValueError("session_revision must be greater than or equal to 0.")

        sanitized_run_id = self._sanitize_identifier(processing_run_id, field_name="processing_run_id")
        artifact_id = uuid4().hex
        storage_ref = f"exports/{sanitized_run_id}/{artifact_id}/{filename}"
        metadata = {
            "processing_run_id": str(processing_run_id),
            "session_revision": session_revision,
            "original_filename": filename,
            "content_type": str(
                content_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "file_size_bytes": len(content_bytes),
            "storage_ref": storage_ref,
            "filename": filename,
        }
        self._blob_client.put_bytes(
            pathname=storage_ref,
            content_bytes=content_bytes,
            content_type=metadata["content_type"],
        )
        self._write_metadata_blob(
            pathname=self._metadata_path_for_storage_ref(storage_ref),
            metadata=metadata,
        )
        file_path = self._materialize_cache_file(
            root=self._export_root,
            pathname=storage_ref,
            content_bytes=content_bytes,
            metadata=metadata,
        )
        return StoredArtifact(
            storage_ref=storage_ref,
            original_filename=filename,
            content_type=metadata["content_type"],
            file_size_bytes=len(content_bytes),
            file_path=file_path,
        )

    def get_export_artifact(self, storage_ref: str) -> StoredArtifact:
        """Resolve one export artifact from shared blob storage."""
        return self._get_artifact(
            storage_ref=storage_ref,
            expected_prefix="exports/",
        )

    def delete_export_artifact(self, storage_ref: str) -> None:
        """Delete one export artifact from shared blob storage and any local cache copy."""
        normalized_storage_ref = self._normalize_storage_ref(storage_ref, expected_prefix="exports/")
        self._blob_client.delete_path(normalized_storage_ref)
        self._blob_client.delete_path(self._metadata_path_for_storage_ref(normalized_storage_ref))
        self._delete_cached_path(self._export_root, normalized_storage_ref)

    def _get_artifact(
        self,
        *,
        storage_ref: str,
        expected_prefix: str,
    ) -> StoredArtifact:
        normalized_storage_ref = self._normalize_storage_ref(storage_ref, expected_prefix=expected_prefix)
        metadata = self._read_metadata_blob(self._metadata_path_for_storage_ref(normalized_storage_ref))
        content_bytes = self._blob_client.get_bytes(normalized_storage_ref)
        file_path = self._materialize_cache_file(
            root=self._export_root,
            pathname=normalized_storage_ref,
            content_bytes=content_bytes,
            metadata=metadata,
        )
        return StoredArtifact(
            storage_ref=str(metadata["storage_ref"]),
            original_filename=str(metadata["original_filename"]),
            content_type=str(metadata["content_type"]),
            file_size_bytes=int(metadata["file_size_bytes"]),
            file_path=file_path,
        )

    def _write_metadata_blob(
        self,
        *,
        pathname: str,
        metadata: dict[str, object],
    ) -> None:
        self._blob_client.put_bytes(
            pathname=pathname,
            content_bytes=json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )

    def _read_metadata_blob(self, pathname: str) -> dict[str, object]:
        payload = self._blob_client.get_bytes(pathname)
        metadata = json.loads(payload.decode("utf-8"))
        if not isinstance(metadata, dict):
            raise FileNotFoundError(pathname)
        return metadata

    def _materialize_cache_file(
        self,
        *,
        root: Path,
        pathname: str,
        content_bytes: bytes,
        metadata: dict[str, object],
    ) -> Path:
        cache_file_path = (root / Path(pathname)).resolve()
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        cache_file_path.write_bytes(content_bytes)
        metadata_path = cache_file_path.parent / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return cache_file_path

    def _delete_cached_path(self, root: Path, pathname: str) -> None:
        cache_file_path = (root / Path(pathname)).resolve()
        try:
            cache_file_path.relative_to(root)
        except ValueError:
            return
        if cache_file_path.exists():
            cache_file_path.unlink(missing_ok=True)
        metadata_path = cache_file_path.parent / "metadata.json"
        metadata_path.unlink(missing_ok=True)
        current_dir = cache_file_path.parent
        while current_dir != root and current_dir.exists():
            if any(current_dir.iterdir()):
                break
            current_dir.rmdir()
            current_dir = current_dir.parent

    def _metadata_path_for_upload(self, upload_id: str) -> str:
        return f"uploads/{upload_id}/metadata.json"

    def _metadata_path_for_storage_ref(self, storage_ref: str) -> str:
        normalized_storage_ref = str(storage_ref or "").replace("\\", "/").strip().strip("/")
        storage_ref_parts = Path(normalized_storage_ref).parts
        if len(storage_ref_parts) < 3:
            raise FileNotFoundError(f"Storage reference '{storage_ref}' was not found.")
        return "/".join((*storage_ref_parts[:-1], "metadata.json"))

    def _normalize_filename(self, original_filename: str) -> str:
        filename = Path(str(original_filename or "").strip()).name
        return filename or "source-document.pdf"

    def _normalize_storage_ref(self, storage_ref: str, *, expected_prefix: str) -> str:
        normalized_storage_ref = str(storage_ref or "").replace("\\", "/").strip().strip("/")
        if not normalized_storage_ref.startswith(expected_prefix.strip("/")):
            raise FileNotFoundError(f"Storage reference '{storage_ref}' was not found.")
        return normalized_storage_ref

    def _is_pdf_bytes(self, content_bytes: bytes) -> bool:
        return bool(content_bytes) and content_bytes.startswith(b"%PDF-")

    def _sanitize_identifier(self, raw_identifier: str, *, field_name: str) -> str:
        sanitized_identifier = str(raw_identifier).replace(":", "-").replace("/", "-").strip()
        if not sanitized_identifier:
            raise ValueError(f"{field_name} is required for artifact storage.")
        return sanitized_identifier

    def _metadata_timestamp(self, metadata: dict[str, object], field_name: str) -> datetime:
        raw_value = str(metadata.get(field_name) or "").strip()
        if not raw_value:
            raise FileNotFoundError(field_name)
        return self._normalize_timestamp(datetime.fromisoformat(raw_value))

    def _expires_at(self, created_at: datetime) -> datetime:
        return created_at + timedelta(hours=self._upload_retention_hours)

    def _is_upload_expired(self, metadata: dict[str, object]) -> bool:
        if self._upload_retention_hours <= 0:
            return False
        raw_expires_at = str(metadata.get("expires_at") or "").strip()
        if raw_expires_at:
            expires_at = self._normalize_timestamp(datetime.fromisoformat(raw_expires_at))
        else:
            expires_at = self._expires_at(self._metadata_timestamp(metadata, "created_at"))
        return self._normalize_timestamp(self._now_provider()) >= expires_at

    def _normalize_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
