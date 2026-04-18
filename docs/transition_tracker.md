# Transition Tracker

This is the live tracker for the current repo state.

Historical migration notes, retired planning sections, and older long-form change history now live in [docs/transition_tracker_archive.md](docs/transition_tracker_archive.md).

## How To Use This Tracker
- For meaningful work, read `AGENTS.md` plus the previous day's notes here by default.
- Widen to older entries in this file or the archive only when the task depends on older architecture, workflow, or historical product decisions.
- Update this file only for meaningful current-state changes. Keep it short.

## Current Product Status
- The product is now web-first: `api/` + `web/` are the primary delivery path.
- `app/` remains a valuable desktop fallback and reference implementation.
- Shared business behavior still belongs in `core/` and `services/`.
- Web review, export, trusted-profile selection, and core profile-settings authoring already exist and are active product surfaces.

## Current Architecture Snapshot
- `core/`: parsing, normalization, validation, export semantics, models, shared product rules
- `services/`: processing lineage, review workflow, trusted-profile authoring, bundle helpers, orchestration seams
- `api/`: thin HTTP contracts over services
- `web/`: thin browser workflows over the API
- `app/`: desktop fallback/reference shell

## Current Delivery Stance
- Prefer reusable engine/service logic over shell-specific logic.
- Preserve lineage, immutability, and published-version boundaries.
- Keep desktop stable when desktop code is touched.
- Avoid unnecessary platform sprawl unless the task explicitly calls for it.

## Current Known Risks
- Desktop and web behavior can still drift if new logic bypasses shared helpers/services.
- Guidance docs can drift from repo reality if this live tracker is not kept current and concise.
- Profile-management ergonomics can still tempt broader lifecycle/platform work than the product currently needs.
- Runtime storage and deployment assumptions should remain explicit if pilot/production footprint changes.

## Current Priorities
1. Keep web review, export, and profile settings reliable.
2. Preserve lineage, traceability, and published-version rules.
3. Keep shared core/service logic as the source of truth for business behavior.
4. Maintain desktop fallback stability when desktop code is touched.
5. Add regression coverage for trust-eroding workflow bugs.
6. Keep repo guidance aligned with the actual current state.

## Recent Meaningful Changes

### [2026-04-18] Browser settings now retries the first trusted-profile detail load once after a transient 5xx so startup profile switches do not strand operators behind a refresh-only recovery
- **What changed:** The browser app now retries trusted-profile detail loading once when the settings workspace hits a transient 5xx while opening the selected profile. Regression coverage now includes the exact startup path where the app opens on the default profile in review, the operator switches to another profile before ever visiting settings, and the first settings detail request for that newly selected profile fails once before succeeding on retry without surfacing a lasting `500 Internal Server Error`.
- **Why:** A final startup-only variant of the stale/recoverable settings bug could still survive the settings-session reset hardening. The operator could switch profiles in review before the first settings visit, hit a one-time `500`, and only recover by refreshing the page. Since refresh immediately fixed the state, the browser should perform that one recoverable retry itself.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** This retry is intentionally narrow and only for transient settings detail load failures. If a persistent backend error remains, the browser still surfaces it normally instead of hiding it behind indefinite retries.

### [2026-04-18] Browser settings now start a fresh settings-session on each re-entry from review to prevent stale editor context from surviving across workspace exits
- **What changed:** Re-entering the browser profile-settings workspace now resets settings-scoped detail, draft, loading, and local workspace instance state before the new profile detail is loaded. The settings workspace is keyed by a re-entry session counter so internal browser-only editor state cannot survive a leave-to-review / return-to-settings cycle. Regression coverage now includes the exact path of entering settings on profile A, switching to profile B inside settings, leaving to review without taking review actions, and reopening settings under profile B.
- **Why:** The earlier profile-context guard removed the common stale-profile path, but a harder-to-reproduce variant could still surface `500 Internal Server Error` after a settings-side profile switch followed by leaving to review and reopening settings. The remaining issue was stale browser-only settings workspace state surviving across workspace exits.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** If we later want unsaved browser-only settings state to persist across leaving the settings workspace entirely, move that retained state to an explicit app-level session store instead of relying on component lifetime.

