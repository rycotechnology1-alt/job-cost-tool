"""Persistence protocol for lineage operations used by the web/API workflow."""

from __future__ import annotations

from typing import Protocol

from core.models.lineage import (
    ExportArtifact,
    Organization,
    ProcessingRun,
    ProfileSnapshot,
    ReviewedRecordEdit,
    ReviewSession,
    RunRecord,
    SourceDocument,
    TemplateArtifact,
    TrustedProfile,
    TrustedProfileDraft,
    TrustedProfileObservation,
    TrustedProfileVersion,
    User,
)


class LineageStore(Protocol):
    """Persistence contract consumed by the current web/API services.

    Draft rows carry `draft_revision` so future conflict-safe writes can compare
    persisted state without widening the protocol yet.
    """

    def close(self) -> None: ...

    def ensure_organization(
        self,
        *,
        organization_id: str,
        slug: str,
        display_name: str,
        created_at,
        is_seeded: bool = False,
    ) -> Organization: ...

    def get_organization(self, organization_id: str) -> Organization: ...

    def set_organization_default_trusted_profile(
        self,
        *,
        organization_id: str,
        trusted_profile_id: str,
    ) -> Organization: ...

    def ensure_user(self, user: User) -> User: ...

    def get_or_create_trusted_profile(self, trusted_profile: TrustedProfile) -> TrustedProfile: ...

    def set_current_published_version(
        self,
        trusted_profile_id: str,
        trusted_profile_version_id: str,
    ) -> TrustedProfile: ...

    def get_trusted_profile_for_organization(
        self,
        *,
        organization_id: str,
        trusted_profile_id: str,
    ) -> TrustedProfile: ...

    def get_trusted_profile_by_name(
        self,
        *,
        organization_id: str,
        profile_name: str,
    ) -> TrustedProfile: ...

    def list_trusted_profiles_for_organization(
        self,
        organization_id: str,
        *,
        include_archived: bool = False,
    ) -> list[TrustedProfile]: ...

    def archive_trusted_profile(self, trusted_profile_id: str, *, archived_at) -> TrustedProfile: ...

    def unarchive_trusted_profile(self, trusted_profile_id: str) -> TrustedProfile: ...

    def get_or_create_template_artifact(self, template_artifact: TemplateArtifact) -> TemplateArtifact: ...

    def get_template_artifact(self, template_artifact_id: str) -> TemplateArtifact: ...

    def get_or_create_trusted_profile_version(
        self,
        trusted_profile_version: TrustedProfileVersion,
    ) -> TrustedProfileVersion: ...

    def get_trusted_profile_version_for_organization(
        self,
        *,
        organization_id: str,
        trusted_profile_version_id: str,
    ) -> TrustedProfileVersion: ...

    def list_trusted_profile_versions(self, trusted_profile_id: str) -> list[TrustedProfileVersion]: ...

    def get_next_trusted_profile_version_number(self, trusted_profile_id: str) -> int: ...

    def get_or_create_profile_snapshot(self, profile_snapshot: ProfileSnapshot) -> ProfileSnapshot: ...

    def get_profile_snapshot_for_organization(
        self,
        *,
        organization_id: str,
        profile_snapshot_id: str,
    ) -> ProfileSnapshot: ...

    def get_open_trusted_profile_draft_for_organization(
        self,
        *,
        organization_id: str,
        trusted_profile_id: str,
    ) -> TrustedProfileDraft: ...

    def get_trusted_profile_draft_for_organization(
        self,
        *,
        organization_id: str,
        trusted_profile_draft_id: str,
    ) -> TrustedProfileDraft: ...

    def get_or_create_trusted_profile_draft(
        self,
        trusted_profile_draft: TrustedProfileDraft,
    ) -> TrustedProfileDraft: ...

    def save_trusted_profile_draft(
        self,
        trusted_profile_draft: TrustedProfileDraft,
        *,
        expected_draft_revision: int,
    ) -> TrustedProfileDraft: ...

    def delete_trusted_profile_draft(self, trusted_profile_draft_id: str) -> None: ...

    def publish_trusted_profile_draft(
        self,
        *,
        organization_id: str,
        trusted_profile_draft_id: str,
        expected_draft_revision: int,
        canonical_bundle_json: str,
        content_hash: str,
        template_artifact_id: str | None,
        template_artifact_ref: str | None,
        template_file_hash: str | None,
        created_by_user_id: str | None,
        created_at,
    ) -> TrustedProfileVersion: ...

    def upsert_trusted_profile_observation(
        self,
        observation: TrustedProfileObservation,
    ) -> TrustedProfileObservation: ...

    def get_trusted_profile_observation(
        self,
        *,
        trusted_profile_id: str,
        observation_domain: str,
        canonical_raw_key: str,
    ) -> TrustedProfileObservation | None: ...

    def list_trusted_profile_observations(
        self,
        trusted_profile_id: str,
        *,
        observation_domain: str | None = None,
        unresolved_only: bool = False,
        unmerged_only: bool = False,
    ) -> list[TrustedProfileObservation]: ...

    def get_or_create_source_document(self, source_document: SourceDocument) -> SourceDocument: ...

    def get_source_document_for_organization(
        self,
        *,
        organization_id: str,
        source_document_id: str,
    ) -> SourceDocument: ...

    def create_processing_run(self, processing_run: ProcessingRun) -> ProcessingRun: ...

    def create_run_records(self, run_records: list[RunRecord]) -> list[RunRecord]: ...

    def get_processing_run_for_organization(
        self,
        *,
        organization_id: str,
        processing_run_id: str,
    ) -> ProcessingRun: ...

    def list_run_records_for_processing_run(
        self,
        *,
        organization_id: str,
        processing_run_id: str,
    ) -> list[RunRecord]: ...

    def get_or_create_review_session(self, review_session: ReviewSession) -> ReviewSession: ...

    def get_review_session_for_run_for_organization(
        self,
        *,
        organization_id: str,
        processing_run_id: str,
    ) -> ReviewSession: ...

    def save_review_session_edits(
        self,
        review_session: ReviewSession,
        reviewed_record_edits: list[ReviewedRecordEdit],
        *,
        expected_current_revision: int,
    ) -> None: ...

    def list_reviewed_record_edits_for_review_session(
        self,
        *,
        organization_id: str,
        review_session_id: str,
        up_to_revision: int | None = None,
    ) -> list[ReviewedRecordEdit]: ...

    def create_export_artifact(self, export_artifact: ExportArtifact) -> ExportArtifact: ...

    def get_export_artifact_for_organization(
        self,
        *,
        organization_id: str,
        export_artifact_id: str,
    ) -> ExportArtifact: ...
