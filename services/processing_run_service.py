"""Application service for trusted-profile snapshot resolution and processing-run persistence."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.config import ConfigLoader, ProfileManager
from core.models.lineage import (
    HistoricalExportStatus,
    Organization,
    ProcessingRun,
    ProfileSnapshot,
    RunRecord,
    SourceDocument,
    TrustedProfile,
)
from infrastructure.persistence.sqlite_lineage_store import SqliteLineageStore
from services.lineage_service import build_profile_snapshot, build_run_records, build_template_artifact
from services.lineage_service import build_historical_export_status
from services.review_workflow_service import load_review_data


@dataclass(frozen=True, slots=True)
class ProcessingRunResult:
    """Persisted lineage created for one processing invocation."""

    organization: Organization
    trusted_profile: TrustedProfile
    profile_snapshot: ProfileSnapshot
    source_document: SourceDocument
    processing_run: ProcessingRun
    run_records: list[RunRecord]


@dataclass(frozen=True, slots=True)
class ProcessingRunState:
    """Immutable processing-run lineage and emitted records for API/read workflows."""

    organization: Organization
    trusted_profile: TrustedProfile | None
    profile_snapshot: ProfileSnapshot
    source_document: SourceDocument
    processing_run: ProcessingRun
    run_records: list[RunRecord]
    historical_export_status: HistoricalExportStatus


@dataclass(frozen=True, slots=True)
class _ResolvedProfileContext:
    """One selected trusted profile bundle resolved for snapshotting and processing."""

    organization: Organization
    trusted_profile: TrustedProfile
    profile_metadata: dict[str, object]
    profile_dir: Path
    loader: ConfigLoader
    template_path: Path
    template_bytes: bytes
    template_file_hash: str


class ProcessingRunService:
    """Resolve trusted-profile snapshots and persist immutable processing runs."""

    def __init__(
        self,
        *,
        lineage_store: SqliteLineageStore,
        profile_manager: ProfileManager | None = None,
        engine_version: str = "dev-local",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._profile_manager = profile_manager or ProfileManager()
        self._engine_version = str(engine_version).strip() or "dev-local"
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def resolve_trusted_profile_snapshot(
        self,
        profile_name: str | None = None,
    ) -> tuple[Organization, TrustedProfile, ProfileSnapshot]:
        """Resolve the current effective trusted profile to a persisted immutable snapshot."""
        profile_context = self._resolve_profile_context(profile_name)
        persisted_snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        return (
            profile_context.organization,
            profile_context.trusted_profile,
            persisted_snapshot,
        )

    def create_processing_run(
        self,
        source_document_path: str | Path,
        *,
        profile_name: str | None = None,
        created_by_user_id: str | None = None,
        storage_ref: str | None = None,
    ) -> ProcessingRunResult:
        """Process one source document against one trusted-profile snapshot and persist immutable run records."""
        created_at = self._now_provider()
        source_path = Path(source_document_path).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Source document was not found: {source_path}")

        profile_context = self._resolve_profile_context(profile_name)
        snapshot = self._create_or_reuse_profile_snapshot(profile_context)
        review_result = load_review_data(
            str(source_path),
            config_dir=profile_context.profile_dir,
            legacy_config_dir=self._get_legacy_config_dir(),
        )
        source_document_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        persisted_storage_ref = str(storage_ref).strip() if storage_ref else str(source_path)

        persisted_source_document = self._lineage_store.get_or_create_source_document(
            SourceDocument(
                source_document_id=self._build_source_document_id(
                    file_hash=source_document_hash,
                    storage_ref=persisted_storage_ref,
                ),
                organization_id=profile_context.organization.organization_id,
                original_filename=source_path.name,
                file_hash=source_document_hash,
                storage_ref=persisted_storage_ref,
                content_type=mimetypes.guess_type(source_path.name)[0] or "application/pdf",
                file_size_bytes=source_path.stat().st_size,
                uploaded_by_user_id=created_by_user_id,
                created_at=created_at,
            )
        )

        processing_run = self._lineage_store.create_processing_run(
            ProcessingRun(
                processing_run_id=f"processing-run:{uuid4()}",
                organization_id=profile_context.organization.organization_id,
                source_document_id=persisted_source_document.source_document_id,
                profile_snapshot_id=snapshot.profile_snapshot_id,
                trusted_profile_id=profile_context.trusted_profile.trusted_profile_id,
                status="completed",
                engine_version=self._engine_version,
                aggregate_blockers=tuple(review_result.blocking_issues),
                created_at=created_at,
                created_by_user_id=created_by_user_id,
            )
        )
        run_records = self._lineage_store.create_run_records(
            build_run_records(
                organization_id=profile_context.organization.organization_id,
                processing_run_id=processing_run.processing_run_id,
                records=review_result.records,
                created_at=created_at,
            )
        )
        return ProcessingRunResult(
            organization=profile_context.organization,
            trusted_profile=profile_context.trusted_profile,
            profile_snapshot=snapshot,
            source_document=persisted_source_document,
            processing_run=processing_run,
            run_records=run_records,
        )

    def get_processing_run_state(self, processing_run_id: str) -> ProcessingRunState:
        """Fetch immutable run lineage plus emitted run records for one processing run."""
        processing_run = self._lineage_store.get_processing_run(processing_run_id)
        profile_snapshot = self._lineage_store.get_profile_snapshot(processing_run.profile_snapshot_id)
        return self._build_processing_run_state(processing_run, profile_snapshot)

    def _resolve_profile_context(self, profile_name: str | None) -> _ResolvedProfileContext:
        """Resolve one selected trusted profile bundle for snapshotting and processing."""
        created_at = self._now_provider()
        organization = self._lineage_store.ensure_organization(
            organization_id="org-default",
            slug="default-org",
            display_name="Default Organization",
            created_at=created_at,
            is_seeded=True,
        )

        profile_metadata, profile_dir, loader = self._load_profile_bundle(profile_name)
        trusted_profile = self._lineage_store.get_or_create_trusted_profile(
            TrustedProfile(
                trusted_profile_id=f"trusted-profile:{organization.organization_id}:{profile_metadata['profile_name']}",
                organization_id=organization.organization_id,
                profile_name=str(profile_metadata["profile_name"]),
                display_name=str(profile_metadata["display_name"]),
                source_kind="seeded" if str(profile_metadata["profile_name"]).casefold() == "default" else "imported",
                bundle_ref=str(profile_metadata.get("profile_dir") or ""),
                description=str(profile_metadata.get("description") or ""),
                version_label=str(profile_metadata.get("version") or "") or None,
                created_at=created_at,
            )
        )

        template_path = self._resolve_template_path(profile_dir, profile_metadata, loader)
        template_bytes = template_path.read_bytes()
        template_file_hash = hashlib.sha256(template_bytes).hexdigest()
        return _ResolvedProfileContext(
            organization=organization,
            trusted_profile=trusted_profile,
            profile_metadata=profile_metadata,
            profile_dir=profile_dir,
            loader=loader,
            template_path=template_path,
            template_bytes=template_bytes,
            template_file_hash=template_file_hash,
        )

    def _build_processing_run_state(
        self,
        processing_run: ProcessingRun,
        profile_snapshot: ProfileSnapshot,
    ) -> ProcessingRunState:
        """Build immutable processing-run state from persisted lineage."""
        organization = self._lineage_store.ensure_organization(
            organization_id=processing_run.organization_id,
            slug="default-org",
            display_name="Default Organization",
            created_at=processing_run.created_at,
            is_seeded=True,
        )
        source_document = self._lineage_store.get_source_document(processing_run.source_document_id)
        trusted_profile = (
            self._lineage_store.get_trusted_profile(processing_run.trusted_profile_id)
            if processing_run.trusted_profile_id
            else None
        )
        run_records = self._lineage_store.list_run_records(processing_run.processing_run_id)
        return ProcessingRunState(
            organization=organization,
            trusted_profile=trusted_profile,
            profile_snapshot=profile_snapshot,
            source_document=source_document,
            processing_run=processing_run,
            run_records=run_records,
            historical_export_status=build_historical_export_status(profile_snapshot),
        )

    def _create_or_reuse_profile_snapshot(
        self,
        profile_context: _ResolvedProfileContext,
    ) -> ProfileSnapshot:
        """Create or reuse the immutable snapshot for one resolved behavioral bundle."""
        template_artifact = self._lineage_store.get_or_create_template_artifact(
            build_template_artifact(
                template_artifact_id=f"template-artifact:{profile_context.organization.organization_id}:{uuid4()}",
                organization_id=profile_context.organization.organization_id,
                original_filename=profile_context.template_path.name,
                content_bytes=profile_context.template_bytes,
                created_at=self._now_provider(),
            )
        )
        full_bundle_payload, behavioral_hash_payload = self._build_snapshot_payloads(
            profile_metadata=profile_context.profile_metadata,
            loader=profile_context.loader,
            template_file_hash=profile_context.template_file_hash,
        )
        snapshot = build_profile_snapshot(
            profile_snapshot_id=f"profile-snapshot:{profile_context.organization.organization_id}:{uuid4()}",
            organization_id=profile_context.organization.organization_id,
            trusted_profile_id=None,
            bundle_payload=full_bundle_payload,
            hash_payload=behavioral_hash_payload,
            engine_version=self._engine_version,
            created_at=self._now_provider(),
            template_artifact_id=template_artifact.template_artifact_id,
            template_artifact_ref=profile_context.template_path.name,
            template_file_hash=profile_context.template_file_hash,
        )
        return self._lineage_store.get_or_create_profile_snapshot(snapshot)

    def _load_profile_bundle(
        self,
        profile_name: str | None,
    ) -> tuple[dict[str, object], Path, ConfigLoader]:
        """Load profile metadata plus the config loader for one named or active profile."""
        if profile_name:
            profile_dir = self._profile_manager.get_profile_dir(profile_name)
            if profile_dir is None:
                raise FileNotFoundError(f"Profile '{profile_name}' was not found.")
            profile_metadata = self._profile_manager.get_profile_metadata(profile_name)
            loader = self._build_config_loader(profile_dir)
            return profile_metadata, profile_dir, loader
        profile_dir = self._profile_manager.get_active_profile_dir()
        loader = self._build_config_loader(profile_dir)
        return self._profile_manager.get_active_profile_metadata(), profile_dir, loader

    def _build_snapshot_payloads(
        self,
        profile_metadata: dict[str, object],
        loader: ConfigLoader,
        template_file_hash: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Build persisted snapshot payloads plus the behavior-only hash basis."""
        behavioral_bundle = {
            "phase_mapping": loader.get_phase_mapping(),
            "labor_mapping": loader.get_labor_mapping(),
            "equipment_mapping": loader.get_equipment_mapping(),
            "vendor_normalization": loader.get_vendor_normalization(),
            "input_model": loader.get_input_model(),
            "review_rules": loader.get_review_rules(),
            "rates": loader.get_rates(),
            "labor_slots": loader.get_labor_slots(),
            "equipment_slots": loader.get_equipment_slots(),
            "recap_template_map": loader.get_recap_template_map(),
            "template": {
                "template_file_hash": template_file_hash,
            },
        }
        full_bundle = {
            "behavioral_bundle": behavioral_bundle,
            "traceability": {
                "trusted_profile": {
                    "profile_name": str(profile_metadata.get("profile_name") or ""),
                    "display_name": str(profile_metadata.get("display_name") or ""),
                    "description": str(profile_metadata.get("description") or ""),
                    "version": str(profile_metadata.get("version") or ""),
                    "template_filename": str(profile_metadata.get("template_filename") or ""),
                },
                "engine_version": self._engine_version,
            },
        }
        return full_bundle, behavioral_bundle

    def _build_config_loader(self, profile_dir: Path) -> ConfigLoader:
        """Build a fresh loader so snapshot resolution sees the current on-disk bundle."""
        resolved_profile_dir = profile_dir.resolve()
        ConfigLoader._shared_cache.pop(resolved_profile_dir, None)
        return ConfigLoader(
            config_dir=resolved_profile_dir,
            legacy_config_dir=self._get_legacy_config_dir(),
        )

    def _get_legacy_config_dir(self) -> Path | None:
        """Reuse the configured shared-config root when a custom profile manager is supplied."""
        legacy_config_dir = getattr(self._profile_manager, "_legacy_config_root", None)
        if isinstance(legacy_config_dir, Path):
            return legacy_config_dir
        return None

    def _resolve_template_path(
        self,
        profile_dir: Path,
        profile_metadata: dict[str, object],
        loader: ConfigLoader,
    ) -> Path:
        """Resolve the template path without relying on a global active-profile lookup."""
        template_filename = str(profile_metadata.get("template_filename") or "").strip()
        if template_filename:
            template_path = (profile_dir / template_filename).resolve()
            if template_path.is_file():
                return template_path

        recap_map = loader.get_recap_template_map()
        configured_path = str(recap_map.get("default_template_path") or "").strip()
        if configured_path:
            template_path = Path(configured_path).expanduser().resolve()
            if template_path.is_file():
                return template_path

        raise FileNotFoundError(
            f"No recap template workbook could be resolved for config bundle '{profile_dir}'."
        )

    def _build_source_document_id(self, *, file_hash: str, storage_ref: str) -> str:
        """Build a stable source-document identity from file hash and storage location."""
        storage_value = storage_ref.encode("utf-8")
        storage_hash = hashlib.sha256(storage_value).hexdigest()[:12]
        return f"source-document:{file_hash}:{storage_hash}"
