# Phase 7 Cleanup And Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden draft/review/export transaction behavior, add strict fail-fast optimistic concurrency for hosted authoring, and remove obsolete transition scaffolding so the Postgres migration lands in a clean final architecture.

**Architecture:** Keep transaction and compare-and-swap logic in persistence, not in route glue. Add one explicit persistence conflict type, push draft and review revision guards down into SQLite/Postgres store methods, and shrink the repository/service surface so publish and review flows read as single authoritative paths instead of migration-era compositions.

**Tech Stack:** Python, FastAPI, SQLite, Postgres via psycopg, Vercel Blob runtime storage, pytest, unittest

---

## File Structure Map

### Core persistence and models

- Modify: `core/models/lineage.py`
  - Add `draft_revision` to `TrustedProfileDraft`.
- Modify: `infrastructure/persistence/lineage_store.py`
  - Add the minimal conflict-safe draft/review persistence methods needed by hosted services.
- Modify: `infrastructure/persistence/sqlite_lineage_store.py`
  - Add SQLite compare-and-swap draft saves, transactional publish, compare-and-swap review revision writes, and export-row cleanup helpers.
- Modify: `infrastructure/persistence/postgres_lineage_store.py`
  - Mirror the same behavior in Postgres using explicit transactions.
- Modify: `infrastructure/persistence/phase1_lineage_schema.sql`
  - Add the SQLite `draft_revision` column.
- Modify: `infrastructure/persistence/postgres_migrations/0002_phase5_hosted_auth.sql`
  - Add the Postgres `draft_revision` column with a safe default.

### Service and repository layer

- Modify: `services/trusted_profile_authoring_repository.py`
  - Collapse publish into one repository/store transaction call and add expected-revision draft save behavior.
- Modify: `services/profile_authoring_service.py`
  - Require expected draft revision on every mutation and publish; handle conflict errors explicitly.
- Modify: `services/review_session_service.py`
  - Pass expected current revision when appending edits; clean up export artifacts on lineage persistence failure.
- Modify: `services/profile_authoring_errors.py`
  - Add an explicit optimistic concurrency conflict type if no existing shared error type fits.

### API layer

- Modify: `api/schemas/profile_authoring.py`
  - Add `draft_revision` to draft responses and `expected_draft_revision` to draft mutation/publish requests.
- Modify: `api/schemas/review_sessions.py`
  - Add `expected_current_revision` to append-edit requests.
- Modify: `api/routes/profiles.py`
  - Thread expected draft revision into service calls.
- Modify: `api/routes/review_sessions.py`
  - Thread expected current revision into review append calls.
- Modify: `api/serializers.py`
  - Serialize the draft revision in draft responses.
- Modify: `api/errors.py`
  - Map concurrency conflicts to HTTP `409`.

### Tests and docs

- Modify: `tests/profile_authoring_service_tests.py`
  - Add stale draft mutation/publish conflict coverage and publish atomicity coverage.
- Modify: `tests/review_session_service_tests.py`
  - Add stale review revision conflict coverage and export cleanup coverage.
- Modify: `tests/api_tests.py`
  - Add hosted API conflict tests for stale draft saves/publish and stale review append.
- Modify: `tests/postgres_lineage_store_tests.py`
  - Add Postgres transaction/concurrency coverage.
- Modify: `tests/trusted_profile_authoring_repository_tests.py`
  - Add repository-level publish transaction tests.
- Modify: current-state repo guidance docs
  - Record the final hardened architecture and remaining intentional seams where the repo now keeps current guidance.

## Task 1: Add Persistence Conflict Primitives And Draft Revision Schema

**Files:**
- Modify: `core/models/lineage.py`
- Modify: `services/profile_authoring_errors.py`
- Modify: `infrastructure/persistence/lineage_store.py`
- Modify: `infrastructure/persistence/phase1_lineage_schema.sql`
- Modify: `infrastructure/persistence/postgres_migrations/0002_phase5_hosted_auth.sql`
- Test: `tests/postgres_lineage_store_tests.py`

- [ ] **Step 1: Write the failing Postgres migration/schema test**

