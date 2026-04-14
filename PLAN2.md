# Phase 4 Plan: Multi-Template Catalog, Dashboard, and Profile Selection

## Summary
- Build Phase 4 as a versioned, admin-editable template catalog on top of the Phase 3 template foundation.
- Limit this phase to multiple **detailed** export templates only. Do not implement summary or cover-sheet export modes yet.
- Let profile drafts inspect and select a published template version, persist that choice into the draft, and block profile publish when the selected template is incompatible with the profile’s active slot counts.

## Key Changes
- **Template catalog and lineage**
  - Introduce first-class logical templates with immutable published template versions and one editable draft per template.
  - Store each template version as:
    - workbook artifact
    - structured mapping metadata
    - template metadata and notes
    - derived labor/equipment active capacities
  - Keep published profile lineage exact by storing the selected `template_version_id` in the profile draft and snapshotting that exact template version into the published profile bundle.

- **Admin-editable template management**
  - Add a browser template-management surface inside settings for internal admins/operators.
  - Support:
    - create template
    - open existing template draft
    - upload or replace workbook
    - edit structured mapping forms
    - edit display metadata, notes, and behavior flags
    - publish a new template version
  - Use structured forms, not a visual designer:
    - header field cell refs
    - labor row definitions
    - equipment row definitions
    - bounded list-section mappings
    - sales-tax area mappings
    - template notes and supported behavior flags

- **Template dashboard and profile selection**
  - Add a read-only dashboard/detail view for published templates showing:
    - identity and version
    - workbook filename
    - labor/equipment capacities
    - row/section behavior summary
    - export notes
    - compatibility state for the currently open profile draft
  - Extend profile settings so a draft can select a published template version.
  - When the selected template has lower capacity than the current active slots:
    - keep the draft selection
    - surface compatibility warnings immediately
    - block profile publish until the profile is cleaned up
    - do not auto-trim or silently deactivate slots

- **Shared export/runtime behavior**
  - Move runtime template resolution from “current single template metadata on the profile” to “selected published template version.”
  - Keep export behavior template-driven and versioned, but restrict supported template mode in this phase to detailed row-mapped export only.
  - Preserve current inactive-slot compaction, rates, and export-only settings behavior under whichever detailed template version the profile selected.

## Public Interfaces
- **Template APIs**
  - Add template catalog list/detail endpoints for published templates.
  - Add template draft endpoints for create/open, workbook upload, metadata/mapping patch, validation, and publish.
  - Return both user-facing metadata and compatibility-ready capacity/mapping summaries.

- **Profile authoring APIs**
  - Extend profile detail and draft state with:
    - available published templates
    - selected `template_version_id`
    - selected template summary
    - compatibility warnings or publish blockers
  - Add a template-selection patch endpoint on profile drafts.

- **Core/shared types**
  - Add versioned template entities and draft/editor state equivalents.
  - Keep published profile bundles carrying exact template identity, workbook artifact reference, and normalized template metadata snapshot.

## Test Plan
- **Services and persistence**
  - Template repository/service tests for draft creation, workbook replacement, mapping-form persistence, publish versioning, and exact version reuse.
  - Profile authoring tests for template selection persistence, compatibility warnings, and publish rejection when active labor/equipment counts exceed selected template capacity.
  - Lineage regressions proving older published profiles still export with their original selected template version after later template edits.

- **Export**
  - Export regressions for multiple detailed templates with different row layouts and capacities.
  - Regression that Phase 3 export-only behaviors still hold after template switching:
    - inactive-slot compaction
    - labor minimum-hours override
    - totals and rates alignment

- **Browser/API**
  - Browser tests for template catalog visibility, create/edit/publish flow, workbook upload, structured mapping forms, and template dashboard inspection.
  - Browser tests for profile template selection, compatibility warnings, blocked publish, and successful publish after cleanup.
  - API contract tests for template list/detail/draft/select flows.

## Assumptions and Defaults
- Admin-editable means an internal one-org management surface in the existing product; no new RBAC/auth system is introduced in this phase.
- Template authoring uses workbook upload plus structured mapping forms; no drag-and-drop or cell-designer UI.
- Profile drafts store an explicit selected published `template_version_id`; they do not follow a template’s latest version implicitly.
- Incompatible template selection is allowed to persist in the profile draft for inspection and cleanup, but profile publish is blocked until the profile fits.
- Summary-style templates are out of scope for this Phase 4 plan and should remain future work.
