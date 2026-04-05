# Revised Web Migration Plan

## Summary

- Migrate with a strangler approach: keep `core/` as the product engine, extract non-Qt application services, add a web shell, and keep the desktop app alive until web parity is accepted.

- Phase 1 targets one deployed customer / one organization, not full multi-tenant SaaS. The code should stay organization-ready by keeping org-scoped boundaries on top-level persisted entities, but phase 1 should not include true multi-tenant provisioning, billing, or org-management complexity.

- Phase 1 parity means the web workflow must produce the same usable business result as desktop for the same input report and trusted profile. At minimum that means the same surviving review records, the same normalized family/type outcomes, the same blockers/warnings, the same correction results, and materially the same export workbook output.

- Full browser-native profile/admin parity is deferred unless a narrow subset is required for go-live. Web v1 must use trusted profiles correctly, and labor/equipment classification behavior is mandatory in v1.

## Phase 1 Build Sequence

1\. Extract plain Python application services from `ReviewViewModel` and `SettingsViewModel`, keeping workflow orchestration and business-state shaping out of Qt.

2\. Define the immutable run/session/export lineage model and persistence schema before building APIs.

3\. Implement trusted-profile import/selection plus effective `ProfileSnapshot` resolution.

4\. Implement processing-run creation, immutable run-record persistence, and deterministic `record_key` assignment.

5\. Implement review-session overlay editing, `session_revision` progression, and export generation from a specific revision.

6\. Add the HTTP API around those services and lineage rules.

7\. Build the minimal browser workflow for upload, process, review/correct, blocker inspection, and export.

8\. Build the parity acceptance harness and run it against the desktop corpus before any cutover decision.

9\. Pilot the web flow while desktop remains the fallback; only expand profile/admin features after workflow parity is accepted.

## Key Changes

- Preserve `core/` as the shared engine for parsing, normalization, validation, config interpretation, recap payload building, and workbook export.

- Extract non-Qt application services before rebuilding UI. Pull out workflow orchestration, correction application, validation/blocker state changes, export readiness rules, profile resolution, option loading, and issue/blocker shaping. Leave Qt signals, widget refreshes, row coloring, dialogs, and screen-management behavior in desktop UI glue.

- Add a Python web backend, defaulting to FastAPI plus PostgreSQL, with authenticated single-organization deployment in phase 1.

- Add a browser UI, defaulting to React + TypeScript, that mirrors the current workflow: upload report, process, review/correct, inspect blockers/issues, and export workbook.

- Keep workbook export in web v1 and reuse the existing exporter logic rather than redesigning output behavior.

- Start with synchronous or lightly asynchronous request handling. Do not introduce a background worker queue by default. Add workers only if staging measurements show parse/normalize/validate or export exceeds a P95 of 10 seconds or a max of 20 seconds on the acceptance corpus under 3 concurrent users, or if retries/cancellation/progress persistence become necessary due to request instability or timeouts.

- Keep desktop coexistence operationally: the desktop app remains the production fallback until the parity corpus passes and web is accepted.

## Phase 1 Persistence, Lineage, and Interfaces

- Enforce immutability before database work:

  - Once a report is processed, that `ProcessingRun` is a fixed snapshot.

  - Reprocessing with new logic or new settings creates a new `ProcessingRun`.

  - A `ReviewSession` belongs to one specific `ProcessingRun`.

  - Edits are stored as overlays/deltas, never as destructive overwrites of run records.

  - Every run captures the exact profile/config snapshot and engine build/version used at process time.

  - Later profile/config changes do not affect old runs, review sessions, exports, or prior results.

  - Rerunning with new settings creates a new run whose export reflects the new settings.

- Use this phase-1 persistence model:

  - `Organization`: single seeded org in v1; retained to keep boundaries organization-ready.

  - `User`: authenticated user within that org.

  - `TrustedProfile`: imported/seeded profile representing the approved business bundle for processing/export.

  - `ProfileSnapshot`: immutable serialized effective bundle for a run, including only what is required for reproducibility and traceability. Capture the effective processing/export inputs that materially affect outcomes, such as profile identity/version, effective JSON config payloads, slot definitions, rates, review rules, recap template map, template workbook hash/reference, and any engine/config version markers used to explain the result later. Do not capture transient UI state, caches, or incidental admin metadata that does not affect processing/export behavior.

  - `SourceDocument`: uploaded input PDF plus file hash and storage reference.

  - `ProcessingRun`: immutable result of processing one `SourceDocument` against one `ProfileSnapshot`; stores status, engine version, created time, and aggregate blockers.

  - `RunRecord`: immutable ordered canonical record rows for that run.

  - `ReviewSession`: one primary review session per processing run in phase 1.

  - `ReviewedRecordEdit`: append-only delta events keyed by `review_session_id`, `record_key`, and `session_revision`, storing only changed fields.

  - `ExportArtifact`: workbook generated from one review session at one specific session revision; references the originating run and revision lineage.