### [2026-04-18] Browser settings now re-enter under the newly selected review profile instead of reusing stale profile editor context
- **What changed:** The browser app now clears and reloads settings-scoped profile detail/draft state when the review-side trusted profile selection changes or when the operator re-enters the profile-settings workspace. Settings actions now scope themselves to the currently selected trusted profile, and a new regression proves that switching from one profile in review to another profile before reopening settings edits against the newly selected profile's draft API path instead of reusing the prior profile's editor context.
- **Why:** Operators could hit a trust-eroding browser state bug where entering settings for profile A, returning to review, switching to profile B, and reopening settings could surface a transient `500 Internal Server Error` until the page was refreshed. The root issue was stale settings context surviving a review-side profile switch.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** If future browser workflow work adds richer loading or optimistic profile prefetching, keep settings actions gated on the selected profile's current detail state so review-side profile switches cannot revive stale editor context.

### [2026-04-18] Browser review export now invalidates after any successful profile-settings save until reprocess
- **What changed:** The web app now uses the existing review export-invalidation seam to mark the loaded review stale immediately after any successful profile-settings save/publish while a review session is open. Returning to the review workspace shows the stale-export banner, disables `Export and Download`, clears any previously downloaded export artifact, and keeps export blocked until the user reprocesses. Browser workflow coverage now exercises the full process -> save settings -> blocked export -> rerun -> export re-enabled flow.
- **Why:** A loaded review is a fixed snapshot of the profile version used during processing. Allowing export after later saved profile changes made it too easy to export a run that no longer matched the operator's current saved settings without forcing a fresh processing run.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** This is intentionally a browser workflow guard, not a backend lineage change. If the product later needs server-enforced export invalidation across tabs or devices, add a persisted run-versus-profile freshness check instead of duplicating more browser-only state.

### [2026-04-18] Browser profile-settings saves now send draft revision CAS state on every draft mutation and publish
- **What changed:** The web profile-settings client and app save workflow now carry `draft_revision` in browser draft state, include `expected_draft_revision` on every draft mutation and publish request, and keep the latest returned draft revision in a live ref so multi-step save flows do not reuse stale revision values between awaited requests. The settings workspace regression tests now enforce the same revision requirement the API enforces and cover the end-to-end save/publish workflow under that stricter contract.
- **Why:** Phase 7 hardened the API to require fail-fast draft compare-and-swap, but the browser settings client was still sending the pre-hardening request shape, which caused every profile-settings save attempt to fail at request validation with HTTP 422.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** Review edits in local mode still rely on the older client shape because the API keeps a local fallback there; if hosted review editing becomes the default browser mode, align that client path with the hosted `expected_current_revision` contract too.

### [2026-04-18] Hosted trusted-profile draft edits now use compare-and-swap revisions
- **What changed:** Draft editor states and hosted draft mutation requests now carry `draft_revision` / `expected_draft_revision`, and every hosted profile-authoring save path compares the caller's expected revision before persisting. The SQLite/Postgres lineage stores now reject stale draft writes with the existing persistence conflict error, which the API maps to HTTP 409.
- **Why:** Phase 7 draft concurrency hardening needs fail-fast optimistic locking for web-authored profile edits without starting publish compare-and-swap yet.
- **Area:** Application services / Persistence/API / Tests
- **Follow-up needed:** Publish still uses the existing path for now; if publish hardening becomes necessary later, keep its revision guard separate so the current draft CAS behavior stays lean.

### [2026-04-18] Trusted-profile drafts now carry a persisted revision counter for later conflict-safe writes
- **What changed:** Added `draft_revision` to the trusted-profile draft model, seeded new drafts at revision `1`, taught the normal draft-save path to advance the persisted revision, and taught both lineage stores plus the SQLite/Postgres schema paths to persist and hydrate that value. A focused Postgres lineage-store test now proves a real save round-trips with revision `2`, and a forward Postgres migration now safely backfills already-upgraded schemas.
- **Why:** Phase 1 of the draft/review conflict-safety work needs a stable persisted revision primitive before any compare-and-swap behavior is introduced.
- **Area:** Persistence/API / Tests / Config/docs
- **Follow-up needed:** Later tasks can use the revision field to detect stale draft writes and review-session conflicts without widening the store protocol prematurely.

