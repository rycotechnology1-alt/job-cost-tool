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

### [2026-04-09] Phase 2 added bulk review classification actions and prioritized mapping guidance
- **What changed:** The web review workspace can now bulk-apply one labor classification or equipment category across compatible selected rows, and the profile-settings mapping tables now surface required unresolved observations first, support bulk target assignment, and show advisory equipment suggestions.
- **Why:** This lands the second operator-throughput slice from the advanced-feature roadmap and reduces repetitive mapping/review work without changing lineage or published-version rules.
- **Area:** Application services / Persistence/API / Web delivery / Tests
- **Follow-up needed:** If later review polishing continues, consider hiding irrelevant bulk controls more aggressively for mixed selections and refine equipment-suggestion heuristics against broader pilot data.

### [2026-04-09] Review workflow now supports staged PDF queueing, grouped families, totals, and bulk omit/include
- **What changed:** The browser review launch flow now stages up to 10 PDFs in a reusable queue, review rows render grouped by family with full raw/included/omitted totals, and batch omit/include actions submit one append-only edit batch across the selected rows.
- **Why:** This lands the first operator-throughput slice from the advanced-feature roadmap without widening into later template/model work.
- **Area:** Web delivery / Tests
- **Follow-up needed:** Later phases can build on the staged queue and grouped-row selection model for bulk classification/category changes and mapping-priority workflows.

### [2026-04-09] Web settings now uses a simpler current-profile edit/save flow
- **What changed:** The browser settings workspace now presents `Edit current profile` and `Save profile settings` instead of exposing create/open/publish draft terminology. Saving batches dirty section saves and publishes in one operator-facing flow.
- **Why:** The earlier draft lifecycle wording was correct technically but confusing operationally.
- **Area:** Web delivery / Tests
- **Follow-up needed:** Keep future settings UX changes in operator-facing language instead of reintroducing backend draft jargon.

### [2026-04-09] Web settings now blocks unsafe leave-with-unsaved changes and no longer restores false empty draft state
- **What changed:** Fixed the remount bug that could reopen saved settings as if they were blank, and added an explicit leave-settings dialog with save, discard, and stay actions.
- **Why:** The old behavior undermined trust in saved profile settings.
- **Area:** Application services / Persistence/API / Web delivery / Tests
- **Follow-up needed:** Browser/tab-close warnings are still a separate decision if later requested.

### [2026-04-08] Uploaded source PDFs now expire from temporary web storage
- **What changed:** Added a short-retention upload lifecycle with cleanup and clear stale-upload messaging.
- **Why:** Cached source PDFs were lingering in runtime storage longer than intended.
- **Area:** Persistence/API / Web delivery / Tests
- **Follow-up needed:** Revisit only if the product later needs longer-lived source-document retrieval.

### [2026-04-08] Review classification edits now stay constrained to run-bound trusted-profile options
- **What changed:** Browser review classification edits now use run-snapshot-backed options and reject values outside the run's trusted-profile snapshot.
- **Why:** Freeform classification editing in web was diverging from the intended product rules.
- **Area:** Application services / Persistence/API / Web delivery / Tests
- **Follow-up needed:** If review-editor polish continues later, hide irrelevant selectors by row type without weakening snapshot validation.

### [2026-04-08] Export now invalidates immediately when trusted-profile selection changes after processing
- **What changed:** The browser review workflow now blocks export as soon as the selected trusted profile no longer matches the processed run context.
- **Why:** Operators could otherwise export stale review state under a different visible profile selection.
- **Area:** Web delivery / Tests
- **Follow-up needed:** If needed later, surface more run-profile snapshot detail for extra operator trust.