```python
def test_trusted_profile_draft_defaults_to_revision_one(self) -> None:
    draft = self.lineage_store.get_or_create_trusted_profile_draft(
        TrustedProfileDraft(
            trusted_profile_draft_id="trusted-profile-draft:org-default:default",
            organization_id="org-default",
            trusted_profile_id="trusted-profile:org-default:default",
            base_trusted_profile_version_id="trusted-profile-version:org-default:default:v1",
            bundle_payload={"behavioral_bundle": {}},
            canonical_bundle_json='{"behavioral_bundle":{}}',
            content_hash="draft-hash",
            created_at=self.created_at,
            updated_at=self.created_at,
        )
    )

    assert draft.draft_revision == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/postgres_lineage_store_tests.py -k draft_defaults_to_revision_one -q`

Expected: `FAIL` because `TrustedProfileDraft` does not expose `draft_revision` yet or the stores do not persist it.

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(frozen=True, slots=True)
class TrustedProfileDraft:
    trusted_profile_draft_id: str
    organization_id: str
    trusted_profile_id: str
    bundle_payload: dict[str, Any]
    canonical_bundle_json: str
    content_hash: str
    created_at: datetime
    updated_at: datetime
    draft_revision: int = 1
    base_trusted_profile_version_id: str | None = None