### [2026-04-18] Hosted uploads and generated artifacts can now survive across API instances through shared runtime storage
- **What changed:** Added a shared `VercelBlobRuntimeStorage` implementation behind the existing `RuntimeStorage` seam and updated API runtime composition so deployments can select `local` or `vercel_blob` storage without changing routes or services. Hosted-compatible upload, export-workbook, and profile-sync archive flows now persist artifact bytes plus explicit metadata in shared storage and materialize per-instance local cache files only when the existing processing/download pipeline needs a `Path`. New regression coverage proves one instance can upload/process/export while another instance later resolves and downloads the same artifacts.
- **Why:** Phase 6 needed hosted-safe artifact storage and multi-instance runtime behavior without reopening the persistence/auth architecture or reintroducing hosted assumptions that the same machine which saved a file will later read it.
- **Area:** Persistence/API / Tests / Config/docs
- **Follow-up needed:** Long-term shared-deployment hardening still needs operational retention/sweeping outside request paths, eventual object-storage lifecycle policy decisions, and a future cleanup of temporary local materialization once processing/export flows can consume persisted artifacts more directly.

### [2026-04-18] Hosted API requests now resolve through authenticated org/user context with persisted org default-profile state
- **What changed:** Added a real bearer-token request-context provider for hosted API mode, persisted org/user lifecycle support, and an organization-level `default_trusted_profile_id` that is seeded once from the bundled default baseline. Hosted trusted-profile listing, create-profile default seeding, processing/review/export audit fields, and cross-org access now run through authenticated org/user context instead of relying on `org-default` or `ProfileManager.get_active_profile_name()` as hosted fallbacks.
- **Why:** Phase 5 needed real hosted org/user behavior and a persisted org-scoped default profile before moving on to broader shared deployment hardening, without reintroducing filesystem profiles as the hosted source of truth.
- **Area:** Application services / Persistence/API / Tests / Config/docs
- **Follow-up needed:** Shared-deployment hardening still needs stronger token/secret operational handling, upload/export storage scoping beyond local runtime files, and eventual auth-provider/product rollout beyond the current signed bearer-token compatibility step.

### [2026-04-18] Hosted reads now use organization-scoped persistence instead of raw-ID fetch plus service-side assertion
- **What changed:** Added org-aware lineage-store methods for hosted reads of trusted profiles, versions, drafts, sync exports, source documents, processing runs, snapshots, review sessions, run records, reviewed edits, and export artifacts. `ProcessingRunService`, `ReviewSessionService`, `ProfileAuthoringService`, `TrustedProfileProvisioningService`, and `TrustedProfileService` now resolve the request organization first and read through organization-scoped persistence methods instead of loading by raw id and checking organization afterward. New API and Postgres integration tests now verify cross-org access fails closed as not found.
- **Why:** Phase 4 needed tenant safety at the repository/store boundary so shared-hosting mode does not depend on route-layer checks or post-fetch assertions to block cross-organization reads.
- **Area:** Application services / Persistence/API / Tests / Config/docs
- **Follow-up needed:** Full auth-backed request-context resolution still remains later, and concrete-store compatibility helpers like raw-id reads/global listings still exist for local tests and desktop-style flows even though hosted services no longer rely on them.

### [2026-04-18] Postgres lineage persistence now exists behind the existing store seam in compatibility single-org mode
- **What changed:** Added a `PostgresLineageStore` implementation behind the existing `LineageStore` contract, real Postgres schema migrations, runtime provider selection via API settings, and a SQLite-to-Postgres import utility that preserves current text IDs and lineage rows. Focused Postgres integration tests now cover runtime selection, immutable runs, append-only review edits, exact-revision exports, draft/publish immutability, and SQLite import fidelity.
- **Why:** Phase 3 needed a real Postgres-backed persistence path without reopening service architecture work or changing current single-org/local-web behavior.
- **Area:** Persistence/API / Tests / Config/docs
- **Follow-up needed:** Phase 4 still needs org-aware store methods instead of post-fetch assertions, runtime/storage scoping beyond the current local-default org behavior, and eventual cleanup of compatibility choices like text timestamp storage and temp filesystem execution bundles.

### [2026-04-18] Postgres connection variables are now staged in a repo-root env template
- **What changed:** Added a checked-in `.env.example` with explicit placeholders for the Neon admin/migration connection string and the Neon pooled application connection string, and documented the paste locations in `README.md`. The runtime still stays on SQLite for now.
- **Why:** This sets the Postgres connection contract in one place before the next persistence phase without prematurely rewiring services or application startup.
- **Area:** Config/docs
- **Follow-up needed:** The next Postgres phase still needs actual settings/runtime consumption and a Postgres-backed lineage store implementation.

