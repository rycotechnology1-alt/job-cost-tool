"""Pure lineage helpers for phase-1 processing, review-session, and export persistence rules."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from hashlib import sha256
from typing import Any, Sequence

from core.models.record import Record
from core.models.lineage import (
    ExportArtifact,
    HistoricalExportStatus,
    PendingRecordEdit,
    ProcessingRun,
    ProfileSnapshot,
    ReviewSession,
    ReviewedRecordEdit,
    RunRecord,
    TemplateArtifact,
)


def build_profile_snapshot(
    *,
    profile_snapshot_id: str,
    organization_id: str,
    trusted_profile_id: str | None,
    bundle_payload: dict[str, Any],
    hash_payload: dict[str, Any] | None = None,
    engine_version: str,
    created_at: datetime,
    template_artifact_id: str | None = None,
    template_artifact_ref: str | None = None,
    template_file_hash: str | None = None,
) -> ProfileSnapshot:
    """Freeze one effective bundle while preserving config order and stable content hashing."""
    stored_bundle_json = json.dumps(bundle_payload, ensure_ascii=True)
    canonical_hash_json = canonicalize_json(hash_payload if hash_payload is not None else bundle_payload)
    content_hash = sha256(canonical_hash_json.encode("utf-8")).hexdigest()
    return ProfileSnapshot(
        profile_snapshot_id=profile_snapshot_id,
        organization_id=organization_id,
        trusted_profile_id=trusted_profile_id,
        content_hash=content_hash,
        bundle_payload=json.loads(stored_bundle_json),
        canonical_bundle_json=stored_bundle_json,
        engine_version=engine_version,
        created_at=created_at,
        template_artifact_id=template_artifact_id,
        template_artifact_ref=template_artifact_ref,
        template_file_hash=template_file_hash,
    )


def build_template_artifact(
    *,
    template_artifact_id: str,
    organization_id: str,
    original_filename: str,
    content_bytes: bytes,
    created_at: datetime,
    created_by_user_id: str | None = None,
) -> TemplateArtifact:
    """Create an immutable workbook template artifact from exact file content."""
    if not content_bytes:
        raise ValueError("Template artifact content_bytes must not be empty.")
    original_filename_text = str(original_filename).strip()
    if not original_filename_text:
        raise ValueError("Template artifact original_filename is required.")
    return TemplateArtifact(
        template_artifact_id=template_artifact_id,
        organization_id=organization_id,
        content_hash=sha256(content_bytes).hexdigest(),
        original_filename=original_filename_text,
        content_bytes=bytes(content_bytes),
        file_size_bytes=len(content_bytes),
        created_at=created_at,
        created_by_user_id=created_by_user_id,
    )


def build_run_records(
    *,
    organization_id: str,
    processing_run_id: str,
    records: Sequence[Any],
    created_at: datetime,
) -> list[RunRecord]:
    """Build immutable run records with deterministic run-scoped record keys."""
    run_records: list[RunRecord] = []
    for index, record in enumerate(records):
        payload = normalize_payload(record)
        record_key = build_record_key(index)
        run_records.append(
            RunRecord(
                run_record_id=f"{processing_run_id}:{record_key}",
                organization_id=organization_id,
                processing_run_id=processing_run_id,
                record_key=record_key,
                record_index=index,
                canonical_record=payload,
                created_at=created_at,
                source_page=_coerce_optional_int(payload.get("source_page")),
                source_line_text=_coerce_optional_str(payload.get("source_line_text")),
            )
        )
    return run_records


def build_record_key(record_index: int) -> str:
    """Return the deterministic run-scoped record key derived from emitted order."""
    if record_index < 0:
        raise ValueError("record_index must be greater than or equal to 0.")
    return f"record-{record_index}"


def rebuild_review_records(
    *,
    run_records: Sequence[RunRecord],
    reviewed_record_edits: Sequence[ReviewedRecordEdit],
) -> list[Record]:
    """Reconstruct effective review records by overlaying append-only edits onto immutable run rows."""
    base_records: dict[str, Record] = {}
    ordered_keys: list[str] = []

    for run_record in sorted(run_records, key=lambda item: item.record_index):
        base_records[run_record.record_key] = Record(**normalize_payload(run_record.canonical_record))
        ordered_keys.append(run_record.record_key)

    sorted_edits = sorted(
        reviewed_record_edits,
        key=lambda item: (item.session_revision, item.created_at, item.reviewed_record_edit_id),
    )
    for reviewed_edit in sorted_edits:
        if reviewed_edit.record_key not in base_records:
            raise KeyError(
                f"ReviewedRecordEdit '{reviewed_edit.reviewed_record_edit_id}' references unknown record_key "
                f"'{reviewed_edit.record_key}'."
            )
        base_records[reviewed_edit.record_key] = replace(
            base_records[reviewed_edit.record_key],
            **normalize_payload(reviewed_edit.changed_fields),
        )

    return [base_records[record_key] for record_key in ordered_keys]


def create_review_session(
    *,
    review_session_id: str,
    organization_id: str,
    processing_run_id: str,
    created_at: datetime,
    created_by_user_id: str | None = None,
) -> ReviewSession:
    """Start a review session at revision 0 for one fixed processing run."""
    return ReviewSession(
        review_session_id=review_session_id,
        organization_id=organization_id,
        processing_run_id=processing_run_id,
        current_revision=0,
        created_at=created_at,
        updated_at=created_at,
        created_by_user_id=created_by_user_id,
    )


def append_review_edit_batch(
    *,
    review_session: ReviewSession,
    pending_edits: Sequence[PendingRecordEdit],
    created_at: datetime,
    created_by_user_id: str | None = None,
) -> tuple[ReviewSession, list[ReviewedRecordEdit]]:
    """Accept one edit batch, append delta rows, and advance the session revision once."""
    if not pending_edits:
        raise ValueError("pending_edits must include at least one record delta.")

    next_revision = review_session.current_revision + 1
    seen_record_keys: set[str] = set()
    persisted_edits: list[ReviewedRecordEdit] = []

    for index, pending_edit in enumerate(pending_edits):
        record_key = str(pending_edit.record_key).strip()
        if not record_key:
            raise ValueError("record_key is required for every pending edit.")
        if record_key in seen_record_keys:
            raise ValueError(f"Duplicate record_key '{record_key}' is not allowed in one accepted edit batch.")
        seen_record_keys.add(record_key)

        changed_fields = normalize_payload(pending_edit.changed_fields)
        if not changed_fields:
            raise ValueError(f"Pending edit for '{record_key}' must include at least one changed field.")

        persisted_edits.append(
            ReviewedRecordEdit(
                reviewed_record_edit_id=f"{review_session.review_session_id}:rev-{next_revision}:{index}",
                organization_id=review_session.organization_id,
                processing_run_id=review_session.processing_run_id,
                review_session_id=review_session.review_session_id,
                record_key=record_key,
                session_revision=next_revision,
                changed_fields=changed_fields,
                created_at=created_at,
                created_by_user_id=created_by_user_id,
            )
        )

    updated_session = replace(
        review_session,
        current_revision=next_revision,
        updated_at=created_at,
    )
    return updated_session, persisted_edits


def build_export_artifact(
    *,
    export_artifact_id: str,
    organization_id: str,
    processing_run: ProcessingRun,
    review_session: ReviewSession,
    session_revision: int,
    artifact_kind: str,
    storage_ref: str,
    created_at: datetime,
    template_artifact_id: str | None = None,
    created_by_user_id: str | None = None,
    file_hash: str | None = None,
) -> ExportArtifact:
    """Create export lineage for one exact review-session revision."""
    if review_session.processing_run_id != processing_run.processing_run_id:
        raise ValueError("review_session must belong to the same processing_run as the export artifact.")
    if session_revision < 0:
        raise ValueError("session_revision must be greater than or equal to 0.")
    if session_revision > review_session.current_revision:
        raise ValueError("session_revision cannot be greater than the review session's current revision.")
    storage_ref_text = str(storage_ref).strip()
    if not storage_ref_text:
        raise ValueError("storage_ref is required for export lineage.")

    return ExportArtifact(
        export_artifact_id=export_artifact_id,
        organization_id=organization_id,
        processing_run_id=processing_run.processing_run_id,
        review_session_id=review_session.review_session_id,
        session_revision=session_revision,
        artifact_kind=str(artifact_kind).strip() or "recap_workbook",
        storage_ref=storage_ref_text,
        created_at=created_at,
        template_artifact_id=template_artifact_id,
        created_by_user_id=created_by_user_id,
        file_hash=str(file_hash).strip() or None,
    )


def build_historical_export_status(profile_snapshot: ProfileSnapshot) -> HistoricalExportStatus:
    """Return the explicit historical-export posture for one persisted profile snapshot."""
    if not str(profile_snapshot.template_artifact_id or "").strip():
        return HistoricalExportStatus(
            status_code="legacy_non_reproducible",
            is_reproducible=False,
            detail=(
                "This processing run predates template-artifact capture, so historical exports cannot be "
                "reproduced exactly."
            ),
        )
    return HistoricalExportStatus(
        status_code="reproducible",
        is_reproducible=True,
        detail="Historical exports are reproducible from captured template artifact lineage.",
    )


def canonicalize_json(value: Any) -> str:
    """Canonicalize JSON-serializable data for hashing and deterministic persistence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalize_payload(value: Any) -> dict[str, Any]:
    """Normalize a record-like payload into a deterministic plain dictionary."""
    if isinstance(value, dict):
        return json.loads(canonicalize_json(value))
    if is_dataclass(value):
        return json.loads(canonicalize_json(asdict(value)))
    raise TypeError("value must be a dict or dataclass instance.")


def _coerce_optional_int(value: Any) -> int | None:
    """Coerce a possibly-empty integer field from a normalized payload."""
    if value in {None, ""}:
        return None
    return int(value)


def _coerce_optional_str(value: Any) -> str | None:
    """Coerce a possibly-empty string field from a normalized payload."""
    text = str(value or "").strip()
    return text or None
