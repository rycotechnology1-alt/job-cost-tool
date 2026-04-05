"""Application service for review-session overlays and exact-revision export lineage."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterator, Sequence
from uuid import uuid4

from core.models import PendingRecordEdit, Record
from core.models.lineage import (
    ExportArtifact,
    HistoricalExportStatus,
    ProcessingRun,
    ProfileSnapshot,
    ReviewSession,
    RunRecord,
    TemplateArtifact,
    TrustedProfile,
)
from infrastructure.storage import RuntimeStorage, StoredArtifact
from infrastructure.persistence.sqlite_lineage_store import SqliteLineageStore
from services.export_service import export_records_to_recap
from services.lineage_service import (
    append_review_edit_batch,
    build_historical_export_status,
    build_export_artifact,
    create_review_session,
    rebuild_review_records,
)
from services.review_workflow_service import prepare_review_updates
from services.validation_service import validate_records


@dataclass(frozen=True, slots=True)
class ReviewSessionState:
    """Effective review state for one immutable run at one session revision."""

    processing_run: ProcessingRun
    profile_snapshot: ProfileSnapshot
    trusted_profile: TrustedProfile | None
    review_session: ReviewSession
    run_records: list[RunRecord]
    records: list[Record]
    blocking_issues: list[str]
    session_revision: int
    historical_export_status: HistoricalExportStatus


@dataclass(frozen=True, slots=True)
class ReviewSessionExportResult:
    """Exact-revision export output plus its persisted lineage."""

    review_session_state: ReviewSessionState
    export_artifact: ExportArtifact
    output_path: Path
    stored_artifact: StoredArtifact | None = None


@dataclass(frozen=True, slots=True)
class _MaterializedSnapshotBundle:
    """Temporary explicit config context rebuilt from one immutable snapshot."""

    config_dir: Path
    legacy_config_dir: Path
    template_path: Path


class HistoricalExportUnavailableError(RuntimeError):
    """Raised when exact historical export lineage is unavailable for a processing run."""

    def __init__(self, status: HistoricalExportStatus) -> None:
        self.status = status
        super().__init__(status.detail)


class ReviewSessionService:
    """Persist append-only review overlays and export one exact session revision."""

    def __init__(
        self,
        *,
        lineage_store: SqliteLineageStore,
        artifact_store: RuntimeStorage | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._artifact_store = artifact_store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def open_review_session(
        self,
        processing_run_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> ReviewSessionState:
        """Open or create the phase-1 review session and resume its latest revision."""
        return self.get_review_session_state(
            processing_run_id,
            created_by_user_id=created_by_user_id,
        )

    def get_review_session_state(
        self,
        processing_run_id: str,
        *,
        session_revision: int | None = None,
        created_by_user_id: str | None = None,
    ) -> ReviewSessionState:
        """Return effective review records for one run at one exact session revision."""
        context = self._load_run_context(
            processing_run_id,
            create_session=True,
            created_by_user_id=created_by_user_id,
        )
        target_revision = context.review_session.current_revision if session_revision is None else session_revision
        if target_revision < 0:
            raise ValueError("session_revision must be greater than or equal to 0.")
        if target_revision > context.review_session.current_revision:
            raise ValueError("session_revision cannot be greater than the review session's current revision.")

        reviewed_record_edits = self._lineage_store.list_reviewed_record_edits(
            context.review_session.review_session_id,
            up_to_revision=target_revision,
        )
        effective_records = rebuild_review_records(
            run_records=context.run_records,
            reviewed_record_edits=reviewed_record_edits,
        )
        validated_records, blocking_issues = validate_records(effective_records)
        return ReviewSessionState(
            processing_run=context.processing_run,
            profile_snapshot=context.profile_snapshot,
            trusted_profile=context.trusted_profile,
            review_session=context.review_session,
            run_records=context.run_records,
            records=list(validated_records),
            blocking_issues=list(blocking_issues),
            session_revision=target_revision,
            historical_export_status=build_historical_export_status(context.profile_snapshot),
        )

    def apply_review_edits(
        self,
        processing_run_id: str,
        pending_edits: Sequence[PendingRecordEdit],
        *,
        created_by_user_id: str | None = None,
    ) -> ReviewSessionState:
        """Append one accepted review-edit batch without mutating immutable run rows."""
        context = self._load_run_context(
            processing_run_id,
            create_session=True,
            created_by_user_id=created_by_user_id,
        )
        run_record_keys = {run_record.record_key for run_record in context.run_records}
        prepared_pending_edits: list[PendingRecordEdit] = []

        with self._materialized_snapshot_bundle(
            context.profile_snapshot,
        ) as snapshot_bundle:
            for pending_edit in pending_edits:
                if pending_edit.record_key not in run_record_keys:
                    raise KeyError(
                        f"record_key '{pending_edit.record_key}' does not exist in ProcessingRun "
                        f"'{processing_run_id}'."
                    )
                changed_fields = prepare_review_updates(
                    pending_edit.changed_fields,
                    config_dir=snapshot_bundle.config_dir,
                    legacy_config_dir=snapshot_bundle.legacy_config_dir,
                )
                prepared_pending_edits.append(
                    PendingRecordEdit(
                        record_key=pending_edit.record_key,
                        changed_fields=changed_fields,
                    )
                )

        updated_session, persisted_edits = append_review_edit_batch(
            review_session=context.review_session,
            pending_edits=prepared_pending_edits,
            created_at=self._now_provider(),
            created_by_user_id=created_by_user_id,
        )
        self._lineage_store.save_review_session_edits(updated_session, persisted_edits)
        return self.get_review_session_state(
            processing_run_id,
            session_revision=updated_session.current_revision,
        )

    def export_session_revision(
        self,
        processing_run_id: str,
        *,
        session_revision: int,
        output_path: str | Path | None = None,
        created_by_user_id: str | None = None,
    ) -> ReviewSessionExportResult:
        """Generate one workbook from one exact persisted session revision and record its lineage."""
        review_session_state = self.get_review_session_state(
            processing_run_id,
            session_revision=session_revision,
            created_by_user_id=created_by_user_id,
        )
        if not review_session_state.historical_export_status.is_reproducible:
            raise HistoricalExportUnavailableError(review_session_state.historical_export_status)

        if output_path is not None:
            resolved_output_path = Path(output_path).expanduser().resolve()
            with self._materialized_snapshot_bundle(
                review_session_state.profile_snapshot,
            ) as snapshot_bundle:
                export_records_to_recap(
                    review_session_state.records,
                    str(snapshot_bundle.template_path),
                    str(resolved_output_path),
                    config_dir=snapshot_bundle.config_dir,
                    legacy_config_dir=snapshot_bundle.legacy_config_dir,
                )
            stored_artifact = None
        else:
            if self._artifact_store is None:
                raise ValueError("output_path is required when no artifact_store is configured.")
            stored_artifact = self._export_via_artifact_store(
                review_session_state=review_session_state,
            )
            resolved_output_path = stored_artifact.file_path

        file_hash = hashlib.sha256(resolved_output_path.read_bytes()).hexdigest()
        export_artifact = self._lineage_store.create_export_artifact(
            build_export_artifact(
                export_artifact_id=f"export-artifact:{review_session_state.review_session.review_session_id}:{uuid4()}",
                organization_id=review_session_state.processing_run.organization_id,
                processing_run=review_session_state.processing_run,
                review_session=review_session_state.review_session,
                session_revision=session_revision,
                artifact_kind="recap_workbook",
                storage_ref=stored_artifact.storage_ref if stored_artifact else str(resolved_output_path),
                created_at=self._now_provider(),
                template_artifact_id=review_session_state.profile_snapshot.template_artifact_id,
                created_by_user_id=created_by_user_id,
                file_hash=file_hash,
            )
        )
        return ReviewSessionExportResult(
            review_session_state=review_session_state,
            export_artifact=export_artifact,
            output_path=resolved_output_path,
            stored_artifact=stored_artifact,
        )

    def get_export_artifact(self, export_artifact_id: str) -> ExportArtifact:
        """Fetch one persisted export artifact for API/download workflows."""
        return self._lineage_store.get_export_artifact(export_artifact_id)

    def resolve_export_artifact_payload(self, export_artifact_id: str) -> StoredArtifact:
        """Resolve one persisted export artifact through the configured storage seam."""
        if self._artifact_store is None:
            raise ValueError("artifact_store is required to resolve persisted export payloads.")
        export_artifact = self.get_export_artifact(export_artifact_id)
        return self._artifact_store.get_export_artifact(export_artifact.storage_ref)

    def _load_run_context(
        self,
        processing_run_id: str,
        *,
        create_session: bool,
        created_by_user_id: str | None = None,
    ) -> _RunContext:
        processing_run = self._lineage_store.get_processing_run(processing_run_id)
        profile_snapshot = self._lineage_store.get_profile_snapshot(processing_run.profile_snapshot_id)
        trusted_profile = None
        if processing_run.trusted_profile_id:
            trusted_profile = self._lineage_store.get_trusted_profile(processing_run.trusted_profile_id)

        if create_session:
            review_session = self._lineage_store.get_or_create_review_session(
                create_review_session(
                    review_session_id=f"review-session:{processing_run.processing_run_id}",
                    organization_id=processing_run.organization_id,
                    processing_run_id=processing_run.processing_run_id,
                    created_at=self._now_provider(),
                    created_by_user_id=created_by_user_id,
                )
            )
        else:
            review_session = self._lineage_store.get_review_session_for_run(processing_run.processing_run_id)

        run_records = self._lineage_store.list_run_records(processing_run.processing_run_id)
        return _RunContext(
            processing_run=processing_run,
            profile_snapshot=profile_snapshot,
            trusted_profile=trusted_profile,
            review_session=review_session,
            run_records=run_records,
        )

    @contextmanager
    def _materialized_snapshot_bundle(
        self,
        profile_snapshot: ProfileSnapshot,
    ) -> Iterator[_MaterializedSnapshotBundle]:
        """Materialize one immutable behavioral bundle into a temporary config directory."""
        with TemporaryDirectory(prefix="job-cost-snapshot-config-") as config_tmp, TemporaryDirectory(
            prefix="job-cost-snapshot-legacy-"
        ) as legacy_tmp:
            config_dir = Path(config_tmp).resolve()
            legacy_config_dir = Path(legacy_tmp).resolve()
            behavioral_bundle = self._get_behavioral_bundle(profile_snapshot)
            traceability = self._get_traceability_bundle(profile_snapshot)
            self._write_snapshot_config_bundle(
                config_dir=config_dir,
                behavioral_bundle=behavioral_bundle,
                traceability=traceability,
            )
            template_artifact = self._load_template_artifact(profile_snapshot)
            template_path = (config_dir / template_artifact.original_filename).resolve()
            template_path.write_bytes(template_artifact.content_bytes)
            (legacy_config_dir / "phase_catalog.json").write_text('{"phases":[]}', encoding="utf-8")
            yield _MaterializedSnapshotBundle(
                config_dir=config_dir,
                legacy_config_dir=legacy_config_dir,
                template_path=template_path,
            )

    def _write_snapshot_config_bundle(
        self,
        *,
        config_dir: Path,
        behavioral_bundle: dict[str, object],
        traceability: dict[str, object],
    ) -> None:
        """Write the snapshot-backed config files required by review/edit/export services."""
        file_payloads = {
            "labor_mapping.json": behavioral_bundle.get("labor_mapping", {}),
            "equipment_mapping.json": behavioral_bundle.get("equipment_mapping", {}),
            "phase_mapping.json": behavioral_bundle.get("phase_mapping", {}),
            "vendor_normalization.json": behavioral_bundle.get("vendor_normalization", {}),
            "input_model.json": behavioral_bundle.get("input_model", {}),
            "recap_template_map.json": behavioral_bundle.get("recap_template_map", {}),
            "target_labor_classifications.json": behavioral_bundle.get("labor_slots", {}),
            "target_equipment_classifications.json": behavioral_bundle.get("equipment_slots", {}),
            "rates.json": behavioral_bundle.get("rates", {}),
            "review_rules.json": behavioral_bundle.get("review_rules", {}),
            "profile.json": {
                "profile_name": str(self._nested_lookup(traceability, "trusted_profile", "profile_name") or "snapshot"),
                "display_name": str(self._nested_lookup(traceability, "trusted_profile", "display_name") or "Snapshot"),
                "description": str(self._nested_lookup(traceability, "trusted_profile", "description") or ""),
                "version": str(self._nested_lookup(traceability, "trusted_profile", "version") or ""),
                "template_filename": str(
                    self._nested_lookup(traceability, "trusted_profile", "template_filename")
                    or self._nested_lookup(traceability, "trusted_profile", "template_artifact_ref")
                    or "recap_template.xlsx"
                ),
            },
        }

        for file_name, payload in file_payloads.items():
            (config_dir / file_name).write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )

    def _load_template_artifact(self, profile_snapshot: ProfileSnapshot) -> TemplateArtifact:
        """Load the exact workbook template artifact captured for one snapshot."""
        if not str(profile_snapshot.template_artifact_id or "").strip():
            raise HistoricalExportUnavailableError(build_historical_export_status(profile_snapshot))
        template_artifact = self._lineage_store.get_template_artifact(profile_snapshot.template_artifact_id)
        if profile_snapshot.template_file_hash and template_artifact.content_hash != profile_snapshot.template_file_hash:
            raise ValueError(
                "Persisted template artifact does not match the template hash recorded on the ProfileSnapshot."
            )
        return template_artifact

    def _export_via_artifact_store(
        self,
        *,
        review_session_state: ReviewSessionState,
    ) -> StoredArtifact:
        """Generate one workbook into temporary storage, then persist it through the runtime storage seam."""
        with TemporaryDirectory(prefix="job-cost-export-artifact-") as export_tmp:
            temp_output_path = Path(export_tmp).resolve() / "recap-export.xlsx"
            with self._materialized_snapshot_bundle(
                review_session_state.profile_snapshot,
            ) as snapshot_bundle:
                export_records_to_recap(
                    review_session_state.records,
                    str(snapshot_bundle.template_path),
                    str(temp_output_path),
                    config_dir=snapshot_bundle.config_dir,
                    legacy_config_dir=snapshot_bundle.legacy_config_dir,
                )
            return self._artifact_store.save_export_artifact(
                processing_run_id=review_session_state.processing_run.processing_run_id,
                session_revision=review_session_state.session_revision,
                original_filename=temp_output_path.name,
                content_bytes=temp_output_path.read_bytes(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    def _get_behavioral_bundle(self, profile_snapshot: ProfileSnapshot) -> dict[str, object]:
        """Return the behaviorally relevant config payload captured in one snapshot."""
        raw_bundle = profile_snapshot.bundle_payload
        if isinstance(raw_bundle.get("behavioral_bundle"), dict):
            return dict(raw_bundle["behavioral_bundle"])
        return dict(raw_bundle)

    def _get_traceability_bundle(self, profile_snapshot: ProfileSnapshot) -> dict[str, object]:
        """Return the traceability metadata captured in one snapshot."""
        raw_bundle = profile_snapshot.bundle_payload
        if isinstance(raw_bundle.get("traceability"), dict):
            return dict(raw_bundle["traceability"])
        return {}

    def _nested_lookup(self, payload: dict[str, object], *keys: str) -> object | None:
        """Safely read a nested dictionary value."""
        current: object = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current


@dataclass(frozen=True, slots=True)
class _RunContext:
    """Loaded immutable lineage needed to evaluate one review session."""

    processing_run: ProcessingRun
    profile_snapshot: ProfileSnapshot
    trusted_profile: TrustedProfile | None
    review_session: ReviewSession
    run_records: list[RunRecord]
