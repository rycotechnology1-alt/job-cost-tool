# Phase 7 Cleanup And Hardening Design

Date: 2026-04-18

## Goal

Complete the SQLite-to-Postgres transition by hardening transactional behavior, adding explicit optimistic concurrency for hosted profile authoring, and deleting transitional scaffolding that no longer serves the final architecture.

This phase is not a new feature slice. It is the pass that makes the current architecture safer, more deterministic, and easier to understand.

## Scope

This phase covers:

- trusted-profile draft mutation and publish transaction safety
- review-session revision advancement safety
- export lineage persistence hardening
- removal of dead transitional helpers and duplicate hosted paths
- runtime composition cleanup and naming cleanup
- regression tests and tracker/docs updates for the final post-transition shape

This phase does not cover:

- new auth-product behavior
- new tenant features beyond the already-established organization boundary
- parser/review/export pipeline redesign
- removal of intentionally retained desktop/local compatibility support

## Problems To Fix

### 1. Draft authoring is missing explicit concurrency control

Hosted draft updates currently behave like mutable overwrites. Two operators can read the same draft state and the later writer can silently replace the earlier one. Publish has the same weakness because it does not currently prove that the caller is publishing the latest draft revision.

### 2. Publish is logically one operation but is persisted as several steps

Publishing a draft currently spans:

- reading the draft
- finding or creating an equivalent immutable version
- updating the trusted profile's current published pointer
- deleting the draft

Those steps should succeed or fail as one database transaction.

### 3. Review edit persistence must fail closed on stale revision state

Review-session edits are append-only and revisioned, but the persistence contract should explicitly protect against concurrent writes that would incorrectly advance the same prior revision twice.

### 4. Export persistence still spans storage and lineage in a way that can leave orphaned artifacts

Artifact bytes are stored first and the export lineage row is recorded afterward. If lineage persistence fails after storage succeeds, the current flow can leave behind stored artifacts with no lineage row.

### 5. Transitional seams and compatibility helpers are still mixed into the final architecture

The repository and store layers still contain compatibility-era methods and naming that were useful during migration but now make the code harder to read and reason about.

## Recommended Approach

Use strict fail-fast optimistic concurrency for every hosted draft mutation and publish operation, keep the authoritative transaction boundaries in the persistence layer, and remove compatibility helpers that hosted flows no longer use.

This keeps the rules explicit:

- stale draft mutation fails with conflict
- stale draft publish fails with conflict
- review revision advancement fails with conflict when the expected prior revision no longer matches
- version creation, current-version pointer update, and draft deletion either all commit or all roll back

## Alternatives Considered

### A. Publish-only concurrency guards

This would reduce implementation work, but it still permits silent last-write-wins during draft editing. It protects the final commit but not the authoring workflow.

### B. Last-write-wins draft editing with timestamps

This is smaller mechanically but weaker semantically. It hides conflicts instead of surfacing them and makes hosted collaboration less trustworthy.

### C. Service-layer transaction orchestration

This would keep more logic outside persistence, but it spreads transaction knowledge across services and duplicates behavior between SQLite and Postgres implementations. The cleaner final shape is for the store layer to own the transaction boundary.

## Final Design

## Concurrency Model

Add an explicit persisted `draft_revision` integer to `TrustedProfileDraft`.

Rules:

- a newly created draft starts at revision `1`
- every successful draft mutation increments `draft_revision`
- every hosted draft mutation requires the caller to provide `expected_draft_revision`
- publish also requires `expected_draft_revision`
- if the stored draft revision does not match the expected revision, persistence raises a conflict error

The API and service contract should present this as a fail-fast `409` conflict, not a merge attempt.

Desktop/local compatibility can still use the same mechanisms, but hosted APIs must not have a silent fallback path.

## Trusted Profile Publish Transaction

Replace the current multi-step publish path with one explicit transactional repository/store operation.

The transactional publish operation must:

1. load the target draft scoped to organization
2. assert the expected draft revision still matches
3. compute the deterministic content hash and canonical bundle payload
4. reuse an existing equivalent published version if one already exists, or insert a new immutable version if it does not
5. update the trusted profile's `current_published_version_id`
6. delete the open draft row
7. commit once

If any step fails, the store must roll the whole publish operation back.

Observation-resolution updates can remain outside the database transaction because they are derived follow-up state and not part of the core publish identity boundary. They should remain idempotent and safe to retry.

## Draft Mutation Persistence

Replace unconditional draft-save behavior with compare-and-swap semantics.

Each mutation method should:

