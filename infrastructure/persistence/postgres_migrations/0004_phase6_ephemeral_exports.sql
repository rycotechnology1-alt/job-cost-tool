CREATE TABLE IF NOT EXISTS retained_export_artifacts (
    export_artifact_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations (organization_id),
    session_revision INTEGER NOT NULL CHECK (session_revision >= 0),
    artifact_kind TEXT NOT NULL,
    storage_ref TEXT NOT NULL,
    file_hash TEXT,
    created_by_user_id TEXT REFERENCES users (user_id),
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_retained_export_artifacts_expires_at
ON retained_export_artifacts (expires_at, created_at);
