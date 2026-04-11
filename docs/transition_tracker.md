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

### [2026-04-11] Profile settings now forces open drafts to resolve before leaving and auto-discards them on browser exit
- **What changed:** The browser settings workspace now treats any open profile draft as a blocking unpublished change, even when no local sections are currently dirty. Leaving settings for review or another trusted profile now always forces `Save and leave`, `Don't save`, or `Stay here`, and browser/tab exit uses a keepalive draft-discard request so unpublished badges do not survive normal browser navigation away from the page.
- **Why:** Operators could previously leave settings with a clean-but-open draft still attached to the profile, which let the `Unpublished changes` badge linger and undermined trust in whether profile edits were truly resolved.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** Browser-exit discard remains best-effort because it depends on the platform delivering the keepalive request, so keep future workflow changes explicit about save/discard resolution before leaving settings.

### [2026-04-11] Active trusted-profile switching rows and creation flow now center display names in settings
- **What changed:** The browser settings sidebar now renders `Profiles in this organization` as denser two-row quick-pick cards: row one shows display name plus version, row two shows only remaining status badges like `Unpublished changes`, and the previous source badge was removed. Profile creation now asks operators only for a display name; the browser derives the stable backend key from that name by replacing spaces with hyphens and stripping unsupported characters.
- **Why:** The earlier full-card treatment scaled poorly once an organization had many trusted profiles, and exposing backend-style profile keys in the create flow added clutter without helping operators.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** If later settings polish continues, revisit whether the top trusted-profile dropdown is still useful once the compact row selector has been exercised with broader operator data.

### [2026-04-11] Clean unpublished profile drafts can now be explicitly saved away
- **What changed:** The browser settings workspace now keeps `Save profile settings` available for a valid open draft even when the on-screen editor matches the live/unpublished baseline again, so operators can clear the lingering `Unpublished changes` state without making a throwaway edit. Added a browser regression covering edit-then-revert followed by no-op publish.
- **Why:** The prior dirty-section gating could strand a valid open draft with the unpublished badge still visible after an operator reverted their edits before saving, which undermined trust in the settings workflow.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** Keep future settings-status copy explicit about the difference between local unsaved browser edits and persisted unpublished draft state.

### [2026-04-10] Profile settings now shares the review workspace console-style shell
- **What changed:** The browser profile-settings page now uses the same dark console-style shell language as review, with a persistent settings side rail for profile controls and lifecycle cards while the existing authoring sections remain in the main content column.
- **Why:** The old settings layout was functionally complete but visually disconnected from the newer review workspace and harder to scan as one product surface.
- **Area:** Web delivery / Config/docs
- **Follow-up needed:** If more settings polish continues later, keep the console shell aligned with review without reintroducing redundant controls or changing the current profile-authoring workflow.

### [2026-04-10] Review launch action moved to the top bar and the left rail was simplified
- **What changed:** The review page now launches processing from a top-bar `Process Source PDF` button, and the left staging rail no longer shows the redundant trusted-profile summary card.
- **Why:** The profile summary duplicated information already visible elsewhere, and the processing action is easier to find in the top status area.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** If more review-shell cleanup continues, keep launch and queue controls distinct so the staged-file rail remains focused on selection and status rather than mixed actions.

### [2026-04-10] Review workspace now uses a consolidated dashboard-style shell
- **What changed:** The browser review page now presents staging in a persistent left rail, keeps the grouped review table and bulk actions in the center, and uses a darker dashboard-style layout inspired by the pilot mockup while preserving the existing staging, review-edit, and export workflows.
- **Why:** The earlier stacked layout worked functionally but felt visually disconnected and harder to scan during review.
- **Area:** Web delivery / Tests / Config/docs
- **Follow-up needed:** If later polishing continues, revisit whether the right rail should surface richer readiness summaries without duplicating backend/export-state concepts.

### [2026-04-10] Review export is now visible immediately when the workspace opens
- **What changed:** The browser review sidebar now keeps the export card visible as soon as a review session loads instead of hiding export behind selected-row details.
- **Why:** Export readiness is a workspace-level action, so gating the button behind row selection was unnecessary and confusing.
- **Area:** Web delivery / Tests
- **Follow-up needed:** If the sidebar keeps shrinking later, consider whether export and other workspace-level actions should stay in the sidebar or move into a dedicated header actions region.

### [2026-04-10] Review vendor editing now lives in the top action bar with bulk support
- **What changed:** The browser review workspace now applies vendor-name edits from the same top action bar used for omit/include and labor/equipment bulk edits, and the redundant right-sidebar `Edit selected row` editor has been removed.
- **Why:** After the earlier bulk-edit work, the sidebar editor was down to a single vendor-only use case and was making the review workflow feel split and redundant.
- **Area:** Web delivery / Tests
- **Follow-up needed:** If row-editing polish continues later, consider hiding incompatible top-bar actions more aggressively when the current checkbox selection mixes vendor, labor, and equipment rows.

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
