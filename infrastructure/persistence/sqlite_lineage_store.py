"""SQLite-backed persistence helpers for phase-1 lineage contracts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core.models.lineage import (
    ExportArtifact,
    Organization,
    ProcessingRun,
    ProfileSnapshot,
    ReviewSession,
    ReviewedRecordEdit,
    RunRecord,
    SourceDocument,
    TemplateArtifact,
    TrustedProfile,
    TrustedProfileDraft,
    TrustedProfileObservation,
    TrustedProfileSyncExport,
    TrustedProfileVersion,
)
from services.lineage_service import canonicalize_json


class SqliteLineageStore:
    """Persist lineage entities into the phase-1 SQLite schema contract."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self._database_path = str(database_path)
        # FastAPI runs sync handlers in a worker threadpool, so the phase-1 API
        # slice needs one connection that can be shared across those threads.
        self._connection = sqlite3.connect(self._database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._connection.close()

    def ensure_organization(
        self,
        *,
        organization_id: str,
        slug: str,
        display_name: str,
        created_at: datetime,
        is_seeded: bool = True,
    ) -> Organization:
        """Create or reuse the single seeded organization boundary for phase 1."""
        row = self._connection.execute(
            "SELECT * FROM organizations WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
        if row is None:
            self._connection.execute(
                "INSERT INTO organizations (organization_id, slug, display_name, is_seeded, created_at) VALUES (?, ?, ?, ?, ?)",
                (organization_id, slug, display_name, int(is_seeded), _dt(created_at)),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM organizations WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()
        return _organization_from_row(row)

    def get_or_create_trusted_profile(
        self,
        trusted_profile: TrustedProfile,
    ) -> TrustedProfile:
        """Create or reuse a trusted profile by organization/profile name."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profiles WHERE organization_id = ? AND profile_name = ?",
            (trusted_profile.organization_id, trusted_profile.profile_name),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO trusted_profiles (
                    trusted_profile_id,
                    organization_id,
                    profile_name,
                    display_name,
                    source_kind,
                    bundle_ref,
                    description,
                    version_label,
                    current_published_version_id,
                    archived_at,
                    created_by_user_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trusted_profile.trusted_profile_id,
                    trusted_profile.organization_id,
                    trusted_profile.profile_name,
                    trusted_profile.display_name,
                    trusted_profile.source_kind,
                    trusted_profile.bundle_ref,
                    trusted_profile.description,
                    trusted_profile.version_label,
                    trusted_profile.current_published_version_id,
                    _dt(trusted_profile.archived_at) if trusted_profile.archived_at else None,
                    trusted_profile.created_by_user_id,
                    _dt(trusted_profile.created_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM trusted_profiles WHERE trusted_profile_id = ?",
                (trusted_profile.trusted_profile_id,),
            ).fetchone()
        else:
            self._connection.execute(
                """
                UPDATE trusted_profiles
                SET display_name = ?,
                    source_kind = ?,
                    bundle_ref = ?,
                    description = ?,
                    version_label = ?,
                    current_published_version_id = COALESCE(?, current_published_version_id),
                    archived_at = ?
                WHERE trusted_profile_id = ?
                """,
                (
                    trusted_profile.display_name,
                    trusted_profile.source_kind,
                    trusted_profile.bundle_ref,
                    trusted_profile.description,
                    trusted_profile.version_label,
                    trusted_profile.current_published_version_id,
                    _dt(trusted_profile.archived_at) if trusted_profile.archived_at else None,
                    row["trusted_profile_id"],
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM trusted_profiles WHERE trusted_profile_id = ?",
                (row["trusted_profile_id"],),
            ).fetchone()
        return _trusted_profile_from_row(row)

    def set_current_published_version(
        self,
        trusted_profile_id: str,
        trusted_profile_version_id: str,
    ) -> TrustedProfile:
        """Point one logical trusted profile at its current published version."""
        self._connection.execute(
            """
            UPDATE trusted_profiles
            SET current_published_version_id = ?
            WHERE trusted_profile_id = ?
            """,
            (trusted_profile_version_id, trusted_profile_id),
        )
        self._connection.commit()
        return self.get_trusted_profile(trusted_profile_id)

    def get_trusted_profile(self, trusted_profile_id: str) -> TrustedProfile:
        """Fetch one persisted trusted profile."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profiles WHERE trusted_profile_id = ?",
            (trusted_profile_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"TrustedProfile '{trusted_profile_id}' was not found.")
        return _trusted_profile_from_row(row)

    def get_trusted_profile_by_name(
        self,
        *,
        organization_id: str,
        profile_name: str,
    ) -> TrustedProfile:
        """Fetch one persisted trusted profile by organization/profile name."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profiles WHERE organization_id = ? AND profile_name = ?",
            (organization_id, profile_name),
        ).fetchone()
        if row is None:
            raise KeyError(f"TrustedProfile '{profile_name}' was not found in organization '{organization_id}'.")
        return _trusted_profile_from_row(row)

    def list_trusted_profiles(self, organization_id: str) -> list[TrustedProfile]:
        """List persisted logical trusted profiles for one organization."""
        return self.list_trusted_profiles_for_organization(organization_id, include_archived=False)

    def list_trusted_profiles_for_organization(
        self,
        organization_id: str,
        *,
        include_archived: bool = False,
    ) -> list[TrustedProfile]:
        """List persisted logical trusted profiles for one organization."""
        query = """
            SELECT * FROM trusted_profiles
            WHERE organization_id = ?
        """
        parameters: list[object] = [organization_id]
        if not include_archived:
            query += " AND archived_at IS NULL"
        query += " ORDER BY profile_name ASC, trusted_profile_id ASC"
        rows = self._connection.execute(query, parameters).fetchall()
        return [_trusted_profile_from_row(row) for row in rows]

    def archive_trusted_profile(
        self,
        trusted_profile_id: str,
        *,
        archived_at: datetime,
    ) -> TrustedProfile:
        """Mark one trusted profile archived without deleting lineage history."""
        self._connection.execute(
            """
            UPDATE trusted_profiles
            SET archived_at = ?
            WHERE trusted_profile_id = ?
            """,
            (_dt(archived_at), trusted_profile_id),
        )
        self._connection.commit()
        return self.get_trusted_profile(trusted_profile_id)

    def unarchive_trusted_profile(self, trusted_profile_id: str) -> TrustedProfile:
        """Clear the archived marker for one logical trusted profile."""
        self._connection.execute(
            """
            UPDATE trusted_profiles
            SET archived_at = NULL
            WHERE trusted_profile_id = ?
            """,
            (trusted_profile_id,),
        )
        self._connection.commit()
        return self.get_trusted_profile(trusted_profile_id)

    def get_or_create_template_artifact(
        self,
        template_artifact: TemplateArtifact,
    ) -> TemplateArtifact:
        """Create or reuse one immutable workbook template artifact by content hash."""
        row = self._connection.execute(
            "SELECT * FROM template_artifacts WHERE organization_id = ? AND content_hash = ?",
            (template_artifact.organization_id, template_artifact.content_hash),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO template_artifacts (
                    template_artifact_id,
                    organization_id,
                    content_hash,
                    original_filename,
                    content_bytes,
                    file_size_bytes,
                    created_by_user_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_artifact.template_artifact_id,
                    template_artifact.organization_id,
                    template_artifact.content_hash,
                    template_artifact.original_filename,
                    sqlite3.Binary(template_artifact.content_bytes),
                    template_artifact.file_size_bytes,
                    template_artifact.created_by_user_id,
                    _dt(template_artifact.created_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM template_artifacts WHERE template_artifact_id = ?",
                (template_artifact.template_artifact_id,),
            ).fetchone()
        return _template_artifact_from_row(row)

    def get_template_artifact(self, template_artifact_id: str) -> TemplateArtifact:
        """Fetch one persisted immutable workbook template artifact."""
        row = self._connection.execute(
            "SELECT * FROM template_artifacts WHERE template_artifact_id = ?",
            (template_artifact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"TemplateArtifact '{template_artifact_id}' was not found.")
        return _template_artifact_from_row(row)

    def get_or_create_trusted_profile_version(
        self,
        trusted_profile_version: TrustedProfileVersion,
    ) -> TrustedProfileVersion:
        """Create or reuse one immutable published trusted-profile version by content hash."""
        row = self._connection.execute(
            """
            SELECT * FROM trusted_profile_versions
            WHERE organization_id = ? AND trusted_profile_id = ? AND content_hash = ?
            """,
            (
                trusted_profile_version.organization_id,
                trusted_profile_version.trusted_profile_id,
                trusted_profile_version.content_hash,
            ),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO trusted_profile_versions (
                    trusted_profile_version_id,
                    organization_id,
                    trusted_profile_id,
                    version_number,
                    base_trusted_profile_version_id,
                    bundle_json,
                    content_hash,
                    template_artifact_id,
                    template_artifact_ref,
                    template_file_hash,
                    source_kind,
                    created_by_user_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trusted_profile_version.trusted_profile_version_id,
                    trusted_profile_version.organization_id,
                    trusted_profile_version.trusted_profile_id,
                    trusted_profile_version.version_number,
                    trusted_profile_version.base_trusted_profile_version_id,
                    trusted_profile_version.canonical_bundle_json,
                    trusted_profile_version.content_hash,
                    trusted_profile_version.template_artifact_id,
                    trusted_profile_version.template_artifact_ref,
                    trusted_profile_version.template_file_hash,
                    trusted_profile_version.source_kind,
                    trusted_profile_version.created_by_user_id,
                    _dt(trusted_profile_version.created_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM trusted_profile_versions WHERE trusted_profile_version_id = ?",
                (trusted_profile_version.trusted_profile_version_id,),
            ).fetchone()
        return _trusted_profile_version_from_row(row)

    def get_trusted_profile_version(self, trusted_profile_version_id: str) -> TrustedProfileVersion:
        """Fetch one immutable published trusted-profile version."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profile_versions WHERE trusted_profile_version_id = ?",
            (trusted_profile_version_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"TrustedProfileVersion '{trusted_profile_version_id}' was not found.")
        return _trusted_profile_version_from_row(row)

    def get_current_trusted_profile_version(self, trusted_profile_id: str) -> TrustedProfileVersion:
        """Fetch the current published version for one logical trusted profile."""
        row = self._connection.execute(
            """
            SELECT version.*
            FROM trusted_profiles profile
            JOIN trusted_profile_versions version
              ON version.trusted_profile_version_id = profile.current_published_version_id
            WHERE profile.trusted_profile_id = ?
            """,
            (trusted_profile_id,),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"TrustedProfile '{trusted_profile_id}' does not have a current published version."
            )
        return _trusted_profile_version_from_row(row)

    def list_trusted_profile_versions(self, trusted_profile_id: str) -> list[TrustedProfileVersion]:
        """List immutable published versions for one logical trusted profile."""
        rows = self._connection.execute(
            """
            SELECT * FROM trusted_profile_versions
            WHERE trusted_profile_id = ?
            ORDER BY version_number ASC, created_at ASC
            """,
            (trusted_profile_id,),
        ).fetchall()
        return [_trusted_profile_version_from_row(row) for row in rows]

    def get_next_trusted_profile_version_number(self, trusted_profile_id: str) -> int:
        """Return the next sequential version number for one logical trusted profile."""
        row = self._connection.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) AS max_version_number
            FROM trusted_profile_versions
            WHERE trusted_profile_id = ?
            """,
            (trusted_profile_id,),
        ).fetchone()
        return int(row["max_version_number"] or 0) + 1

    def get_or_create_profile_snapshot(
        self,
        snapshot: ProfileSnapshot,
    ) -> ProfileSnapshot:
        """Create or reuse an immutable profile snapshot by content hash."""
        row = self._connection.execute(
            "SELECT * FROM profile_snapshots WHERE organization_id = ? AND content_hash = ?",
            (snapshot.organization_id, snapshot.content_hash),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO profile_snapshots (
                    profile_snapshot_id,
                    organization_id,
                    trusted_profile_id,
                    trusted_profile_version_id,
                    template_artifact_id,
                    content_hash,
                    bundle_json,
                    engine_version,
                    template_artifact_ref,
                    template_file_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.profile_snapshot_id,
                    snapshot.organization_id,
                    snapshot.trusted_profile_id,
                    snapshot.trusted_profile_version_id,
                    snapshot.template_artifact_id,
                    snapshot.content_hash,
                    snapshot.canonical_bundle_json,
                    snapshot.engine_version,
                    snapshot.template_artifact_ref,
                    snapshot.template_file_hash,
                    _dt(snapshot.created_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM profile_snapshots WHERE profile_snapshot_id = ?",
                (snapshot.profile_snapshot_id,),
            ).fetchone()
        return _profile_snapshot_from_row(row)

    def get_profile_snapshot(self, profile_snapshot_id: str) -> ProfileSnapshot:
        """Fetch one persisted profile snapshot."""
        row = self._connection.execute(
            "SELECT * FROM profile_snapshots WHERE profile_snapshot_id = ?",
            (profile_snapshot_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"ProfileSnapshot '{profile_snapshot_id}' was not found.")
        return _profile_snapshot_from_row(row)

    def get_open_trusted_profile_draft(self, trusted_profile_id: str) -> TrustedProfileDraft:
        """Fetch the single open draft for one logical trusted profile."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profile_drafts WHERE trusted_profile_id = ?",
            (trusted_profile_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"TrustedProfileDraft for '{trusted_profile_id}' was not found.")
        return _trusted_profile_draft_from_row(row)

    def get_trusted_profile_draft(self, trusted_profile_draft_id: str) -> TrustedProfileDraft:
        """Fetch one trusted-profile draft by id."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profile_drafts WHERE trusted_profile_draft_id = ?",
            (trusted_profile_draft_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"TrustedProfileDraft '{trusted_profile_draft_id}' was not found.")
        return _trusted_profile_draft_from_row(row)

    def get_or_create_trusted_profile_draft(
        self,
        draft: TrustedProfileDraft,
    ) -> TrustedProfileDraft:
        """Create or reuse the single open draft for one logical trusted profile."""
        row = self._connection.execute(
            "SELECT * FROM trusted_profile_drafts WHERE trusted_profile_id = ?",
            (draft.trusted_profile_id,),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO trusted_profile_drafts (
                    trusted_profile_draft_id,
                    organization_id,
                    trusted_profile_id,
                    base_trusted_profile_version_id,
                    bundle_json,
                    content_hash,
                    template_artifact_id,
                    template_artifact_ref,
                    template_file_hash,
                    status,
                    created_by_user_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.trusted_profile_draft_id,
                    draft.organization_id,
                    draft.trusted_profile_id,
                    draft.base_trusted_profile_version_id,
                    draft.canonical_bundle_json,
                    draft.content_hash,
                    draft.template_artifact_id,
                    draft.template_artifact_ref,
                    draft.template_file_hash,
                    draft.status,
                    draft.created_by_user_id,
                    _dt(draft.created_at),
                    _dt(draft.updated_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM trusted_profile_drafts WHERE trusted_profile_draft_id = ?",
                (draft.trusted_profile_draft_id,),
            ).fetchone()
        return _trusted_profile_draft_from_row(row)

    def save_trusted_profile_draft(
        self,
        draft: TrustedProfileDraft,
    ) -> TrustedProfileDraft:
        """Persist the current mutable state for one trusted-profile draft."""
        self._connection.execute(
            """
            UPDATE trusted_profile_drafts
            SET bundle_json = ?,
                content_hash = ?,
                template_artifact_id = ?,
                template_artifact_ref = ?,
                template_file_hash = ?,
                status = ?,
                updated_at = ?
            WHERE trusted_profile_draft_id = ?
            """,
            (
                draft.canonical_bundle_json,
                draft.content_hash,
                draft.template_artifact_id,
                draft.template_artifact_ref,
                draft.template_file_hash,
                draft.status,
                _dt(draft.updated_at),
                draft.trusted_profile_draft_id,
            ),
        )
        self._connection.commit()
        return self.get_trusted_profile_draft(draft.trusted_profile_draft_id)

    def delete_trusted_profile_draft(self, trusted_profile_draft_id: str) -> None:
        """Delete one trusted-profile draft once it is no longer the open working copy."""
        self._connection.execute(
            "DELETE FROM trusted_profile_drafts WHERE trusted_profile_draft_id = ?",
            (trusted_profile_draft_id,),
        )
        self._connection.commit()

    def upsert_trusted_profile_observation(
        self,
        observation: TrustedProfileObservation,
    ) -> TrustedProfileObservation:
        """Insert or update one observed unmapped raw value for a trusted profile."""
        row = self._connection.execute(
            """
            SELECT * FROM trusted_profile_observations
            WHERE trusted_profile_id = ? AND observation_domain = ? AND canonical_raw_key = ?
            """,
            (
                observation.trusted_profile_id,
                observation.observation_domain,
                observation.canonical_raw_key,
            ),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO trusted_profile_observations (
                    trusted_profile_observation_id,
                    organization_id,
                    trusted_profile_id,
                    observation_domain,
                    canonical_raw_key,
                    raw_display_value,
                    first_seen_processing_run_id,
                    last_seen_processing_run_id,
                    first_seen_at,
                    last_seen_at,
                    draft_applied_at,
                    is_resolved,
                    resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.trusted_profile_observation_id,
                    observation.organization_id,
                    observation.trusted_profile_id,
                    observation.observation_domain,
                    observation.canonical_raw_key,
                    observation.raw_display_value,
                    observation.first_seen_processing_run_id,
                    observation.last_seen_processing_run_id,
                    _dt(observation.first_seen_at),
                    _dt(observation.last_seen_at),
                    _dt(observation.draft_applied_at) if observation.draft_applied_at else None,
                    int(observation.is_resolved),
                    _dt(observation.resolved_at) if observation.resolved_at else None,
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM trusted_profile_observations WHERE trusted_profile_observation_id = ?",
                (observation.trusted_profile_observation_id,),
            ).fetchone()
        else:
            self._connection.execute(
                """
                UPDATE trusted_profile_observations
                SET raw_display_value = CASE
                        WHEN TRIM(COALESCE(raw_display_value, '')) = '' THEN ?
                        ELSE raw_display_value
                    END,
                    last_seen_processing_run_id = COALESCE(?, last_seen_processing_run_id),
                    last_seen_at = ?,
                    draft_applied_at = COALESCE(?, draft_applied_at),
                    is_resolved = ?,
                    resolved_at = COALESCE(?, resolved_at)
                WHERE trusted_profile_observation_id = ?
                """,
                (
                    observation.raw_display_value,
                    observation.last_seen_processing_run_id,
                    _dt(observation.last_seen_at),
                    _dt(observation.draft_applied_at) if observation.draft_applied_at else None,
                    int(observation.is_resolved),
                    _dt(observation.resolved_at) if observation.resolved_at else None,
                    row["trusted_profile_observation_id"],
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM trusted_profile_observations WHERE trusted_profile_observation_id = ?",
                (row["trusted_profile_observation_id"],),
            ).fetchone()
        return _trusted_profile_observation_from_row(row)

    def get_trusted_profile_observation(
        self,
        trusted_profile_id: str,
        observation_domain: str,
        canonical_raw_key: str,
    ) -> TrustedProfileObservation:
        """Fetch one observed unmapped raw value by trusted profile, domain, and key."""
        row = self._connection.execute(
            """
            SELECT * FROM trusted_profile_observations
            WHERE trusted_profile_id = ? AND observation_domain = ? AND canonical_raw_key = ?
            """,
            (trusted_profile_id, observation_domain, canonical_raw_key),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"TrustedProfileObservation '{trusted_profile_id}:{observation_domain}:{canonical_raw_key}' "
                "was not found."
            )
        return _trusted_profile_observation_from_row(row)

    def list_trusted_profile_observations(
        self,
        trusted_profile_id: str,
        *,
        observation_domain: str | None = None,
        unresolved_only: bool = False,
        unmerged_only: bool = False,
    ) -> list[TrustedProfileObservation]:
        """List observed unmapped values for one logical trusted profile with optional filters."""
        query = """
            SELECT * FROM trusted_profile_observations
            WHERE trusted_profile_id = ?
        """
        parameters: list[object] = [trusted_profile_id]
        if observation_domain:
            query += " AND observation_domain = ?"
            parameters.append(observation_domain)
        if unresolved_only:
            query += " AND is_resolved = 0"
        if unmerged_only:
            query += " AND draft_applied_at IS NULL"
        query += " ORDER BY observation_domain ASC, canonical_raw_key ASC"
        rows = self._connection.execute(query, tuple(parameters)).fetchall()
        return [_trusted_profile_observation_from_row(row) for row in rows]

    def create_trusted_profile_sync_export(
        self,
        sync_export: TrustedProfileSyncExport,
    ) -> TrustedProfileSyncExport:
        """Persist one trusted-profile sync-export audit record."""
        self._connection.execute(
            """
            INSERT INTO trusted_profile_sync_exports (
                trusted_profile_sync_export_id,
                organization_id,
                trusted_profile_version_id,
                artifact_storage_ref,
                artifact_file_hash,
                manifest_json,
                created_by_user_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sync_export.trusted_profile_sync_export_id,
                sync_export.organization_id,
                sync_export.trusted_profile_version_id,
                sync_export.artifact_storage_ref,
                sync_export.artifact_file_hash,
                sync_export.manifest_json,
                sync_export.created_by_user_id,
                _dt(sync_export.created_at),
            ),
        )
        self._connection.commit()
        return self.get_trusted_profile_sync_export(sync_export.trusted_profile_sync_export_id)

    def get_trusted_profile_sync_export(
        self,
        trusted_profile_sync_export_id: str,
    ) -> TrustedProfileSyncExport:
        """Fetch one trusted-profile sync-export audit record."""
        row = self._connection.execute(
            """
            SELECT * FROM trusted_profile_sync_exports
            WHERE trusted_profile_sync_export_id = ?
            """,
            (trusted_profile_sync_export_id,),
        ).fetchone()
        if row is None:
            raise KeyError(
                f"TrustedProfileSyncExport '{trusted_profile_sync_export_id}' was not found."
            )
        return _trusted_profile_sync_export_from_row(row)

    def get_or_create_source_document(
        self,
        source_document: SourceDocument,
    ) -> SourceDocument:
        """Create or reuse a source document by file hash and storage ref."""
        row = self._connection.execute(
            "SELECT * FROM source_documents WHERE organization_id = ? AND file_hash = ? AND storage_ref = ?",
            (source_document.organization_id, source_document.file_hash, source_document.storage_ref),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO source_documents (
                    source_document_id,
                    organization_id,
                    original_filename,
                    file_hash,
                    storage_ref,
                    content_type,
                    file_size_bytes,
                    uploaded_by_user_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_document.source_document_id,
                    source_document.organization_id,
                    source_document.original_filename,
                    source_document.file_hash,
                    source_document.storage_ref,
                    source_document.content_type,
                    source_document.file_size_bytes,
                    source_document.uploaded_by_user_id,
                    _dt(source_document.created_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM source_documents WHERE source_document_id = ?",
                (source_document.source_document_id,),
            ).fetchone()
        return _source_document_from_row(row)

    def get_source_document(self, source_document_id: str) -> SourceDocument:
        """Fetch one persisted source document."""
        row = self._connection.execute(
            "SELECT * FROM source_documents WHERE source_document_id = ?",
            (source_document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"SourceDocument '{source_document_id}' was not found.")
        return _source_document_from_row(row)

    def create_processing_run(self, processing_run: ProcessingRun) -> ProcessingRun:
        """Persist one immutable processing run."""
        self._connection.execute(
            """
            INSERT INTO processing_runs (
                processing_run_id,
                organization_id,
                source_document_id,
                profile_snapshot_id,
                trusted_profile_id,
                trusted_profile_version_id,
                status,
                engine_version,
                aggregate_blockers_json,
                created_by_user_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                processing_run.processing_run_id,
                processing_run.organization_id,
                processing_run.source_document_id,
                processing_run.profile_snapshot_id,
                processing_run.trusted_profile_id,
                processing_run.trusted_profile_version_id,
                processing_run.status,
                processing_run.engine_version,
                json.dumps(list(processing_run.aggregate_blockers)),
                processing_run.created_by_user_id,
                _dt(processing_run.created_at),
            ),
        )
        self._connection.commit()
        return self.get_processing_run(processing_run.processing_run_id)

    def create_run_records(self, run_records: list[RunRecord]) -> list[RunRecord]:
        """Persist immutable ordered run records for one processing run."""
        self._connection.executemany(
            """
            INSERT INTO run_records (
                run_record_id,
                organization_id,
                processing_run_id,
                record_key,
                record_index,
                canonical_record_json,
                source_page,
                source_line_text,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_record.run_record_id,
                    run_record.organization_id,
                    run_record.processing_run_id,
                    run_record.record_key,
                    run_record.record_index,
                    canonicalize_json(run_record.canonical_record),
                    run_record.source_page,
                    run_record.source_line_text,
                    _dt(run_record.created_at),
                )
                for run_record in run_records
            ],
        )
        self._connection.commit()
        if not run_records:
            return []
        return self.list_run_records(run_records[0].processing_run_id)

    def get_processing_run(self, processing_run_id: str) -> ProcessingRun:
        """Fetch one persisted processing run."""
        row = self._connection.execute(
            "SELECT * FROM processing_runs WHERE processing_run_id = ?",
            (processing_run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"ProcessingRun '{processing_run_id}' was not found.")
        return _processing_run_from_row(row)

    def list_run_records(self, processing_run_id: str) -> list[RunRecord]:
        """Fetch persisted run records in immutable emitted order."""
        rows = self._connection.execute(
            "SELECT * FROM run_records WHERE processing_run_id = ? ORDER BY record_index ASC",
            (processing_run_id,),
        ).fetchall()
        return [_run_record_from_row(row) for row in rows]

    def list_processing_runs(self) -> list[ProcessingRun]:
        """Return all processing runs in creation order for tests and service verification."""
        rows = self._connection.execute(
            "SELECT * FROM processing_runs ORDER BY created_at ASC, processing_run_id ASC"
        ).fetchall()
        return [_processing_run_from_row(row) for row in rows]

    def get_or_create_review_session(self, review_session: ReviewSession) -> ReviewSession:
        """Create or reuse the phase-1 primary review session for one processing run."""
        row = self._connection.execute(
            "SELECT * FROM review_sessions WHERE processing_run_id = ?",
            (review_session.processing_run_id,),
        ).fetchone()
        if row is None:
            self._connection.execute(
                """
                INSERT INTO review_sessions (
                    review_session_id,
                    organization_id,
                    processing_run_id,
                    current_revision,
                    created_by_user_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_session.review_session_id,
                    review_session.organization_id,
                    review_session.processing_run_id,
                    review_session.current_revision,
                    review_session.created_by_user_id,
                    _dt(review_session.created_at),
                    _dt(review_session.updated_at),
                ),
            )
            self._connection.commit()
            row = self._connection.execute(
                "SELECT * FROM review_sessions WHERE review_session_id = ?",
                (review_session.review_session_id,),
            ).fetchone()
        return _review_session_from_row(row)

    def get_review_session(self, review_session_id: str) -> ReviewSession:
        """Fetch one persisted review session."""
        row = self._connection.execute(
            "SELECT * FROM review_sessions WHERE review_session_id = ?",
            (review_session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"ReviewSession '{review_session_id}' was not found.")
        return _review_session_from_row(row)

    def get_review_session_for_run(self, processing_run_id: str) -> ReviewSession:
        """Fetch the phase-1 primary review session for one processing run."""
        row = self._connection.execute(
            "SELECT * FROM review_sessions WHERE processing_run_id = ?",
            (processing_run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"ReviewSession for ProcessingRun '{processing_run_id}' was not found.")
        return _review_session_from_row(row)

    def save_review_session_edits(
        self,
        review_session: ReviewSession,
        reviewed_record_edits: list[ReviewedRecordEdit],
    ) -> ReviewSession:
        """Persist one accepted edit batch and the session revision it advanced."""
        with self._connection:
            self._connection.execute(
                """
                UPDATE review_sessions
                SET current_revision = ?, updated_at = ?
                WHERE review_session_id = ?
                """,
                (
                    review_session.current_revision,
                    _dt(review_session.updated_at),
                    review_session.review_session_id,
                ),
            )
            self._connection.executemany(
                """
                INSERT INTO reviewed_record_edits (
                    reviewed_record_edit_id,
                    organization_id,
                    processing_run_id,
                    review_session_id,
                    record_key,
                    session_revision,
                    changed_fields_json,
                    created_by_user_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        edit.reviewed_record_edit_id,
                        edit.organization_id,
                        edit.processing_run_id,
                        edit.review_session_id,
                        edit.record_key,
                        edit.session_revision,
                        canonicalize_json(edit.changed_fields),
                        edit.created_by_user_id,
                        _dt(edit.created_at),
                    )
                    for edit in reviewed_record_edits
                ],
            )
        return self.get_review_session(review_session.review_session_id)

    def list_reviewed_record_edits(
        self,
        review_session_id: str,
        *,
        up_to_revision: int | None = None,
    ) -> list[ReviewedRecordEdit]:
        """Fetch persisted review delta rows in revision order."""
        query = (
            "SELECT * FROM reviewed_record_edits WHERE review_session_id = ? "
            "ORDER BY session_revision ASC, created_at ASC, reviewed_record_edit_id ASC"
        )
        parameters: tuple[object, ...] = (review_session_id,)
        if up_to_revision is not None:
            query = (
                "SELECT * FROM reviewed_record_edits WHERE review_session_id = ? AND session_revision <= ? "
                "ORDER BY session_revision ASC, created_at ASC, reviewed_record_edit_id ASC"
            )
            parameters = (review_session_id, up_to_revision)
        rows = self._connection.execute(query, parameters).fetchall()
        return [_reviewed_record_edit_from_row(row) for row in rows]

    def create_export_artifact(self, export_artifact: ExportArtifact) -> ExportArtifact:
        """Persist export lineage for one exact review-session revision."""
        self._connection.execute(
            """
            INSERT INTO export_artifacts (
                export_artifact_id,
                organization_id,
                processing_run_id,
                review_session_id,
                session_revision,
                artifact_kind,
                storage_ref,
                template_artifact_id,
                file_hash,
                created_by_user_id,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                export_artifact.export_artifact_id,
                export_artifact.organization_id,
                export_artifact.processing_run_id,
                export_artifact.review_session_id,
                export_artifact.session_revision,
                export_artifact.artifact_kind,
                export_artifact.storage_ref,
                export_artifact.template_artifact_id,
                export_artifact.file_hash,
                export_artifact.created_by_user_id,
                _dt(export_artifact.created_at),
            ),
        )
        self._connection.commit()
        return self.get_export_artifact(export_artifact.export_artifact_id)

    def get_export_artifact(self, export_artifact_id: str) -> ExportArtifact:
        """Fetch one persisted export artifact."""
        row = self._connection.execute(
            "SELECT * FROM export_artifacts WHERE export_artifact_id = ?",
            (export_artifact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"ExportArtifact '{export_artifact_id}' was not found.")
        return _export_artifact_from_row(row)

    def list_export_artifacts(self, review_session_id: str) -> list[ExportArtifact]:
        """Fetch export artifacts in creation order for one review session."""
        rows = self._connection.execute(
            """
            SELECT * FROM export_artifacts
            WHERE review_session_id = ?
            ORDER BY created_at ASC, export_artifact_id ASC
            """,
            (review_session_id,),
        ).fetchall()
        return [_export_artifact_from_row(row) for row in rows]

    def _initialize_schema(self) -> None:
        """Create the phase-1 persistence schema when the store starts."""
        schema_path = Path(__file__).with_name("phase1_lineage_schema.sql")
        self._connection.executescript(schema_path.read_text(encoding="utf-8"))
        self._ensure_column(
            "trusted_profiles",
            "current_published_version_id",
            "TEXT REFERENCES trusted_profile_versions (trusted_profile_version_id)",
        )
        self._ensure_column(
            "trusted_profiles",
            "archived_at",
            "TEXT",
        )
        self._ensure_column(
            "profile_snapshots",
            "trusted_profile_version_id",
            "TEXT REFERENCES trusted_profile_versions (trusted_profile_version_id)",
        )
        self._ensure_column(
            "processing_runs",
            "trusted_profile_version_id",
            "TEXT REFERENCES trusted_profile_versions (trusted_profile_version_id)",
        )
        self._connection.commit()

    def _ensure_column(self, table_name: str, column_name: str, column_sql: str) -> None:
        """Add a missing column to an existing table for additive schema evolution."""
        existing_columns = {
            row["name"]
            for row in self._connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        self._connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _dt(value: datetime) -> str:
    """Serialize datetimes for persistence."""
    return value.isoformat()


def _parse_dt(value: str) -> datetime:
    """Parse persisted datetimes from SQLite."""
    return datetime.fromisoformat(value)


def _organization_from_row(row: sqlite3.Row) -> Organization:
    return Organization(
        organization_id=row["organization_id"],
        slug=row["slug"],
        display_name=row["display_name"],
        is_seeded=bool(row["is_seeded"]),
        created_at=_parse_dt(row["created_at"]),
    )


def _trusted_profile_from_row(row: sqlite3.Row) -> TrustedProfile:
    return TrustedProfile(
        trusted_profile_id=row["trusted_profile_id"],
        organization_id=row["organization_id"],
        profile_name=row["profile_name"],
        display_name=row["display_name"],
        source_kind=row["source_kind"],
        bundle_ref=row["bundle_ref"],
        description=row["description"],
        version_label=row["version_label"],
        current_published_version_id=row["current_published_version_id"],
        archived_at=_parse_dt(row["archived_at"]) if row["archived_at"] else None,
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _trusted_profile_version_from_row(row: sqlite3.Row) -> TrustedProfileVersion:
    bundle_json = row["bundle_json"]
    return TrustedProfileVersion(
        trusted_profile_version_id=row["trusted_profile_version_id"],
        organization_id=row["organization_id"],
        trusted_profile_id=row["trusted_profile_id"],
        version_number=int(row["version_number"]),
        bundle_payload=json.loads(bundle_json),
        canonical_bundle_json=bundle_json,
        content_hash=row["content_hash"],
        base_trusted_profile_version_id=row["base_trusted_profile_version_id"],
        template_artifact_id=row["template_artifact_id"],
        template_artifact_ref=row["template_artifact_ref"],
        template_file_hash=row["template_file_hash"],
        source_kind=row["source_kind"],
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _trusted_profile_draft_from_row(row: sqlite3.Row) -> TrustedProfileDraft:
    bundle_json = row["bundle_json"]
    return TrustedProfileDraft(
        trusted_profile_draft_id=row["trusted_profile_draft_id"],
        organization_id=row["organization_id"],
        trusted_profile_id=row["trusted_profile_id"],
        bundle_payload=json.loads(bundle_json),
        canonical_bundle_json=bundle_json,
        content_hash=row["content_hash"],
        base_trusted_profile_version_id=row["base_trusted_profile_version_id"],
        template_artifact_id=row["template_artifact_id"],
        template_artifact_ref=row["template_artifact_ref"],
        template_file_hash=row["template_file_hash"],
        status=row["status"],
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _trusted_profile_observation_from_row(row: sqlite3.Row) -> TrustedProfileObservation:
    return TrustedProfileObservation(
        trusted_profile_observation_id=row["trusted_profile_observation_id"],
        organization_id=row["organization_id"],
        trusted_profile_id=row["trusted_profile_id"],
        observation_domain=row["observation_domain"],
        canonical_raw_key=row["canonical_raw_key"],
        raw_display_value=row["raw_display_value"],
        first_seen_processing_run_id=row["first_seen_processing_run_id"],
        last_seen_processing_run_id=row["last_seen_processing_run_id"],
        first_seen_at=_parse_dt(row["first_seen_at"]),
        last_seen_at=_parse_dt(row["last_seen_at"]),
        draft_applied_at=_parse_dt(row["draft_applied_at"]) if row["draft_applied_at"] else None,
        is_resolved=bool(row["is_resolved"]),
        resolved_at=_parse_dt(row["resolved_at"]) if row["resolved_at"] else None,
    )


def _trusted_profile_sync_export_from_row(row: sqlite3.Row) -> TrustedProfileSyncExport:
    return TrustedProfileSyncExport(
        trusted_profile_sync_export_id=row["trusted_profile_sync_export_id"],
        organization_id=row["organization_id"],
        trusted_profile_version_id=row["trusted_profile_version_id"],
        artifact_storage_ref=row["artifact_storage_ref"],
        artifact_file_hash=row["artifact_file_hash"],
        manifest_json=row["manifest_json"],
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _profile_snapshot_from_row(row: sqlite3.Row) -> ProfileSnapshot:
    bundle_json = row["bundle_json"]
    return ProfileSnapshot(
        profile_snapshot_id=row["profile_snapshot_id"],
        organization_id=row["organization_id"],
        trusted_profile_id=row["trusted_profile_id"],
        trusted_profile_version_id=row["trusted_profile_version_id"],
        template_artifact_id=row["template_artifact_id"],
        content_hash=row["content_hash"],
        bundle_payload=json.loads(bundle_json),
        canonical_bundle_json=bundle_json,
        engine_version=row["engine_version"],
        template_artifact_ref=row["template_artifact_ref"],
        template_file_hash=row["template_file_hash"],
        created_at=_parse_dt(row["created_at"]),
    )


def _source_document_from_row(row: sqlite3.Row) -> SourceDocument:
    return SourceDocument(
        source_document_id=row["source_document_id"],
        organization_id=row["organization_id"],
        original_filename=row["original_filename"],
        file_hash=row["file_hash"],
        storage_ref=row["storage_ref"],
        content_type=row["content_type"],
        file_size_bytes=row["file_size_bytes"],
        uploaded_by_user_id=row["uploaded_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _processing_run_from_row(row: sqlite3.Row) -> ProcessingRun:
        return ProcessingRun(
            processing_run_id=row["processing_run_id"],
            organization_id=row["organization_id"],
            source_document_id=row["source_document_id"],
            profile_snapshot_id=row["profile_snapshot_id"],
            trusted_profile_id=row["trusted_profile_id"],
            trusted_profile_version_id=row["trusted_profile_version_id"],
            status=row["status"],
        engine_version=row["engine_version"],
        aggregate_blockers=tuple(json.loads(row["aggregate_blockers_json"])),
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _run_record_from_row(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_record_id=row["run_record_id"],
        organization_id=row["organization_id"],
        processing_run_id=row["processing_run_id"],
        record_key=row["record_key"],
        record_index=int(row["record_index"]),
        canonical_record=json.loads(row["canonical_record_json"]),
        source_page=row["source_page"],
        source_line_text=row["source_line_text"],
        created_at=_parse_dt(row["created_at"]),
    )


def _review_session_from_row(row: sqlite3.Row) -> ReviewSession:
    return ReviewSession(
        review_session_id=row["review_session_id"],
        organization_id=row["organization_id"],
        processing_run_id=row["processing_run_id"],
        current_revision=int(row["current_revision"]),
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _reviewed_record_edit_from_row(row: sqlite3.Row) -> ReviewedRecordEdit:
    return ReviewedRecordEdit(
        reviewed_record_edit_id=row["reviewed_record_edit_id"],
        organization_id=row["organization_id"],
        processing_run_id=row["processing_run_id"],
        review_session_id=row["review_session_id"],
        record_key=row["record_key"],
        session_revision=int(row["session_revision"]),
        changed_fields=json.loads(row["changed_fields_json"]),
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )


def _export_artifact_from_row(row: sqlite3.Row) -> ExportArtifact:
    return ExportArtifact(
        export_artifact_id=row["export_artifact_id"],
        organization_id=row["organization_id"],
        processing_run_id=row["processing_run_id"],
        review_session_id=row["review_session_id"],
        session_revision=int(row["session_revision"]),
        artifact_kind=row["artifact_kind"],
        storage_ref=row["storage_ref"],
        template_artifact_id=row["template_artifact_id"],
        created_by_user_id=row["created_by_user_id"],
        file_hash=row["file_hash"],
        created_at=_parse_dt(row["created_at"]),
    )


def _template_artifact_from_row(row: sqlite3.Row) -> TemplateArtifact:
    return TemplateArtifact(
        template_artifact_id=row["template_artifact_id"],
        organization_id=row["organization_id"],
        content_hash=row["content_hash"],
        original_filename=row["original_filename"],
        content_bytes=bytes(row["content_bytes"]),
        file_size_bytes=row["file_size_bytes"],
        created_by_user_id=row["created_by_user_id"],
        created_at=_parse_dt(row["created_at"]),
    )