### [2026-04-18] Workspace settings now point VS Code Python terminals at the repo `.env`
- **What changed:** Added a workspace `.vscode/settings.json` that sets `python.envFile` to the repo-root `.env` and enables `python.terminal.useEnvFile`.
- **Why:** This makes the staged Postgres environment variables available to new VS Code Python terminals without changing application runtime code.
- **Area:** Config/docs
- **Follow-up needed:** Existing terminals still need to be reopened, and future runtime phases still need actual application settings consumption for the Postgres variables.

### [2026-04-18] Trusted-profile bootstrap/materialization moved out of persistence-facing code
- **What changed:** Trusted-profile persistence is now cleanly narrowed to persisted profiles, versions, drafts, observations, and sync-export rows. Local filesystem bootstrap/provisioning moved into `TrustedProfileProvisioningService`, and temp config-bundle execution materialization moved into `ProfileExecutionCompatibilityAdapter`. `ProcessingRunService`, `ReviewSessionService`, and desktop sync export now consume those explicit seams instead of letting repositories or services hide bootstrap/materialization policy.
- **Why:** Phase 2 of the SQLite-to-Postgres transition needed bootstrap, provisioning, and temp-bundle compatibility logic separated from persistence so Postgres can replace SQLite later without dragging local filesystem policy and execution shims through the repository boundary.
- **Area:** Application services / Persistence/API / Tests / Config/docs
- **Follow-up needed:** Phase 3+ still need org-aware persistence methods, storage scoping, and eventual removal of temp filesystem compatibility once parser/review/export flows can consume persisted bundles directly.

### [2026-04-18] API/runtime composition now uses a lineage protocol seam and request-scoped organization context
- **What changed:** Extracted a shared `LineageStore` protocol for the current web/API persistence surface, introduced an explicit `RequestContext` seam with a local default dependency in `api/`, and rewired API runtime composition so `ProcessingRunService` receives its trusted-profile repository/profile-authoring collaborators through composition instead of instantiating them internally. API-facing run, review, export, trusted-profile, and profile-authoring routes/services now accept request context and enforce organization scope without changing the default `org-default` local behavior.
- **Why:** This creates the dependency-inversion and request-context boundary needed for upcoming Postgres and multi-organization work without piling new layers on top of SQLite-specific wiring or changing current operator-visible behavior.
- **Area:** Application services / Persistence/API / Tests / Config/docs
- **Follow-up needed:** Phase 2 still needs a real organization-aware store implementation, auth-backed request-context resolution, and consistent upload/storage scoping beyond the current local-default context seam.

### [2026-04-13] Phase 3 profile export now uses template metadata, export settings, and inactive-slot compaction
- **What changed:** Trusted-profile authoring now persists template metadata and export-only settings alongside the draft/published bundle, profile classification slots can keep inactive overflow rows beyond active template capacity, and recap export now compacts active labor/equipment slots into contiguous template rows so inactive middle slots no longer leave blank workbook gaps. The web settings surface now exposes template capacity and the first export-only rule for labor minimum-hours shaping.
- **Why:** Phase 3 needed to preserve lineage-ready template context, unblock future multi-template work without starting it yet, and fix the trust-eroding blank-row export behavior caused by inactive classifications in the middle of the slot list.
- **Area:** Core engine / Application services / Persistence/API / Web delivery / Tests / Config/docs
- **Follow-up needed:** Phase 4 can build multi-template browsing/selection on top of this metadata model, but template choice remains fixed for now and export ordering still follows slot-table order.

### [2026-04-11] Review header now uses a single seven-block summary row
- **What changed:** The browser review header no longer shows the extra descriptive sentence beneath the source filename. Instead, the filename/workspace label now occupies the first tile in a single seven-block top summary row, with the existing raw total, included total, omitted total, total records, blockers, and trusted profile tiles staying alongside it.
- **Why:** The prior stacked header was consuming more vertical space than needed and pushed useful review canvas space downward without adding much operator value.
- **Area:** Web delivery / Config/docs
- **Follow-up needed:** If more review-shell compression happens later, keep the top summary row readable and avoid reintroducing secondary helper copy that competes with the actual metrics.
