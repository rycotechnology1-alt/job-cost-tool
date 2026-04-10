# Four-Phase Advanced Feature Delivery Plan

## Summary
- Deliver the advanced-feature list in four phases so each phase produces a usable operator win without forcing the heavier template-model work too early.
- Keep the existing architecture intact: `core/` and `services/` remain the source of truth, `api/` stays thin, `web/` carries the operator workflows, and desktop is only touched when shared logic or parity requires it.
- Preserve all current lineage rules: runs remain immutable, review edits stay append-only, and profile/template changes only affect future published-version processing and export.

## Phase 1: Review Throughput And Multi-Upload Queue
**Goal**
- Remove the highest-friction operator bottlenecks in the current review workflow without changing the profile or template data model.

**Deliverables**
- **Staged multi-upload queue in the review launch flow**
  - Replace the single-file upload entry with a queue that can hold multiple PDFs in the browser/runtime upload cache.
  - Let operators add, remove, inspect, and process queued PDFs one at a time without re-uploading each file.
  - Keep processing sequential and operator-triggered. Do not introduce background worker infrastructure in this phase.
- **Collapsed review grouped by family**
  - Group review rows by record family in the main review workspace.
  - Each family header shows:
    - family name
    - total rows
    - included cost subtotal
    - omitted cost subtotal when nonzero
    - collapsed or expanded state
  - Default to collapsed groups, but preserve current row selection and edit behavior inside expanded groups.
- **Review totals**
  - Add summary metrics for:
    - full raw report total
    - included or exportable total
    - omitted total
  - These totals must respond immediately to review omission changes.
- **Bulk row actions in review**
  - Add row multi-select.
  - Support bulk:
    - omit selected
    - include selected
  - Submit as one append-only review revision operation, not one revision per row.

**Implementation Notes**
- `web`
  - Expand `UploadRunPanel` into a queue-based pre-review launcher.
  - Expand `ReviewWorkspace` to support grouped rendering, totals, and row multi-select.
- `api/services`
  - Reuse the existing upload lifecycle where possible, but add queue-oriented list, remove, and process seams if the current API is too single-upload specific.
  - Add batch review-edit submission over multiple `record_key`s.
- `contracts`
  - Either extend review responses with family-summary and totals metadata or derive them in the browser from existing row data if that keeps the contract simpler and deterministic.

**Acceptance Criteria**
- An operator can stage 5-10 PDFs and process them one after another without re-uploading.
- Review rows render grouped by family and remain editable at row level.
- Raw total and included total are always visible and correct.
- Bulk omit and include creates exactly one new review revision per action.

**Tests**
- Browser regression for multi-upload staging, removal, and processing.
- Browser regression for grouped family display and totals.
- API or service regression for bulk omission and include over multiple rows.
- Regression that exportability and blocker logic still follows the current review revision only.

---

## Phase 2: Mapping Workflow And Bulk Review Enhancements
**Goal**
- Improve high-volume mapping and current-report triage workflows after the basic throughput improvements are in place.

**Deliverables**
- **Bulk apply classification or category in review**
  - Add bulk labor classification apply for selected compatible labor rows.
  - Add bulk equipment category apply for selected compatible equipment rows.
  - Reject incompatible mixed selections clearly.
- **Bulk apply targets in profile settings mappings**
  - Add multi-select to labor and equipment mapping rows.
  - Support bulk target assignment to the selected mapping rows.
  - Keep row-level editing intact.
- **Required unmapped rows prioritized**
  - In settings mapping sections, split rows into:
    - required for recent or current processing observations
    - all other observed or user-maintained rows
  - Required unmapped rows appear first and are visually emphasized.
  - Keep the emphasis informative, not blocking by itself.
- **Predictive equipment mapping**
  - Restore or add suggestion logic for equipment observations.
  - Suggestions are advisory only and show as recommended targets on a row.
  - The operator must explicitly accept or override them.

**Implementation Notes**
- `web`
  - Extend `ReviewWorkspace` selection model from phase 1 to support compatible bulk category and classification actions.
  - Extend `ProfileSettingsWorkspace` mapping sections with selected-row state, required-row grouping, and suggestion affordances.
- `services`
  - Add or restore an equipment-prediction seam in shared mapping or helper logic rather than browser-only heuristics.
  - Expose a clean "required observation rows first" view model from authoring services if the browser would otherwise need to infer too much.
- `contracts`
  - Mapping rows may need fields like:
    - `is_required_for_recent_processing`
    - `prediction_target`
    - `prediction_confidence_label`
  - The review batch-edit endpoint should support multi-record changed fields for labor and equipment targets.

**Acceptance Criteria**
- Operators can bulk classify or categorize selected compatible rows in review.
- Operators can bulk apply mapping targets in settings.
- Required unmapped rows appear first and are clearly distinguishable.
- Equipment suggestions appear when available and never auto-apply silently.

**Tests**
- Browser regressions for bulk labor and equipment review actions.
- Browser regressions for bulk mapping target assignment.
- Browser regressions for required-row prioritization.
- Service or API tests for equipment prediction output shape and deterministic behavior.
- Regression that invalid bulk mixed-type selections fail clearly and do not partially apply.