1. load the draft
2. validate or transform the requested bundle changes in service code
3. call a repository/store save method that requires `expected_draft_revision`
4. update `bundle_json`, `content_hash`, `updated_at`, and increment `draft_revision`

Stale writes must raise a conflict and must not partially update the draft.

## Review Session Revision Hardening

Keep review edits append-only.

Tighten persistence so `save_review_session_edits` becomes an expected-revision compare-and-swap operation:

- the stored review session must still be at the expected prior revision
- the new review session revision and appended edit rows are written atomically
- concurrent stale writers fail with conflict instead of double-advancing

This keeps exact revision lineage deterministic under concurrent hosted access.

## Export Lineage Hardening

Keep the current explicit separation between runtime artifact storage and lineage persistence, but make failure behavior cleaner.

Hosted export creation should follow this order:

1. build export bytes
2. persist artifact bytes through runtime storage
3. persist the export lineage row in one store operation
4. if lineage persistence fails after artifact storage succeeds, perform best-effort artifact cleanup and surface failure

This avoids claiming success when exact lineage is not recorded and reduces orphaned hosted artifacts.

The same cleanup rule applies to trusted-profile sync exports.

## Persistence Layer Changes

Add the following persistence capabilities and constraints:

- `draft_revision` column for trusted-profile drafts in SQLite and Postgres
- store methods for optimistic draft save and transactional publish
- store methods for compare-and-swap review revision advancement
- explicit conflict exceptions from persistence for stale draft/review writes

Keep `LineageStore` focused on real hosted-service needs. Do not re-expand it with compatibility wrappers that duplicate existing transactional methods.

## Service Layer Changes

`ProfileAuthoringService`:

- require `expected_draft_revision` for hosted draft mutations and publish
- stop treating publish as several repository calls
- use explicit conflict handling for stale writes

`ReviewSessionService`:

- supply expected current revision when persisting appended review edits
- preserve append-only semantics and exact revision lineage

`TrustedProfileAuthoringRepository`:

- narrow further toward authoring persistence concerns
- own deterministic bundle serialization and call the new transactional store methods
- delete compatibility-era helpers that only preserve old call shapes

## API Contract Changes

Hosted draft mutation and publish requests should include the current `draft_revision`.

Responses that return draft state should include the current `draft_revision`.

Conflict behavior:

- stale draft mutation returns `409`
- stale draft publish returns `409`
- stale review append returns `409`

The API should not leak implementation detail beyond a clear conflict message.

## Cleanup Targets

Remove or reduce:

- duplicate raw-id or compatibility helpers in concrete stores that hosted code no longer uses
- obsolete repository methods whose only purpose was preserving pre-transaction publish flow
- transitional naming that still reads like a migration waypoint rather than the final architecture

Retain intentionally:

- `ProfileExecutionCompatibilityAdapter` as the explicit legacy execution bridge until parser/review/export can consume persisted bundles directly
- local runtime file storage for desktop/dev/local compatibility mode
- local request-context compatibility mode for intentional non-hosted usage

## Error Handling

Introduce one explicit persistence conflict error type and map it to HTTP `409`.

Use it for:

- stale draft update
- stale draft publish
- stale review revision advancement

Do not overload `ValueError` for concurrency conflicts.

## Tests

Add or update regression coverage for:

- draft mutation conflict on stale revision
- publish conflict on stale revision
- publish atomicity for version creation, current-version pointer update, and draft deletion
- review revision conflict on stale current revision
- export lineage failure cleanup behavior
- both SQLite and Postgres persistence behavior for the hardened paths

Keep existing desktop/local compatibility tests green.

## Documentation

Update:

- live transition tracker with the final post-transition architecture state
- env/runtime docs only if naming or runtime-selection behavior changes

The tracker should call out remaining intentionally retained compatibility seams rather than leaving them implicit.

## Remaining Debt After This Phase

Two compatibility seams are expected to remain intentionally:

1. `ProfileExecutionCompatibilityAdapter`
   This remains the explicit bridge to temp config directories for legacy parser/review/export execution.

2. Local runtime file storage for desktop/dev/local mode
   This remains intentionally because desktop is still an in-scope fallback shell.

Everything else should move toward one clear hosted path and one clear local compatibility path.

## Success Criteria

Phase 7 is complete when:

- hosted draft mutation and publish fail fast on stale revisions
- publish is atomic across version creation/reuse, pointer advance, and draft deletion
- review revision advancement is atomic and conflict-safe
- export lineage failure does not leave the API in a false-success state
- dead compatibility helpers are removed rather than preserved indefinitely
- the codebase reads like a settled architecture instead of a migration midpoint
