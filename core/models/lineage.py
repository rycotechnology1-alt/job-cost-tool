"""Portable lineage models for phase-1 processing, review, and export persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Organization:
    """Seeded or future organization boundary for persisted workflow entities."""

    organization_id: str
    slug: str
    display_name: str
    created_at: datetime
    is_seeded: bool = False


@dataclass(frozen=True, slots=True)
class User:
    """Authenticated user within one organization."""

    user_id: str
    organization_id: str
    email: str
    display_name: str
    created_at: datetime
    auth_subject: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class TrustedProfile:
    """Imported or seeded trusted profile bundle available for reproducible processing."""

    trusted_profile_id: str
    organization_id: str
    profile_name: str
    display_name: str
    created_at: datetime
    source_kind: str = "imported"
    created_by_user_id: str | None = None
    bundle_ref: str | None = None
    description: str = ""
    version_label: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    """Immutable effective profile/config bundle captured for one processing run."""

    profile_snapshot_id: str
    organization_id: str
    content_hash: str
    bundle_payload: dict[str, Any]
    canonical_bundle_json: str
    engine_version: str
    created_at: datetime
    trusted_profile_id: str | None = None
    template_artifact_id: str | None = None
    template_artifact_ref: str | None = None
    template_file_hash: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateArtifact:
    """Immutable workbook template content captured for reproducible export."""

    template_artifact_id: str
    organization_id: str
    content_hash: str
    original_filename: str
    content_bytes: bytes
    created_at: datetime
    file_size_bytes: int | None = None
    created_by_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class HistoricalExportStatus:
    """Whether one run can reproduce historical exports exactly from captured lineage."""

    status_code: str
    is_reproducible: bool
    detail: str


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Uploaded input document tracked as an immutable source artifact."""

    source_document_id: str
    organization_id: str
    original_filename: str
    file_hash: str
    storage_ref: str
    created_at: datetime
    uploaded_by_user_id: str | None = None
    content_type: str = "application/pdf"
    file_size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class ProcessingRun:
    """Immutable result of processing one source document against one profile snapshot."""

    processing_run_id: str
    organization_id: str
    source_document_id: str
    profile_snapshot_id: str
    status: str
    engine_version: str
    aggregate_blockers: tuple[str, ...]
    created_at: datetime
    trusted_profile_id: str | None = None
    created_by_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Immutable canonical emitted review row captured inside one processing run."""

    run_record_id: str
    organization_id: str
    processing_run_id: str
    record_key: str
    record_index: int
    canonical_record: dict[str, Any]
    created_at: datetime
    source_page: int | None = None
    source_line_text: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewSession:
    """Review overlay lineage anchored to one immutable processing run."""

    review_session_id: str
    organization_id: str
    processing_run_id: str
    current_revision: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewedRecordEdit:
    """Append-only review delta event for one record in one session revision."""

    reviewed_record_edit_id: str
    organization_id: str
    processing_run_id: str
    review_session_id: str
    record_key: str
    session_revision: int
    changed_fields: dict[str, Any]
    created_at: datetime
    created_by_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    """Export artifact generated from one exact review-session revision."""

    export_artifact_id: str
    organization_id: str
    processing_run_id: str
    review_session_id: str
    session_revision: int
    artifact_kind: str
    storage_ref: str
    created_at: datetime
    template_artifact_id: str | None = None
    created_by_user_id: str | None = None
    file_hash: str | None = None


@dataclass(frozen=True, slots=True)
class PendingRecordEdit:
    """Requested field changes for one record before a revision is accepted."""

    record_key: str
    changed_fields: dict[str, Any] = field(default_factory=dict)
