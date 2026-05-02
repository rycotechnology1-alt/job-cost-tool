CREATE TABLE IF NOT EXISTS processing_run_input_snapshots (
    input_snapshot_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations (organization_id),
    processing_run_id TEXT NOT NULL REFERENCES processing_runs (processing_run_id),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    payload_json_gzip BYTEA NOT NULL,
    payload_hash TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    created_at TEXT NOT NULL,
    UNIQUE (processing_run_id)
);

CREATE INDEX IF NOT EXISTS ix_processing_run_input_snapshots_run
ON processing_run_input_snapshots (processing_run_id);
