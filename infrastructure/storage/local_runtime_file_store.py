"""Local file storage helpers for uploaded source documents and exported workbooks."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .runtime_storage import RuntimeStorage, StoredArtifact, StoredUpload


class LocalRuntimeFileStore(RuntimeStorage):
    """Persist uploaded source documents and export outputs on local disk."""

    def __init__(
        self,
        *,
        upload_root: str | Path,
        export_root: str | Path,
    ) -> None:
        self._upload_root = Path(upload_root).expanduser().resolve()
        self._export_root = Path(export_root).expanduser().resolve()
        self._upload_root.mkdir(parents=True, exist_ok=True)
        self._export_root.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self,
        *,
        original_filename: str,
        content_bytes: bytes,
        content_type: str | None = None,
    ) -> StoredUpload:
        """Persist one uploaded source document and return its stable local reference."""
        filename = self._normalize_filename(original_filename)
        if not content_bytes:
            raise ValueError("Uploaded source document must not be empty.")

        upload_id = uuid4().hex
        upload_dir = self._upload_root / upload_id
        upload_dir.mkdir(parents=True, exist_ok=False)
        file_path = (upload_dir / filename).resolve()
        file_path.write_bytes(content_bytes)

        metadata = {
            "upload_id": upload_id,
            "original_filename": filename,
            "content_type": str(content_type or "application/octet-stream"),
            "file_size_bytes": len(content_bytes),
            "storage_ref": f"uploads/{upload_id}/{filename}",
            "filename": filename,
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
        file_path = (upload_dir / str(metadata["filename"])).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Uploaded source document payload is missing for '{normalized_upload_id}'.")

        return StoredUpload(
            upload_id=str(metadata["upload_id"]),
            original_filename=str(metadata["original_filename"]),
            content_type=str(metadata["content_type"]),
            file_size_bytes=int(metadata["file_size_bytes"]),
            storage_ref=str(metadata["storage_ref"]),
            file_path=file_path,
        )

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
        file_path = (export_dir / str(metadata["filename"])).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Export artifact payload is missing for '{storage_ref}'.")

        return StoredArtifact(
            storage_ref=str(metadata["storage_ref"]),
            original_filename=str(metadata["original_filename"]),
            content_type=str(metadata["content_type"]),
            file_size_bytes=int(metadata["file_size_bytes"]),
            file_path=file_path,
        )

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