---

## Phase 3: Profile Capacity And Export Settings Foundation
**Goal**
- Introduce the data-model changes needed for future template flexibility without yet building the full template-platform UX.

**Deliverables**
- **Inactive extra classifications**
  - Allow a profile to store additional labor and equipment classifications beyond the currently active export slots.
  - Distinguish:
    - active template-bound slots
    - inactive stored classifications
  - Keep existing active slot behavior stable for current templates.
- **Template-bound active slot capacity**
  - Stop assuming classification capacity is fixed forever by the current export template.
  - Move the active-slot limit into template metadata and model behavior.
  - Profiles can keep inactive extra classifications ready for future templates.
- **Export minimum-hours setting**
  - Add export settings so operators can define a minimum-hours override rule for labor lines during export only.
  - First rule shape:
    - if export hours are below threshold, replace that line's exported hours with the configured minimum
  - This must not mutate stored run or review data.
- **Template foundation**
  - Add backend template registry and metadata support sufficient for:
    - template identity
    - active labor slot capacity
    - active equipment slot capacity
    - supported export behaviors or notes
  - Do not build the rich dashboard yet. This phase is model, service, and contract groundwork only.

**Implementation Notes**
- `services/repository/contracts`
  - Extend profile authoring contracts to return active slots and inactive extra classifications separately.
  - Introduce template metadata records and contracts without breaking existing single-template published profiles.
  - Extend published-version payload and hash inputs so selected template identity remains part of lineage.
- `web`
  - Update settings UI to display active versus inactive classifications clearly.
  - Add an export-settings editing area for minimum-hours rules.
- `core/export`
  - Apply minimum-hours logic in export shaping only, behind profile, template, and export-settings interpretation.

**Acceptance Criteria**
- Operators can maintain inactive extra classifications without affecting current exports until activated by template capacity.
- Active slot capacity is driven by template metadata, not hard-coded assumptions.
- Minimum-hours export changes workbook output only.
- Published versions still capture exact template and profile state for future reproducibility.

**Tests**
- Service and repository tests for active versus inactive classification persistence.
- Service and repository tests for template-capacity enforcement.
- Export tests proving minimum-hours override affects workbook output only.
- Regression that old published versions remain reproducible and unaffected by later template or profile changes.
- Browser tests for active and inactive classification presentation and export-settings editing.

---

## Phase 4: Multi-Template Platform And Template Dashboard
**Goal**
- Build the operator-facing template platform on top of the phase-3 foundation.

**Deliverables**
- **Multiple export templates**
  - Support multiple selectable templates in the system.
  - Profiles can target a selected template and publish that selection into the current published version.
- **Template inspection dashboard**
  - Add a browser-side template review surface showing:
    - template identity
    - allowed labor and equipment slot counts
    - supported family and section behaviors
    - relevant export notes and rules
  - This is an inspection and configuration dashboard, not a visual drag-and-drop template designer.
- **Summary-style or clean invoice template support**
  - Support templates that use backend-computed family, hour, and rate summaries instead of exposing all detailed rows and rates in the workbook.
  - Keep this template-driven and explicit.
  - The system should know where charges map by the selected template metadata plus export transformation rules, not by UI-only assumptions.
- **Template selection in profile authoring**
  - Let operators inspect and select the template in settings as part of profile authoring before publish.
  - Changing template must respect capacity constraints and published-version lineage.

**Implementation Notes**
- `services/api`
  - Add template list and detail APIs and integrate selected template identity into profile detail and draft state.
  - Keep publish validation responsible for rejecting incompatible template and profile combinations.
- `web`
  - Extend settings to include template inspection and selection.
  - Add warnings when a template change would exceed active slot capacity or require profile cleanup.
- `core/export`
  - Support template-driven export modes:
    - detailed workbook mapping
    - summarized or cover-sheet-style output
  - Keep calculation policy explicit and test-protected.

**Acceptance Criteria**
- Operators can inspect available templates and choose one for a profile.
- The selected template controls active slot capacity and export behavior.
- Summary-style templates can produce clean export output without mutating source review data.
- Published versions preserve exact template identity and remain reproducible later.

**Tests**
- API and service tests for template list, detail, and select flows.
- Service tests for publish validation against template capacity.
- Export tests for both detailed and summarized template modes.
- Browser tests for template dashboard visibility, selection, warnings, and publish flow.
- Regression that older published versions continue exporting with their original template identity.

## Cross-Phase Rules
- Keep each phase independently shippable.
- Do not start phase 3 or 4 model changes inside phase 1 just for convenience unless a minimal seam is strictly required.
- Keep desktop untouched unless shared logic changes require parity-safe adjustments.
- Update `docs/transition_tracker.md` at the end of each completed phase with only the current high-signal outcome and follow-up.

## Assumptions
- Operator throughput is the highest-value first priority.
- Phase 1 is intentionally the smallest usable throughput slice.
- Bulk review actions initially include only omit and include in phase 1.
- Predictive equipment mapping remains suggestion-based, not automatic.
- Minimum-hours override applies to labor export lines only unless later expanded.
- Template work should start with foundation and modeling before rich operator dashboard behavior.
