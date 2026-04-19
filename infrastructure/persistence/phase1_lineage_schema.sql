PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS organizations (
    organization_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    default_trusted_profile_id TEXT,
    is_seeded INTEGER NOT NULL DEFAULT 0 CHECK (is_seeded IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    auth_subject TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, email),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id)
);

CREATE TABLE IF NOT EXISTS trusted_profiles (
    trusted_profile_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    bundle_ref TEXT,
    description TEXT NOT NULL DEFAULT '',
    version_label TEXT,
    current_published_version_id TEXT,
    archived_at TEXT,
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, profile_name),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id),
    FOREIGN KEY (current_published_version_id) REFERENCES trusted_profile_versions (trusted_profile_version_id)
);

CREATE TABLE IF NOT EXISTS trusted_profile_versions (
    trusted_profile_version_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    trusted_profile_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    base_trusted_profile_version_id TEXT,
    bundle_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    template_artifact_id TEXT,
    template_artifact_ref TEXT,
    template_file_hash TEXT,
    source_kind TEXT NOT NULL DEFAULT 'published',
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (trusted_profile_id, version_number),
    UNIQUE (organization_id, trusted_profile_id, content_hash),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (trusted_profile_id) REFERENCES trusted_profiles (trusted_profile_id),
    FOREIGN KEY (base_trusted_profile_version_id) REFERENCES trusted_profile_versions (trusted_profile_version_id),
    FOREIGN KEY (template_artifact_id) REFERENCES template_artifacts (template_artifact_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS trusted_profile_drafts (
    trusted_profile_draft_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    trusted_profile_id TEXT NOT NULL,
    draft_revision INTEGER NOT NULL DEFAULT 1 CHECK (draft_revision > 0),
    base_trusted_profile_version_id TEXT,
    bundle_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    template_artifact_id TEXT,
    template_artifact_ref TEXT,
    template_file_hash TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status = 'open'),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (trusted_profile_id),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (trusted_profile_id) REFERENCES trusted_profiles (trusted_profile_id),
    FOREIGN KEY (base_trusted_profile_version_id) REFERENCES trusted_profile_versions (trusted_profile_version_id),
    FOREIGN KEY (template_artifact_id) REFERENCES template_artifacts (template_artifact_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS trusted_profile_observations (
    trusted_profile_observation_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    trusted_profile_id TEXT NOT NULL,
    observation_domain TEXT NOT NULL CHECK (observation_domain IN ('labor_mapping', 'equipment_mapping')),
    canonical_raw_key TEXT NOT NULL,
    raw_display_value TEXT NOT NULL,
    first_seen_processing_run_id TEXT,
    last_seen_processing_run_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    draft_applied_at TEXT,
    is_resolved INTEGER NOT NULL DEFAULT 0 CHECK (is_resolved IN (0, 1)),
    resolved_at TEXT,
    UNIQUE (trusted_profile_id, observation_domain, canonical_raw_key),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (trusted_profile_id) REFERENCES trusted_profiles (trusted_profile_id),
    FOREIGN KEY (first_seen_processing_run_id) REFERENCES processing_runs (processing_run_id),
    FOREIGN KEY (last_seen_processing_run_id) REFERENCES processing_runs (processing_run_id)
);

CREATE TABLE IF NOT EXISTS template_artifacts (
    template_artifact_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    content_bytes BLOB NOT NULL,
    file_size_bytes INTEGER,
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, content_hash),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    profile_snapshot_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    trusted_profile_id TEXT,
    trusted_profile_version_id TEXT,
    template_artifact_id TEXT,
    content_hash TEXT NOT NULL,
    bundle_json TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    template_artifact_ref TEXT,
    template_file_hash TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, content_hash),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (trusted_profile_id) REFERENCES trusted_profiles (trusted_profile_id),
    FOREIGN KEY (trusted_profile_version_id) REFERENCES trusted_profile_versions (trusted_profile_version_id),
    FOREIGN KEY (template_artifact_id) REFERENCES template_artifacts (template_artifact_id)
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_document_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    storage_ref TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size_bytes INTEGER,
    uploaded_by_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, file_hash, storage_ref),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (uploaded_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS processing_runs (
    processing_run_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    profile_snapshot_id TEXT NOT NULL,
    trusted_profile_id TEXT,
    trusted_profile_version_id TEXT,
    status TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    aggregate_blockers_json TEXT NOT NULL DEFAULT '[]',
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (source_document_id) REFERENCES source_documents (source_document_id),
    FOREIGN KEY (profile_snapshot_id) REFERENCES profile_snapshots (profile_snapshot_id),
    FOREIGN KEY (trusted_profile_id) REFERENCES trusted_profiles (trusted_profile_id),
    FOREIGN KEY (trusted_profile_version_id) REFERENCES trusted_profile_versions (trusted_profile_version_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS run_records (
    run_record_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    processing_run_id TEXT NOT NULL,
    record_key TEXT NOT NULL,
    record_index INTEGER NOT NULL CHECK (record_index >= 0),
    canonical_record_json TEXT NOT NULL,
    source_page INTEGER,
    source_line_text TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (processing_run_id, record_key),
    UNIQUE (processing_run_id, record_index),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (processing_run_id) REFERENCES processing_runs (processing_run_id)
);

CREATE TABLE IF NOT EXISTS review_sessions (
    review_session_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    processing_run_id TEXT NOT NULL,
    current_revision INTEGER NOT NULL DEFAULT 0 CHECK (current_revision >= 0),
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (processing_run_id),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (processing_run_id) REFERENCES processing_runs (processing_run_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS reviewed_record_edits (
    reviewed_record_edit_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    processing_run_id TEXT NOT NULL,
    review_session_id TEXT NOT NULL,
    record_key TEXT NOT NULL,
    session_revision INTEGER NOT NULL CHECK (session_revision > 0),
    changed_fields_json TEXT NOT NULL,
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (review_session_id, record_key, session_revision),
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (processing_run_id) REFERENCES processing_runs (processing_run_id),
    FOREIGN KEY (review_session_id) REFERENCES review_sessions (review_session_id),
    FOREIGN KEY (processing_run_id, record_key) REFERENCES run_records (processing_run_id, record_key),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS export_artifacts (
    export_artifact_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    processing_run_id TEXT NOT NULL,
    review_session_id TEXT NOT NULL,
    session_revision INTEGER NOT NULL CHECK (session_revision >= 0),
    artifact_kind TEXT NOT NULL,
    storage_ref TEXT NOT NULL,
    template_artifact_id TEXT,
    file_hash TEXT,
    created_by_user_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id) REFERENCES organizations (organization_id),
    FOREIGN KEY (processing_run_id) REFERENCES processing_runs (processing_run_id),
    FOREIGN KEY (review_session_id) REFERENCES review_sessions (review_session_id),
    FOREIGN KEY (template_artifact_id) REFERENCES template_artifacts (template_artifact_id),
    FOREIGN KEY (created_by_user_id) REFERENCES users (user_id)
);

CREATE INDEX IF NOT EXISTS ix_trusted_profiles_org ON trusted_profiles (organization_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_subject ON users (auth_subject) WHERE auth_subject IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_trusted_profile_versions_profile_version ON trusted_profile_versions (trusted_profile_id, version_number);
CREATE INDEX IF NOT EXISTS ix_trusted_profile_versions_org_profile ON trusted_profile_versions (organization_id, trusted_profile_id);
CREATE INDEX IF NOT EXISTS ix_trusted_profile_drafts_profile ON trusted_profile_drafts (trusted_profile_id);
CREATE INDEX IF NOT EXISTS ix_trusted_profile_observations_profile_domain ON trusted_profile_observations (trusted_profile_id, observation_domain);
CREATE INDEX IF NOT EXISTS ix_template_artifacts_org ON template_artifacts (organization_id);
CREATE INDEX IF NOT EXISTS ix_profile_snapshots_org ON profile_snapshots (organization_id);
CREATE INDEX IF NOT EXISTS ix_source_documents_org ON source_documents (organization_id);
CREATE INDEX IF NOT EXISTS ix_processing_runs_org_created_at ON processing_runs (organization_id, created_at);
CREATE INDEX IF NOT EXISTS ix_run_records_run ON run_records (processing_run_id, record_index);
CREATE INDEX IF NOT EXISTS ix_reviewed_record_edits_session_revision ON reviewed_record_edits (review_session_id, session_revision);
CREATE INDEX IF NOT EXISTS ix_export_artifacts_session_revision ON export_artifacts (review_session_id, session_revision);
