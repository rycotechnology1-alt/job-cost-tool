"""Minimal runtime settings for the phase-1 FastAPI slice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


def _resolve_repo_env_path() -> Path:
    """Return the repo-root dotenv path used for local startup."""
    return Path(__file__).resolve().parents[1] / ".env"


def _load_repo_dotenv() -> None:
    """Load repo-root dotenv values for local startup without overriding real env vars."""
    env_path = _resolve_repo_env_path()
    if env_path.is_file():
        load_dotenv(env_path, override=False)


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Small runtime configuration seam for hosted API startup and tests."""

    database_provider: str
    database_path: str | Path
    postgres_admin_url: str | None
    postgres_pooled_url: str | None
    postgres_schema: str
    auth_mode: str
    auth_secret: str | None
    storage_provider: str
    blob_read_write_token: str | None
    upload_root: Path
    export_root: Path
    upload_retention_hours: int
    engine_version: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ApiSettings":
        """Build phase-1 API settings from environment variables with hosted defaults."""
        if env is None:
            _load_repo_dotenv()
            environ = os.environ
        else:
            environ = env
        runtime_root = Path(environ.get("JOB_COST_API_RUNTIME_ROOT", "/tmp/job-cost-api")).expanduser()
        database_provider = str(environ.get("JOB_COST_API_DATABASE_PROVIDER", "postgres")).strip().lower() or "postgres"
        database_path = environ.get("JOB_COST_API_DATABASE_PATH") or f"{runtime_root.as_posix()}/lineage.db"
        postgres_admin_url = str(environ.get("JOB_COST_API_POSTGRES_ADMIN_URL", "")).strip() or None
        postgres_pooled_url = str(environ.get("JOB_COST_API_POSTGRES_POOLED_URL", "")).strip() or None
        postgres_schema = str(environ.get("JOB_COST_API_POSTGRES_SCHEMA", "public")).strip() or "public"
        auth_mode = str(environ.get("JOB_COST_API_AUTH_MODE", "local")).strip().lower() or "local"
        auth_secret = str(environ.get("JOB_COST_API_AUTH_SECRET", "")).strip() or None
        storage_provider = str(environ.get("JOB_COST_API_STORAGE_PROVIDER", "vercel_blob")).strip().lower() or "vercel_blob"
        blob_read_write_token = str(environ.get("BLOB_READ_WRITE_TOKEN", "")).strip() or None
        upload_root = Path(environ.get("JOB_COST_API_UPLOAD_ROOT", str(runtime_root / "uploads"))).expanduser()
        export_root = Path(environ.get("JOB_COST_API_EXPORT_ROOT", str(runtime_root / "exports"))).expanduser()
        raw_upload_retention_hours = str(environ.get("JOB_COST_API_UPLOAD_RETENTION_HOURS", "24")).strip()
        upload_retention_hours = int(raw_upload_retention_hours or "24")
        engine_version = str(environ.get("JOB_COST_API_ENGINE_VERSION", "dev-local")).strip() or "dev-local"
        return cls(
            database_provider=database_provider,
            database_path=database_path,
            postgres_admin_url=postgres_admin_url,
            postgres_pooled_url=postgres_pooled_url,
            postgres_schema=postgres_schema,
            auth_mode=auth_mode,
            auth_secret=auth_secret,
            storage_provider=storage_provider,
            blob_read_write_token=blob_read_write_token,
            upload_root=upload_root,
            export_root=export_root,
            upload_retention_hours=upload_retention_hours,
            engine_version=engine_version,
        )

    def with_overrides(
        self,
        *,
        database_provider: str | None = None,
        database_path: str | Path | None = None,
        postgres_admin_url: str | None = None,
        postgres_pooled_url: str | None = None,
        postgres_schema: str | None = None,
        auth_mode: str | None = None,
        auth_secret: str | None = None,
        storage_provider: str | None = None,
        blob_read_write_token: str | None = None,
        upload_root: str | Path | None = None,
        export_root: str | Path | None = None,
        upload_retention_hours: int | None = None,
        engine_version: str | None = None,
    ) -> "ApiSettings":
        """Return one settings object with optional explicit overrides applied."""
        return ApiSettings(
            database_provider=self.database_provider if database_provider is None else str(database_provider).strip().lower(),
            database_path=self.database_path if database_path is None else database_path,
            postgres_admin_url=self.postgres_admin_url if postgres_admin_url is None else postgres_admin_url,
            postgres_pooled_url=self.postgres_pooled_url if postgres_pooled_url is None else postgres_pooled_url,
            postgres_schema=self.postgres_schema if postgres_schema is None else str(postgres_schema).strip() or "public",
            auth_mode=self.auth_mode if auth_mode is None else str(auth_mode).strip().lower() or "local",
            auth_secret=self.auth_secret if auth_secret is None else (str(auth_secret).strip() or None),
            storage_provider=(
                self.storage_provider if storage_provider is None else str(storage_provider).strip().lower() or "local"
            ),
            blob_read_write_token=(
                self.blob_read_write_token
                if blob_read_write_token is None
                else (str(blob_read_write_token).strip() or None)
            ),
            upload_root=self.upload_root if upload_root is None else Path(upload_root).expanduser(),
            export_root=self.export_root if export_root is None else Path(export_root).expanduser(),
            upload_retention_hours=(
                self.upload_retention_hours if upload_retention_hours is None else int(upload_retention_hours)
            ),
            engine_version=self.engine_version if engine_version is None else engine_version,
        )
