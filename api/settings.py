"""Minimal runtime settings for the phase-1 FastAPI slice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Small runtime configuration seam for local API startup and tests."""

    database_path: str | Path
    upload_root: Path
    export_root: Path
    upload_retention_hours: int
    engine_version: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ApiSettings":
        """Build phase-1 API settings from environment variables with safe local defaults."""
        environ = env or os.environ
        runtime_root = Path(environ.get("JOB_COST_API_RUNTIME_ROOT", "runtime/api")).expanduser()
        database_path = environ.get("JOB_COST_API_DATABASE_PATH") or str(runtime_root / "lineage.db")
        upload_root = Path(environ.get("JOB_COST_API_UPLOAD_ROOT", str(runtime_root / "uploads"))).expanduser()
        export_root = Path(environ.get("JOB_COST_API_EXPORT_ROOT", str(runtime_root / "exports"))).expanduser()
        raw_upload_retention_hours = str(environ.get("JOB_COST_API_UPLOAD_RETENTION_HOURS", "24")).strip()
        upload_retention_hours = int(raw_upload_retention_hours or "24")
        engine_version = str(environ.get("JOB_COST_API_ENGINE_VERSION", "dev-local")).strip() or "dev-local"
        return cls(
            database_path=database_path,
            upload_root=upload_root,
            export_root=export_root,
            upload_retention_hours=upload_retention_hours,
            engine_version=engine_version,
        )

    def with_overrides(
        self,
        *,
        database_path: str | Path | None = None,
        upload_root: str | Path | None = None,
        export_root: str | Path | None = None,
        upload_retention_hours: int | None = None,
        engine_version: str | None = None,
    ) -> "ApiSettings":
        """Return one settings object with optional explicit overrides applied."""
        return ApiSettings(
            database_path=self.database_path if database_path is None else database_path,
            upload_root=self.upload_root if upload_root is None else Path(upload_root).expanduser(),
            export_root=self.export_root if export_root is None else Path(export_root).expanduser(),
            upload_retention_hours=(
                self.upload_retention_hours if upload_retention_hours is None else int(upload_retention_hours)
            ),
            engine_version=self.engine_version if engine_version is None else engine_version,
        )
