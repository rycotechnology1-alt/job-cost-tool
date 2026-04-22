"""Local file storage helpers for uploaded source documents and exported workbooks."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .runtime_storage import ExpiredUploadError, RuntimeStorage, StoredArtifact, StoredUpload


class LocalRuntimeFileStore(RuntimeStorage):
    """Persist uploaded source documents and export outputs on local disk."""

    def __init__(
        self,
        *,
        upload_root: str | Path,
        export_root: str | Path,
        export_retention_hours: int | float = 24,
        upload_retention_hours: int | float = 24,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._upload_root = Path(upload_root).expanduser().resolve()
        self._export_root = Path(export_root).expanduser().resolve()
        self._export_retention_hours = float(export_retention_hours)
        self._upload_retention_hours = float(upload_retention_hours)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._upload_root.mkdir(parents=True, exist_ok=True)
        self._export_root.mkdir(parents=True, exist_ok=True)
        self.cleanup_expired_uploads()
        self.cleanup_expired_export_artifacts()

    def save_upload(
        self,
        *,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredUpload:
        """Persist one uploaded source document and return its stable local reference."""
        self.cleanup_expired_uploads()
        filename = self._normalize_filename(original_filename)
        if not content_bytes:
            raise ValueError("Uploaded source document must not be empty.")

        upload_id = uuid4().hex
        upload_dir = self._upload_root / upload_id
        upload_dir.mkdir(parents=True, exist_ok=False)
        file_path = (upload_dir / filename).resolve()
        file_path.write_bytes(content_bytes)
        created_at = self._normalize_timestamp(self._now_provider())

        metadata = {
            "upload_id": upload_id,
            "original_filename": filename,
            "content_type": str(content_type or "application/octet-stream"),
            "file_size_bytes": len(content_bytes),
            "storage_ref": f"uploads/{upload_id}/{filename}",
            "filename": filename,
            "created_at": created_at.isoformat(),
        }
        (upload_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return StoredUpload(
            upload_id=upload_id,
            original_filename=filename,
            content_type=metadata["content_type"],
            file_size_bytes=len(content_bytes),
            storage_ref=metadata["storage_ref"],
            file_path=file_path,
            created_at=created_at,
        )

    def get_upload(self, upload_id: str) -> StoredUpload:
        """Load one previously uploaded source document by its local runtime id."""
        normalized_upload_id = str(upload_id or "").strip()
        if not normalized_upload_id:
            raise ValueError("upload_id is required.")

        upload_dir = (self._upload_root / normalized_upload_id).resolve()
        metadata_path = upload_dir / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Uploaded source document '{normalized_upload_id}' was not found.")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        upload_created_at = self._resolve_upload_created_at(upload_dir, metadata)
        if self._is_expired(upload_created_at):
            self._delete_upload_dir(upload_dir)
            raise ExpiredUploadError(
                "The uploaded PDF expired from temporary storage. Reselect and upload the PDF again before processing."
            )
        file_path = (upload_dir / str(metadata["filename"])).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Uploaded source document payload is missing for '{normalized_upload_id}'.")

        self.cleanup_expired_uploads()
        return StoredUpload(
            upload_id=str(metadata["upload_id"]),
            original_filename=str(metadata["original_filename"]),
            content_type=str(metadata["content_type"]),
            file_size_bytes=int(metadata["file_size_bytes"]),
            storage_ref=str(metadata["storage_ref"]),
            file_path=file_path,
            created_at=upload_created_at,
        )

    def register_blob_upload(
        self,
        *,
        storage_ref: str,
        original_filename: str,
        content_type: str,
        file_size_bytes: int,
    ) -> StoredUpload:
        """Reject direct blob registration when the runtime uses local storage."""
        raise NotImplementedError(
            "Blob upload registration is only supported when storage_provider=vercel_blob."
        )

    def cleanup_expired_uploads(self) -> int:
        """Delete expired uploaded source documents from the temporary runtime cache."""
        if self._upload_retention_hours <= 0:
            return 0

        deleted_count = 0
        for upload_dir in self._upload_root.iterdir():
            if not upload_dir.is_dir():
                continue
            try:
                created_at = self._resolve_upload_created_at(upload_dir)
            except Exception:
                created_at = self._fallback_created_at(upload_dir)
            if self._is_expired(created_at):
                self._delete_upload_dir(upload_dir)
                deleted_count += 1
        return deleted_count

    def cleanup_expired_export_artifacts(self) -> int:
        """Delete expired export artifacts from the temporary runtime cache."""
        if self._export_retention_hours <= 0:
            return 0

        deleted_count = 0
        for metadata_path in self._export_root.rglob("metadata.json"):
            artifact_dir = metadata_path.parent
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
            created_at = self._resolve_runtime_created_at(
                artifact_dir,
                metadata,
            )
            if self._is_export_expired(created_at, metadata=metadata):
                self._delete_runtime_dir(self._export_root, artifact_dir)
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
        """Persist one generated export artifact and return its stable runtime reference."""
        filename = self._normalize_filename(original_filename) or "recap-export.xlsx"
        if not content_bytes:
            raise ValueError("Export artifact content_bytes must not be empty.")
        if session_revision < 0:
            raise ValueError("session_revision must be greater than or equal to 0.")

        sanitized_run_id = self._sanitize_processing_run_id(processing_run_id)
        artifact_id = uuid4().hex
        export_dir = (self._export_root / sanitized_run_id / artifact_id).resolve()
        export_dir.mkdir(parents=True, exist_ok=False)
        file_path = (export_dir / filename).resolve()
        file_path.write_bytes(content_bytes)
        created_at = self._normalize_timestamp(self._now_provider())
        expires_at = (
            created_at + timedelta(hours=self._export_retention_hours)
            if self._export_retention_hours > 0
            else None
        )

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
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        (export_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return StoredArtifact(
            storage_ref=storage_ref,
            original_filename=filename,
            content_type=str(metadata["content_type"]),
            file_size_bytes=len(content_bytes),
            file_path=file_path,
            created_at=created_at,
            expires_at=expires_at,
        )

    def get_export_artifact(self, storage_ref: str) -> StoredArtifact:
        """Resolve one previously stored export artifact by storage reference."""
        export_dir = self._resolve_storage_ref_dir(
            root=self._export_root,
            storage_ref=storage_ref,
            expected_prefix="exports/",
        )
        metadata_path = export_dir / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Export artifact '{storage_ref}' was not found.")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        created_at = self._resolve_runtime_created_at(export_dir, metadata)
        if self._is_export_expired(created_at, metadata=metadata):
            self._delete_runtime_dir(self._export_root, export_dir)
            raise FileNotFoundError(f"Export artifact '{storage_ref}' was not found.")
        file_path = (export_dir / str(metadata["filename"])).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Export artifact payload is missing for '{storage_ref}'.")

        return StoredArtifact(
            storage_ref=str(metadata["storage_ref"]),
            original_filename=str(metadata["original_filename"]),
            content_type=str(metadata["content_type"]),
            file_size_bytes=int(metadata["file_size_bytes"]),
            file_path=file_path,
            created_at=created_at,
            expires_at=self._resolve_expires_at(created_at, metadata=metadata, retention_hours=self._export_retention_hours),
        )

    def delete_export_artifact(self, storage_ref: str) -> None:
        """Delete one previously stored export artifact by storage reference."""
        export_dir = self._resolve_storage_ref_dir(
            root=self._export_root,
            storage_ref=storage_ref,
            expected_prefix="exports/",
        )
        self._delete_runtime_dir(self._export_root, export_dir)

    def _sanitize_processing_run_id(self, processing_run_id: str) -> str:
        """Return a safe local directory name for one processing run id."""
        sanitized_run_id = str(processing_run_id).replace(":", "-").replace("/", "-").strip()
        if not sanitized_run_id:
            raise ValueError("processing_run_id is required for export artifact storage.")
        return sanitized_run_id

    def _resolve_storage_ref_dir(
        self,
        *,
        root: Path,
        storage_ref: str,
        expected_prefix: str,
    ) -> Path:
        """Resolve one logical storage ref to a concrete directory inside the configured root."""
        normalized_storage_ref = str(storage_ref or "").replace("\\", "/").strip().strip("/")
        if not normalized_storage_ref.startswith(expected_prefix.strip("/")):
            raise FileNotFoundError(f"Storage reference '{storage_ref}' was not found.")

        relative_parts = Path(normalized_storage_ref).parts[1:-1]
        resolved_dir = (root.joinpath(*relative_parts)).resolve()
        resolved_dir.relative_to(root)
        return resolved_dir

    def _normalize_filename(self, original_filename: str) -> str:
        """Return a safe local filename for persisted upload or export content."""
        filename = Path(str(original_filename or "").strip()).name
        return filename or "source-document.pdf"

    def _resolve_upload_created_at(self, upload_dir: Path, metadata: dict | None = None) -> datetime:
        """Return the upload creation timestamp from metadata or legacy filesystem state."""
        return self._resolve_runtime_created_at(upload_dir, metadata)

    def _resolve_runtime_created_at(self, runtime_dir: Path, metadata: dict | None = None) -> datetime:
        """Return the runtime artifact creation timestamp from metadata or legacy filesystem state."""
        raw_metadata = metadata
        if raw_metadata is None:
            metadata_path = runtime_dir / "metadata.json"
            if metadata_path.is_file():
                raw_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            else:
                raw_metadata = {}

        created_at_value = str(raw_metadata.get("created_at") or "").strip()
        if created_at_value:
            try:
                return self._normalize_timestamp(datetime.fromisoformat(created_at_value))
            except ValueError:
                pass
        return self._fallback_created_at(runtime_dir)

    def _fallback_created_at(self, upload_dir: Path) -> datetime:
        """Return a best-effort timestamp for legacy uploads that predate created_at metadata."""
        candidate_paths = [upload_dir / "metadata.json", *upload_dir.iterdir(), upload_dir]
        existing_paths = [path for path in candidate_paths if path.exists()]
        oldest_mtime = min(path.stat().st_mtime for path in existing_paths)
        return datetime.fromtimestamp(oldest_mtime, tz=timezone.utc)

    def _is_expired(self, created_at: datetime) -> bool:
        """Return True when one upload is older than the configured retention window."""
        if self._upload_retention_hours <= 0:
            return False
        expires_at = created_at + timedelta(hours=self._upload_retention_hours)
        return self._normalize_timestamp(self._now_provider()) >= expires_at

    def _resolve_expires_at(
        self,
        created_at: datetime,
        *,
        metadata: dict,
        retention_hours: float,
    ) -> datetime | None:
        """Return the resolved artifact expiration timestamp from metadata or retention."""
        raw_expires_at = str(metadata.get("expires_at") or "").strip()
        if raw_expires_at:
            try:
                return self._normalize_timestamp(datetime.fromisoformat(raw_expires_at))
            except ValueError:
                pass
        if retention_hours <= 0:
            return None
        return created_at + timedelta(hours=retention_hours)

    def _is_export_expired(self, created_at: datetime, *, metadata: dict) -> bool:
        """Return True when one export artifact is older than the configured retention window."""
        expires_at = self._resolve_expires_at(
            created_at,
            metadata=metadata,
            retention_hours=self._export_retention_hours,
        )
        if expires_at is None:
            return False
        return self._normalize_timestamp(self._now_provider()) >= expires_at

    def _delete_upload_dir(self, upload_dir: Path) -> None:
        """Delete one cached upload directory safely inside the configured upload root."""
        self._delete_runtime_dir(self._upload_root, upload_dir)

    def _delete_runtime_dir(self, root: Path, runtime_dir: Path) -> None:
        """Delete one runtime-managed directory safely inside the configured root."""
        resolved_dir = runtime_dir.resolve()
        resolved_dir.relative_to(root)
        shutil.rmtree(resolved_dir, ignore_errors=True)

    def _normalize_timestamp(self, value: datetime) -> datetime:
        """Return one timezone-aware UTC timestamp."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