- `record_key` rules:

  - `record_key` is stable only within a single `ProcessingRun`.

  - It should be derived from the immutable emitted review dataset order for that run, not from UI selection state or database row ids.

  - Its purpose is to anchor overlay edits, API addressing, scripted parity comparisons, and export-from-session behavior against one fixed run snapshot.

  - There is no cross-run identity guarantee; reprocessing creates a new run with a new immutable record set and new run-scoped keys.

- `ReviewSession` lifecycle and `session_revision`:

  - A review session starts from one fixed processing run at revision `0`, representing the base run with no user edits applied.

  - Each accepted edit batch appends delta rows and increments `session_revision`.

  - Reopening the session resumes the latest revision for that same run; it does not mutate the underlying run records.

  - Exports must always reference the exact `session_revision` they were generated from.

  - Reprocessing never rebinds an existing review session; it creates a new run and therefore a new session lineage.

- Snapshot mechanism:

  - Resolve the selected trusted profile to one effective bundle at process start.

  - Canonicalize the bundle, compute a content hash, and create or reuse an immutable `ProfileSnapshot`.

  - Persist the template workbook as an artifact reference or stable file hash within the snapshot so later template edits cannot change old exports.

  - Every `ProcessingRun` points to one `ProfileSnapshot`; all review sessions and exports inherit lineage from that run.

- Mandatory web v1 profile behavior:

  - Correctly process and export with trusted profiles.

  - Preserve labor/equipment slot, classification, rate, recap-map, review-rule, and template behavior from those profiles.

  - Support controlled import of existing profile bundles into the web system and controlled export/backup of trusted bundles.

  - Support profile selection and read-only inspection in the web app.

- Deferred profile behavior:

  - Browser-native editing, duplication, wizard-based creation, mapping/rate/template editors, and broader admin parity, unless a small subset is explicitly needed for go-live.

- Phase-1 API surface should center on immutable runs and overlay edits:

  - Upload source document.

  - Start processing run for a chosen trusted profile.

  - Fetch immutable run records and aggregate blockers.

  - Open/fetch the run's review session.

  - Append review edit deltas by `record_key`.

  - Request export for a specific review-session revision.

  - Download an export artifact.

## Parity Harness and Acceptance

- Build a parity acceptance corpus from sample input reports, trusted profiles, scripted review edits, and expected export examples. This corpus becomes the signoff gate for migration.

- Compare desktop and web outputs at semantic, not UI, level:

  - Surviving records: exact same ordered review dataset after parse, normalize, and default review rules, compared on raw/canonical fields such as source page, source line text, phase fields, transaction type, raw description, parsed numeric fields, parsed identity fields, and emitted order.

  - Normalized outcomes: exact equality for `record_type_normalized`, normalized labor/equipment/vendor outputs, slot ids, omission state, and any other export-relevant normalized fields.

  - Blockers/warnings: exact equality of per-record warnings and aggregate blocking issues after whitespace normalization.

  - Correction behavior: the same scripted edit deltas applied to the same `record_key`s must produce the same corrected fields, the same remaining blockers/warnings, and the same export-readiness result.

  - Export workbook: compare a semantic workbook snapshot, not raw XLSX bytes. At minimum compare all mapped writable cells from the recap template map, fixed row labels, section rows within configured bounds, sales-tax cells, summary cells, and style ids for cells the exporter intentionally writes or style-copies.

- Acceptable differences:

  - Generated ids, timestamps, storage keys, ZIP/container metadata, workbook internal ordering, and formula cached values.

- Failing differences:

  - Any mismatch in emitted record count/order, canonical record fields, normalized business fields, warning/blocker text, correction results, or exporter-written cell/formula/style outcomes.

- Rollback and fallback rule:

  - If the web path fails parity on any acceptance-corpus case, desktop remains the production system of record for that scenario.

  - No default cutover occurs until the corpus passes.

  - If needed, web can remain pilot-only for passing scenarios while failing profiles/report families stay on desktop.

## Test Plan

- Keep the existing engine regression suites as the shared safety net for parser, normalization, validation, config, and export behavior.

- Add non-Qt application-service tests that prove extracted workflow services behave the same as current desktop view-model behavior.

- Add persistence tests for run immutability, profile snapshot lineage, delta edit application, export lineage, session revisioning, and "new run on reprocess" behavior.

- Add API tests for upload, run creation, session retrieval, edit application, export creation, and artifact download.

- Add the parity harness to CI using the acceptance corpus and semantic workbook diffing.

- Add performance checks against the acceptance corpus on staging hardware; use those results to decide whether workers remain deferred or become required.

## Assumptions and Defaults

- Default stack: FastAPI backend, React/TypeScript frontend, PostgreSQL persistence, and a storage abstraction that can use local disk in development and production-grade artifact storage in deployment.

- Phase 1 is authenticated and single-organization.

- One primary review session per processing run is sufficient for v1; collaborative multi-user review is deferred.

- Desktop stays operational until workflow parity, not full admin parity, is accepted.

- Profile/admin expansion happens only after the web workflow proves the same business result as desktop.