```

```sql
ALTER TABLE trusted_profile_drafts
ADD COLUMN draft_revision INTEGER NOT NULL DEFAULT 1;
```

```python
class PersistenceConflictError(RuntimeError):
    """Raised when optimistic concurrency checks fail in persistence."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/postgres_lineage_store_tests.py -k draft_defaults_to_revision_one -q`

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add core/models/lineage.py services/profile_authoring_errors.py infrastructure/persistence/lineage_store.py infrastructure/persistence/phase1_lineage_schema.sql infrastructure/persistence/postgres_migrations/0002_phase5_hosted_auth.sql tests/postgres_lineage_store_tests.py
git commit -m "feat: add draft revision and persistence conflict primitives"
```

## Task 2: Add Compare-And-Swap Draft Saves For Every Hosted Mutation

**Files:**
- Modify: `infrastructure/persistence/lineage_store.py`
- Modify: `infrastructure/persistence/sqlite_lineage_store.py`
- Modify: `infrastructure/persistence/postgres_lineage_store.py`
- Modify: `services/trusted_profile_authoring_repository.py`
- Modify: `services/profile_authoring_service.py`
- Modify: `api/schemas/profile_authoring.py`
- Modify: `api/routes/profiles.py`
- Modify: `api/serializers.py`
- Test: `tests/profile_authoring_service_tests.py`
- Test: `tests/api_tests.py`

- [ ] **Step 1: Write the failing service test for stale draft mutation**

```python
def test_update_export_settings_rejects_stale_expected_draft_revision(self) -> None:
    trusted_profile_id = "trusted-profile:org-default:default"
    draft_state = self.service.create_or_open_draft(trusted_profile_id)

    self.service.update_export_settings(
        draft_state.trusted_profile_draft_id,
        {"labor_minimum_hours": {"enabled": True, "threshold_hours": "2", "minimum_hours": "4"}},
        expected_draft_revision=draft_state.draft_revision,
    )

    with self.assertRaises(PersistenceConflictError):
        self.service.update_export_settings(
            draft_state.trusted_profile_draft_id,
            {"labor_minimum_hours": {"enabled": False, "threshold_hours": "", "minimum_hours": ""}},
            expected_draft_revision=draft_state.draft_revision,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/profile_authoring_service_tests.py -k stale_expected_draft_revision -q`

Expected: `FAIL` because draft mutations do not accept or enforce expected revision yet.

- [ ] **Step 3: Write the minimal implementation**

```python
class DraftEditorState(ApiModel):
    draft_revision: int
```

```python
class ExpectedDraftRevisionRequest(ApiModel):
    expected_draft_revision: int = Field(ge=1)
```

```python
def save_trusted_profile_draft(
    self,
    draft: TrustedProfileDraft,
    *,
    expected_draft_revision: int,
) -> TrustedProfileDraft: ...
```

```python
cursor = self._connection.execute(
    """
    UPDATE trusted_profile_drafts
    SET bundle_json = ?,
        content_hash = ?,
        updated_at = ?,
        draft_revision = draft_revision + 1
    WHERE trusted_profile_draft_id = ?
      AND draft_revision = ?
    """,
    (..., draft.trusted_profile_draft_id, expected_draft_revision),
)
if cursor.rowcount != 1:
    raise PersistenceConflictError("Trusted profile draft was updated by another request.")
```

```python
def update_export_settings(..., expected_draft_revision: int, ...) -> DraftEditorState:
    updated_draft = self._save_validated_bundle(
        draft,
        bundle,
        expected_draft_revision=expected_draft_revision,
    )
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/profile_authoring_service_tests.py -k stale_expected_draft_revision -q`

Expected: `1 passed`

- [ ] **Step 5: Add and run the failing API conflict test**

```python
def test_profile_draft_patch_returns_conflict_for_stale_revision(self) -> None:
    draft_response = self.client.post("/api/profiles/trusted-profile:org-default:default/draft")
    draft_id = draft_response.json()["trusted_profile_draft_id"]
    current_revision = draft_response.json()["draft_revision"]

    first_response = self.client.patch(
        f"/api/profile-drafts/{draft_id}/export-settings",
        json={
            "expected_draft_revision": current_revision,
            "export_settings": {"labor_minimum_hours": {"enabled": True, "threshold_hours": "2", "minimum_hours": "4"}},
        },
    )
    stale_response = self.client.patch(
        f"/api/profile-drafts/{draft_id}/export-settings",
        json={
            "expected_draft_revision": current_revision,
            "export_settings": {"labor_minimum_hours": {"enabled": False, "threshold_hours": "", "minimum_hours": ""}},
        },
    )

    assert first_response.status_code == 200
    assert stale_response.status_code == 409
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_tests.py -k stale_revision -q`

Expected: first `FAIL`, then `PASS`

- [ ] **Step 6: Commit**

```bash
git add infrastructure/persistence/lineage_store.py infrastructure/persistence/sqlite_lineage_store.py infrastructure/persistence/postgres_lineage_store.py services/trusted_profile_authoring_repository.py services/profile_authoring_service.py api/schemas/profile_authoring.py api/routes/profiles.py api/serializers.py tests/profile_authoring_service_tests.py tests/api_tests.py
git commit -m "feat: add fail-fast draft concurrency checks"
```

## Task 3: Make Draft Publish One Atomic Transaction

**Files:**
- Modify: `infrastructure/persistence/lineage_store.py`
- Modify: `infrastructure/persistence/sqlite_lineage_store.py`
- Modify: `infrastructure/persistence/postgres_lineage_store.py`
- Modify: `services/trusted_profile_authoring_repository.py`
- Modify: `services/profile_authoring_service.py`
- Modify: `api/schemas/profile_authoring.py`
- Modify: `api/routes/profiles.py`
- Test: `tests/trusted_profile_authoring_repository_tests.py`
- Test: `tests/profile_authoring_service_tests.py`

- [ ] **Step 1: Write the failing repository transaction test**

```python
def test_publish_draft_advances_pointer_and_deletes_draft_atomically(self) -> None:
    draft = self.repository.create_open_draft("org-default", "trusted-profile:org-default:default")

    published_version = self.repository.publish_draft(
        "org-default",
        draft.trusted_profile_draft_id,
        expected_draft_revision=draft.draft_revision,
    )

    trusted_profile = self.repository.get_trusted_profile("org-default", draft.trusted_profile_id)
    self.assertEqual(trusted_profile.current_published_version_id, published_version.trusted_profile_version_id)
    with self.assertRaises(KeyError):
        self.repository.get_draft("org-default", draft.trusted_profile_draft_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/trusted_profile_authoring_repository_tests.py -k publishes_pointer_and_deletes -q`

Expected: `FAIL` because publish does not accept expected revision or enforce one transaction.

- [ ] **Step 3: Write the minimal implementation**

```python
def publish_trusted_profile_draft(
    self,
    *,
    organization_id: str,
    trusted_profile_draft_id: str,
    expected_draft_revision: int,
    published_version: TrustedProfileVersion | None,
    trusted_profile_version_id: str,
) -> TrustedProfileVersion: ...
```

```python
with self._connection:
    draft_row = self._connection.execute(...).fetchone()
    if draft_row["draft_revision"] != expected_draft_revision:
        raise PersistenceConflictError("Trusted profile draft was updated by another request.")
    if equivalent_version_row is None:
        self._connection.execute("INSERT INTO trusted_profile_versions ...", (...))
    self._connection.execute(
        "UPDATE trusted_profiles SET current_published_version_id = ? WHERE trusted_profile_id = ?",
        (resolved_version_id, trusted_profile_id),
    )
    self._connection.execute(
        "DELETE FROM trusted_profile_drafts WHERE trusted_profile_draft_id = ?",
        (trusted_profile_draft_id,),
    )
```

```python
published_detail = self.service.publish_draft(
    draft_id,
    expected_draft_revision=current_revision,
)
```

- [ ] **Step 4: Run the repository and service tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/trusted_profile_authoring_repository_tests.py tests/profile_authoring_service_tests.py -k publish -q`

Expected: `PASS` for the new publish atomicity and stale publish conflict tests.

- [ ] **Step 5: Commit**

```bash
git add infrastructure/persistence/lineage_store.py infrastructure/persistence/sqlite_lineage_store.py infrastructure/persistence/postgres_lineage_store.py services/trusted_profile_authoring_repository.py services/profile_authoring_service.py api/schemas/profile_authoring.py api/routes/profiles.py tests/trusted_profile_authoring_repository_tests.py tests/profile_authoring_service_tests.py
git commit -m "feat: make draft publish atomic and conflict-safe"
```

## Task 4: Harden Review Revision Advancement With Compare-And-Swap

**Files:**
- Modify: `infrastructure/persistence/lineage_store.py`
- Modify: `infrastructure/persistence/sqlite_lineage_store.py`
- Modify: `infrastructure/persistence/postgres_lineage_store.py`
- Modify: `services/review_session_service.py`
- Modify: `api/schemas/review_sessions.py`
- Modify: `api/routes/review_sessions.py`
- Test: `tests/review_session_service_tests.py`
- Test: `tests/api_tests.py`

- [ ] **Step 1: Write the failing review service conflict test**

```python
def test_apply_review_edits_rejects_stale_expected_current_revision(self) -> None:
    processing_result = self._create_processing_run()
    processing_run_id = processing_result.processing_run.processing_run_id

    state = self.review_session_service.open_review_session(processing_run_id)
    self.review_session_service.apply_review_edits(
        processing_run_id,
        [PendingRecordEdit(record_key="record-0", changed_fields={"vendor_name_normalized": "Vendor B"})],
        expected_current_revision=state.review_session.current_revision,
    )

    with self.assertRaises(PersistenceConflictError):
        self.review_session_service.apply_review_edits(
            processing_run_id,
            [PendingRecordEdit(record_key="record-0", changed_fields={"vendor_name_normalized": "Vendor C"})],
            expected_current_revision=state.review_session.current_revision,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/review_session_service_tests.py -k stale_expected_current_revision -q`

Expected: `FAIL` because review append currently does not accept an expected revision.

- [ ] **Step 3: Write the minimal implementation**

```python
class AppendReviewEditsRequest(ApiModel):
    expected_current_revision: int = Field(ge=0)
    edits: list[ReviewEditDelta] = Field(min_length=1)
```

```python
def save_review_session_edits(
    self,
    review_session: ReviewSession,
    reviewed_record_edits: list[ReviewedRecordEdit],
    *,
    expected_previous_revision: int,
) -> None: ...
```

```python
cursor = self._connection.execute(
    """
    UPDATE review_sessions
    SET current_revision = ?, updated_at = ?
    WHERE review_session_id = ? AND current_revision = ?
    """,
    (review_session.current_revision, _dt(review_session.updated_at), review_session.review_session_id, expected_previous_revision),
)
if cursor.rowcount != 1:
    raise PersistenceConflictError("Review session was updated by another request.")
```

- [ ] **Step 4: Run the focused review tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/review_session_service_tests.py -k stale_expected_current_revision -q`

Expected: `1 passed`

- [ ] **Step 5: Add and run the API stale review append test**

```python
def test_review_append_returns_conflict_for_stale_expected_current_revision(self) -> None:
    processing_run_id = self._create_processing_run_via_api()
    review_response = self.client.get(f"/api/runs/{processing_run_id}/review-session")
    current_revision = review_response.json()["current_revision"]

    first_response = self.client.post(
        f"/api/runs/{processing_run_id}/review-session/edits",
        json={
            "expected_current_revision": current_revision,
            "edits": [{"record_key": "record-0", "changed_fields": {"vendor_name_normalized": "Vendor B"}}],
        },
    )
    stale_response = self.client.post(
        f"/api/runs/{processing_run_id}/review-session/edits",
        json={
            "expected_current_revision": current_revision,
            "edits": [{"record_key": "record-0", "changed_fields": {"vendor_name_normalized": "Vendor C"}}],
        },
    )

    assert first_response.status_code == 200
    assert stale_response.status_code == 409
```

- [ ] **Step 6: Commit**

```bash
git add infrastructure/persistence/lineage_store.py infrastructure/persistence/sqlite_lineage_store.py infrastructure/persistence/postgres_lineage_store.py services/review_session_service.py api/schemas/review_sessions.py api/routes/review_sessions.py tests/review_session_service_tests.py tests/api_tests.py
git commit -m "feat: add compare-and-swap review revision persistence"
```

## Task 5: Harden Export Lineage Failure Behavior And Remove Obsolete Publish Helpers

**Files:**
- Modify: `services/review_session_service.py`
- Modify: `services/profile_authoring_service.py`
- Modify: `infrastructure/storage/runtime_storage.py`
- Modify: `infrastructure/storage/local_runtime_file_store.py`
- Modify: `infrastructure/storage/vercel_blob_runtime_storage.py`
- Modify: `services/trusted_profile_authoring_repository.py`
- Modify: `api/errors.py`
- Test: `tests/review_session_service_tests.py`
- Test: `tests/profile_authoring_service_tests.py`

- [ ] **Step 1: Write the failing export cleanup test**

```python
def test_export_artifact_is_cleaned_up_when_lineage_persistence_fails(self) -> None:
    processing_result = self._create_processing_run()
    self.review_session_service._artifact_store = LocalRuntimeFileStore(
        upload_root=TEST_ROOT / "runtime" / "uploads",
        export_root=TEST_ROOT / "runtime" / "exports",
    )

    with patch.object(
        self.lineage_store,
        "create_export_artifact",
        side_effect=RuntimeError("lineage write failed"),
    ):
        with self.assertRaises(RuntimeError):
            self.review_session_service.export_session_revision(
                processing_result.processing_run.processing_run_id,
                session_revision=0,
            )

    self.assertEqual(list((TEST_ROOT / "runtime" / "exports").rglob("*.xlsx")), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/review_session_service_tests.py -k cleaned_up_when_lineage_persistence_fails -q`

Expected: `FAIL` because artifact cleanup does not happen yet.

- [ ] **Step 3: Write the minimal implementation**

```python
class RuntimeStorage(Protocol):
    def delete_artifact(self, storage_ref: str) -> None: ...
```

```python
try:
    export_artifact = self._lineage_store.create_export_artifact(...)
except Exception:
    if stored_artifact is not None:
        self._artifact_store.delete_artifact(stored_artifact.storage_ref)
    raise
```

```python
def delete_artifact(self, storage_ref: str) -> None:
    export_dir = self._resolve_storage_ref_dir(...)
    shutil.rmtree(export_dir, ignore_errors=True)
```

```python
def delete_artifact(self, storage_ref: str) -> None:
    self._blob_client.delete_path(normalized_storage_ref)
    self._blob_client.delete_path(self._metadata_path_for_storage_ref(normalized_storage_ref))
    self._delete_cached_path(self._export_root, normalized_storage_ref)
```

- [ ] **Step 4: Remove obsolete repository helpers after export test is green**

```python
# Delete helpers whose only purpose was preserving the old multi-call publish flow:
# - set_current_published_version()
# - get_next_trusted_profile_version_number() from repository surface if the store publish method now owns sequencing
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/review_session_service_tests.py tests/profile_authoring_service_tests.py -k "cleaned_up_when_lineage_persistence_fails or publish" -q`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add services/review_session_service.py services/profile_authoring_service.py infrastructure/storage/runtime_storage.py infrastructure/storage/local_runtime_file_store.py infrastructure/storage/vercel_blob_runtime_storage.py services/trusted_profile_authoring_repository.py api/errors.py tests/review_session_service_tests.py tests/profile_authoring_service_tests.py
git commit -m "refactor: harden export cleanup and remove obsolete publish helpers"
```

## Task 6: Final Cleanup, Docs, And Full Verification

**Files:**
- Modify: `api/dependencies.py`
- Modify: `services/trusted_profile_authoring_repository.py`
- Modify: current-state repo guidance docs when needed
- Modify: `README.md` only if naming/docs are now stale
- Test: `tests/api_tests.py`
- Test: `tests/postgres_lineage_store_tests.py`
- Test: `tests/runtime_storage_tests.py`

- [ ] **Step 1: Write the failing naming/cleanup test where it protects behavior**

```python
def test_draft_state_response_includes_draft_revision(self) -> None:
    response = self.client.post("/api/profiles/trusted-profile:org-default:default/draft")
    assert response.status_code == 201
    assert response.json()["draft_revision"] == 1
```

- [ ] **Step 2: Run test to verify it passes only after the cleanup is actually wired through**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api_tests.py -k draft_state_response_includes_draft_revision -q`

Expected: `PASS`

- [ ] **Step 3: Tighten naming and delete dead hosted paths**

```python
# Examples of acceptable cleanup in this task:
# - rename helper methods so "publish draft" and "append review edits" read as the single authoritative path
# - remove raw concrete-store helpers no longer used anywhere in hosted or local flows
# - trim duplicate comments/docstrings that still describe the repo as a migration midpoint
```

- [ ] **Step 4: Update the current-state docs**

```markdown
Document the final hardened architecture and any intentionally retained compatibility seams in the current repo guidance docs.
```

- [ ] **Step 5: Run the full verification sweep**

Run: `.\.venv\Scripts\python.exe -m pytest tests/processing_run_service_tests.py tests/review_session_service_tests.py tests/profile_authoring_service_tests.py tests/trusted_profile_authoring_repository_tests.py tests/api_tests.py tests/postgres_lineage_store_tests.py tests/sqlite_lineage_store_tests.py tests/runtime_storage_tests.py -q`

Expected: `all targeted suites pass`

- [ ] **Step 6: Commit**

```bash
git add api/dependencies.py services/trusted_profile_authoring_repository.py AGENTS.md README.md tests/api_tests.py tests/postgres_lineage_store_tests.py tests/runtime_storage_tests.py
git commit -m "refactor: finalize post-migration hardening cleanup"
```

## Self-Review

### Spec coverage

- Draft optimistic concurrency: covered by Tasks 1-3.
- Publish transaction boundary: covered by Task 3.
- Review revision hardening: covered by Task 4.
- Export lineage cleanup: covered by Task 5.
- Dead-code cleanup and final architecture tightening: covered by Tasks 5-6.
- Updated tests and docs: covered by Tasks 1-6.

### Placeholder scan

- No `TODO`, `TBD`, or “similar to above” placeholders remain.
- Each task names exact files, commands, and at least one concrete test or implementation snippet.

### Type consistency

- `draft_revision` is the shared draft field name across model, schema, service, and API plan steps.
- `expected_draft_revision` is the shared incoming request argument for draft mutation and publish.
- `expected_current_revision` is the shared incoming request argument for review append.
- `PersistenceConflictError` is the single conflict primitive used across draft and review paths.

