### [2026-04-05] Phase-1 operational hardening now uses explicit runtime storage, legacy-run export status, and small startup settings seams
- **What changed:** Added a small runtime storage contract for uploads and export artifacts, routed API export persistence/download through that seam instead of assuming raw file paths, encoded legacy pre-template-artifact runs as explicitly `legacy_non_reproducible` for exact historical export, added a small `ApiSettings` seam plus default ASGI entrypoint for cleaner FastAPI startup, and moved browser API/backend defaults behind a tiny runtime-config helper. Added regressions for storage round-tripping, legacy-run fail-closed export handling, and runtime default resolution.
- **Why:** The readiness review identified three narrow pre-pilot hardening seams that mattered more than new workflow features: remove the hard-coded file-path assumption around artifact delivery, stop treating pre-artifact historical runs as implicitly reproducible, and make local API/browser startup less brittle without broadening the platform.
- **Area:** Persistence/API prep / Web delivery / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that exact historical export for legacy runs now fails more explicitly in API/service flows instead of as a generic missing-template error, though that is the intended conservative product posture.
- **Follow-up needed:** Before any limited pilot discussion, the main remaining hardening question is whether the current local-file plus SQLite-backed artifact path is sufficient for the expected pilot footprint or whether one more storage-adapter implementation pass is warranted for deployment operations; desktop remains the fallback either way.

### [2026-04-05] The final readily available sample batch is now in the parity corpus, with one reviewed project-management case modeled explicitly
- **What changed:** Added `2pass`, `5pass`, `12pass`, and `19pass` to the real acceptance corpus. `2pass`, `5pass`, and `19pass` were added as clean revision-0 reference cases, while `12pass` was added as a reviewed export case that explicitly un-omits the single project-management row before export. Extended the representative parity batch to cover these final readily available samples.
- **Why:** This was the last available batch of easy-access historical desktop-tested samples, and corpus expansion at this stage is about improving signoff coverage while encoding review context honestly rather than assuming every accepted workbook was produced at revision 0.
- **Area:** Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that future parity blind spots are now more likely to come from missing sample diversity rather than missing sample count, because the readily available corpus now covers both clean revision-0 exports and multiple post-review export patterns.
- **Follow-up needed:** Any further parity-confidence gains now likely depend on curated edge-case/customer-specific samples or intentional corpus maintenance, not on another easy batch of readily available desktop reference files.

### [2026-04-05] The parity corpus now includes three more clean revision-0 desktop-tested cases
- **What changed:** Added `1harness`, `11harness`, and `17harness` to the real acceptance corpus as revision-0 reference cases with no scripted review edits, and extended the representative parity batch to run them through the existing semantic desktop-versus-web harness.
- **Why:** The next controlled corpus-expansion slice needed a few more high-value real cases, and these three all matched their accepted historical desktop workbooks directly under default processing without requiring any post-review export context.
- **Area:** Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that revision-0 assumptions are now overused, because `11harness` still documents a default-omitted dotted-subphase row while proving that not every historically accepted workbook depends on explicit post-review edits.
- **Follow-up needed:** Keep balancing future corpus additions between clean revision-0 cases and reviewed cases so signoff coverage reflects the real desktop workflow rather than only one happy-path mode.

### [2026-04-05] The parity corpus now includes three more real desktop-tested cases across clean, user-un-omit, and manual-correction flows
- **What changed:** Added `10harness` as a clean revision-0 export case, `15harness-user-omit` as a reviewed export case that explicitly un-omits three omitted Herc Rentals rows, and `22harness` as a reviewed export case that explicitly corrects a blocking per-diem reimbursement material row to vendor `pdiem`. Also added optional `notes` metadata on parity cases and extended the representative parity test batch to run these real cases through the existing semantic desktop-versus-web harness.
- **Why:** The next migration step is corpus depth and triage, not new architecture, so the parity gate needed a few more representative real-world cases covering clean export, manual omission-state changes, and manual blocker-clearing correction behavior.
- **Area:** Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that more real cases may still reveal missing review-context or settings-context assumptions, though the harness now has a proven pattern for encoding that context explicitly instead of misclassifying it as product drift.
- **Follow-up needed:** Keep growing the corpus with a small number of high-value real cases and continue classifying each one explicitly as revision 0 or post-review export before using it as a signoff signal.

### [2026-04-05] Real production harness samples now run as revision-aware parity cases over the fixed historical export seam
- **What changed:** Added the provided `6harness`, `7harness`, and `18harness` production-tested samples into the parity corpus, extended the harness to run real PDF inputs and compare semantic workbook snapshots against supplied reference exports, fixed a web-only historical export bug where profile snapshot canonicalization/materialization was reordering fixed recap row mappings, and then updated the corpus format to support scripted review-edit batches plus an explicit `target_export_revision` so historical reference workbooks can be compared against the intended post-edit revision rather than assumed revision 0.
- **Why:** The parity gate needed real acceptance samples, and those samples exposed both a real web export lineage bug and a corpus-shape gap: some accepted historical desktop exports were produced only after manual un-omit/correction edits.
- **Area:** Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that future real corpus cases may require more than one accepted revision before export, though the harness now models that explicitly instead of baking revision-0 assumptions into reference comparisons.
- **Follow-up needed:** Keep expanding the corpus with real reviewed cases and encode accepted manual edits directly into the case files so the parity gate stays reviewable and deterministic.

### [2026-04-02] Phase 50 .15 now routes utility service connection refunds as material
- **What changed:** Added explicit phase-map support for 50 .15 as MATERIAL, which lets generic JC lines under Utility Service Connections inherit a stable material family instead of surviving as unresolved other.
- **Why:** Valid report-body JC lines like National Grid Refund 0.00 -2,904.00 had strong phase context but no configured family, so they stayed blocked by unresolved-family and ambiguity warnings even though signed numeric parsing already worked.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that 50 .15 records now surface the next real blocker, such as missing vendor identity, instead of being masked by a broader unresolved-family failure.
- **Follow-up needed:** If utility service connection refunds need to export without manual vendor correction, add a separate vendor-identity decision intentionally rather than overloading this family-routing fix.

### [2026-04-02] Phase `25` now uses a first-class project-management family with summary export support
- **What changed:** Added explicit phase-map support for `25 . . Labor-Project Mgmt` as a `project_management` family, allowed that family through parser/normalization/export validation, and wired recap export to place summed project-management cost into the summary block at `E59/F59`.
- **Why:** Valid PM allocation `JC` lines were surviving as unresolved `other` records, which blocked export and gave users no meaningful correction path even though the phase context was strong and the recap only needed a summary total.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that future non-list summary families may need their own explicit export totals instead of fitting into the current list-section model, though this is still cleaner than forcing PM allocations into labor or material buckets.
- **Follow-up needed:** If more summary-only families appear, consider a config-driven summary-total mapping layer instead of adding each one directly in code.

### [2026-04-02] PR lines under strong non-payroll phase context now stop carrying false ambiguity blockers
- **What changed:** PR tokenization now falls back to configured phase/header family for non-labor, non-equipment sections such as `Other Job Cost` instead of downgrading those lines back to `other` and leaving an ambiguity warning behind.
- **Why:** Valid report-body PR reimbursement lines under phase `50 . . Other Job Cost` were already inheriting material family at the outer pipeline level, but the inner PR tokenizer still emitted `family is ambiguous`, which validation treated as an export blocker even after users corrected vendor identity.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that unusual PR lines under strong non-payroll phase context now rely more intentionally on section-family fallback, though that is more consistent with the raw-line-preservation policy than forcing manual omission.
- **Follow-up needed:** If more non-payroll PR variants surface, keep tightening structured field extraction separately without removing this family-fallback safety net.

### [2026-04-02] Phase `50 .2` now routes to police-detail export with vendor-preferred labels
- **What changed:** Added explicit phase-map support for `50 .2` as a `police_detail` family, allowed that family through parser/normalization family-label handling, and updated police-detail recap payload building to prefer parsed vendor/display names over raw description when available.
- **Why:** `50 .2 . Police Details` AP lines were inheriting broad phase-50 material behavior and, once exported, would have repeated the same raw-description label issue recently fixed for permits.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that future police-detail rows will aggregate by vendor label instead of raw description when a vendor exists, though that better matches recap intent and preserves raw traceability on the record itself.
- **Follow-up needed:** If more `50`-series subphases appear, keep adding them explicitly through phase config and tests rather than broadening the phase-50 material fallback.

### [2026-04-02] Permit export rows now prefer parsed vendor/display name over raw description
- **What changed:** Permit/fees recap payload building now uses the parsed vendor/display name for permit row labels when available, with raw description kept only as the fallback label when no vendor name was parsed.
- **Why:** After phase `50 .1` started routing correctly as permit instead of material, permit export still echoed full raw description text even though the AP parsing path had already extracted a cleaner vendor/display name.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that some permit rows will now aggregate by vendor label instead of raw description when a vendor exists, though that better matches the intended recap display and still preserves raw traceability on the record itself.
- **Follow-up needed:** If future permit workflows need separate vendor and detail columns, extend the permit export shape intentionally rather than overloading the single description cell.

### [2026-04-02] Phase `50 .1` now routes to permit-family recap export instead of materials
- **What changed:** Added explicit phase-map support for `50 .1` as a permit/fees family and taught the parser/normalization family-label helpers to recognize `permit`, so `Permits & Fees` AP records now keep their own non-material type and flow into the recap permits section.
- **Why:** Phase `50 .1 . Permits & Fees` records were inheriting the broad phase-50 material fallback, which made valid permit/fee AP lines show up as material and export into the wrong recap block.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that future `50`-series subphases need their own explicit config entries rather than inheriting the parent phase family, though that is safer than collapsing meaningful subphases back into broad material behavior.
- **Follow-up needed:** If additional fee/police subphases are confirmed in real reports, add them through phase config and tests rather than introducing export-only exceptions.

### [2026-04-01] Review workflow now supports profile-driven default omission rules
- **What changed:** Added an optional profile-side `review_rules.json` config with `default_omit_rules`, and review load now applies matching rules by setting the existing `is_omitted` flag before validation/export readiness is computed.
- **Why:** Some records such as non-job-related time should still survive parsing/normalization for user control, but they need a reusable profile-driven way to start omitted by default without hiding them or hard-coding export exclusions.
- **Area:** Core engine / Application services / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that overly broad future rules could hide records from export readiness unexpectedly, though the MVP matcher is intentionally narrow and the records remain visible and manually reversible in review.
- **Follow-up needed:** Add a lightweight settings/admin editor for review rules later if users need to manage default omit policies without editing profile JSON by hand.

### [2026-03-31] Parser now preserves distinct `29 .999` labor subphase identity
- **What changed:** Phase-header parsing now retains dotted subphase codes such as `29 .999` instead of collapsing them to bare `29`, and phase mapping now explicitly distinguishes `29` (material Market Recovery) from `29 .999` (labor Non-Job Related Time).
- **Why:** Records under `29 .999. Labor-Non-Job Related Time` were inheriting the wrong material fallback because the parser stripped the subphase before family routing ran.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk, though phase-code identity now matters more explicitly for dotted subphases and any future report variants should preserve that fidelity instead of assuming only a top-level numeric phase.
- **Follow-up needed:** If more reports use meaningful dotted subphases, consider centralizing phase-code canonicalization so config, parsing, and normalization all share one helper instead of relying on matching string forms.

### [2026-03-31] Modified recap template now applies material-row styling consistently and uses a wider grand total range
- **What changed:** Fixed the bundled modified recap template so material vendor rows `G34:H41` use the same styles as `G27:H33`, and widened exported grand total to `=SUM(F52:F62)`.
- **Why:** The lower material rows still carried generic blank-cell styling from the underlying sheet, and the narrower grand total formula did not include the full user-editable summary area.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk, though the polished material-row formatting currently lives in the bundled template asset rather than richer template metadata.
- **Follow-up needed:** If recap template variants grow later, consider validating key section style continuity and summary-formula expectations as part of template compatibility checks.

### [2026-03-31] Export writer now avoids non-anchor merged cells in the modified recap template
- **What changed:** Fixed the summary-area rewrite so it no longer writes into non-anchor cells inside the template's merged footer range, and added an export regression that writes through the real bundled modified recap template asset.
- **Why:** The modified recap template introduced merged ranges that the synthetic export test workbook did not model, and the summary writer was trying to clear `E65:H65` even though `A65:H65` is a single merged cell.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk, though export tests now rely more intentionally on the bundled template asset to catch workbook-structure mistakes that pure synthetic sheets can miss.
- **Follow-up needed:** If more template variants are supported later, add a reusable check that export write targets never point to non-anchor merged cells for a given template/map pair.

### [2026-03-31] Recap export now aligns to the modified workbook layout standard
- **What changed:** Updated the default recap template asset, recap template maps, and export workbook writer so exports now follow the modified workbook structure: right-side header values in column H, materials moved beside equipment with expanded vendor capacity, subcontractors shifted to the left block, permits/police sections moved down, and the summary/tax formulas now match the revised layout.
- **Why:** The modified workbook represented the intended recap format, and export needed to treat that layout as the new standard rather than continuing to normalize output into the older structure.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that older external recap templates with the previous layout will no longer match the updated template-map assumptions as cleanly, though the bundled default profile template and export logic now agree on one explicit workbook standard.
- **Follow-up needed:** If multiple recap template variants need to coexist later, promote more of the summary/header/tax layout behavior into richer template metadata instead of relying on a single modified-layout writer path.

### [2026-03-31] Recap export summary area now uses a cleaner total-and-tax layout
- **What changed:** Rewrote the exported recap summary block to remove redundant material/subcontractor subtotal and markup echoes, moved the tax amount into the left-side summary totals column, and simplified grand total to a contiguous `=SUM(F55:F64)` formula.
- **Why:** The old summary area duplicated values already shown elsewhere on the sheet and forced the grand total to pull from scattered references instead of one clean totals column.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk of diverging from older template expectations, though the export writer now normalizes the summary area into a more reliable workbook structure on every export.
- **Follow-up needed:** If recap templates become more customizable later, promote the summary/totals layout from code into richer template-map metadata instead of relying on the current fixed summary cell arrangement.

### [2026-03-31] Export now writes a template-driven sales-tax block
- **What changed:** Added a small sales-tax area to recap export using config-driven workbook cell positions, with a user-editable tax-rate cell and a formula cell that calculates tax from the material total.
- **Why:** Users need a native workbook-side way to enter sales tax after export without pushing tax concepts into parsing, normalization, or validation.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk of relying on the current recap-template cell layout for styling and placement, though the placement is now surfaced in the recap template map rather than being hidden in ad hoc workbook edits.
- **Follow-up needed:** If recap templates become more editable later, move the sales-tax labels/styles fully into configurable template metadata instead of inferring nearby styling from the current workbook layout.

### [2026-03-31] Export now suppresses low-value subcontractor descriptions
- **What changed:** Subcontractor recap export rows still preserve subcontractor name and amount, but the description column is now intentionally written blank instead of echoing raw source description text.
- **Why:** The current subcontractor raw description adds noise rather than useful signal in the recap workbook, and this is better handled as an export-layer presentation choice than as a parsing or normalization change.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that users who relied on raw subcontractor description text in export will now see blank cells, though the underlying record data remains available for future richer export behavior.
- **Follow-up needed:** If subcontractor descriptions become valuable later, reintroduce them through an intentional export mapping rule or configuration option instead of dumping raw source text by default.

### [2026-03-30] Material overflow export now preserves vendors by first appearance order
- **What changed:** Made material vendor ordering explicit before overflow collapse: vendors now retain first-seen order from the reviewed record list, and only vendors beyond the final preservable slot are rolled into `Additional Vendors`.
- **Why:** Overflow export was already template-driven, but the preserved-vendor selection rule was not explicit enough and could feel arbitrary without a defined ordering contract.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk of changing exports that previously relied on incidental aggregation order, though the new rule is stable, predictable, and easy to explain.
- **Follow-up needed:** If users later want a different vendor ordering strategy, make it a profile/template-level export setting rather than letting ordering drift implicitly in code.

### [2026-03-30] Export now collapses material vendor overflow into a template-driven final row
- **What changed:** Material vendor overflow no longer hard-fails recap export when it can fit by preserving vendors through the penultimate template row and aggregating the remainder into a final `Additional Vendors` row based on the active template's configured material-section capacity.
- **Why:** The export model was treating any vendor overflow as fatal even when the fixed recap template could still preserve most vendors and safely aggregate the remainder without changing parsing, normalization, or review behavior.
- **Area:** Core engine / Application services / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that overflow exports now trade per-vendor detail for a summed final row, though totals remain correct and the behavior is explicitly template-driven.
- **Follow-up needed:** If users need full overflow visibility in the exported workbook later, add a formal overflow detail section or companion export rather than pushing template-capacity concepts back into parsing or normalization.

### [2026-03-30] Validation now blocks labor export when hour type is missing
- **What changed:** Added a validation-stage blocker for labor records that have exportable hours but no labor hour type, and aligned the recap export error path to report a clear missing-hour-type prerequisite instead of a late unsupported-`None` failure.
- **Why:** JC correction lines can legitimately survive parsing with hours and cost but no explicit ST/OT/DT token; the workflow must surface that export-critical gap during review instead of only after the user clicks export.
- **Area:** Core engine / Application services / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk of blocking labor records that previously slipped through to export, though that behavior was already inconsistent with actual export requirements.
- **Follow-up needed:** If manual hour-type correction becomes a frequent workflow need, add a small domain-backed correction path instead of leaving users limited to omission or future parser inference.

### [2026-03-30] Parser now treats transaction-like rows as retainable phase-aware detail lines
- **What changed:** Hardened the parser so any `TX mm/dd/yy` row becomes a record boundary, signed numeric tail columns are parsed for generic detail lines, and phase-code mappings now participate directly in raw-family fallback.
- **Why:** Several real reports were losing or mangling valid IC/JC/AP lines because unknown transaction codes were merged or dropped, negative values broke amount parsing, and family routing depended too heavily on transaction-specific token rules.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low-to-medium risk that a non-detail line beginning with a two-letter/date pattern could now be retained, though the rule is still anchored to report-body formatting and is safer than silently losing valid accounting rows.
- **Follow-up needed:** The parser still relies on extracted text lines rather than true PDF spatial columns; if more edge cases surface, add fixture-backed column-aware extraction rather than reintroducing brittle string hacks.

### [2026-03-30] Phase-40 AP records preserve subcontractor family routing
- **What changed:** Added subcontractor family support to the phase-aware parsing and normalization path so AP records under `40 . . Subcontracted` no longer fall through to material typing.
- **Why:** The parser was preserving phase 40 context correctly, but the config-backed family-routing stack did not represent subcontracted behavior, so both raw and normalized type drifted to material.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk of changing behavior for reports that implicitly relied on phase 40 falling through to material, though that behavior was incorrect for subcontracted entries.
- **Follow-up needed:** Add fixture-backed coverage for other subcontracted AP report variants if more examples surface.

# Transition Tracker

## Purpose
This document tracks how the desktop MVP is evolving toward a future scalable product architecture.

The current application is a PySide desktop app and should continue improving as a practical, high-value tool. This tracker exists to make sure ongoing development strengthens the reusable product core instead of accidentally over-investing in desktop-only implementation details.

This is **not** a full changelog. It is a decision and migration tracker.

---

# 1) Current product status

## Current delivery model
- Packaged/downloadable desktop application
- Python-based processing pipeline
- PySide6 UI for review/edit/export workflow
- Intended to automate T&M recap generation from accounting/job cost report inputs

## Current product value
- Digests ugly real-world report output
- Normalizes records into cleaner internal representations
- Applies classification/rate/template/profile logic
- Supports user review and correction
- Exports clean Excel recap output
- Already valuable as an internal productivity tool and near-term deployable MVP

## Long-term product direction
Potential future direction:
- web-based application
- broader customer applicability
- multi-profile / multi-company support
- guided onboarding and setup
- predictive mapping
- template and export management
- stronger admin/configuration workflows

---

# 2) Product layers

## A. Core reusable product engine
These areas should increasingly become platform-independent and portable:
- parsing
- normalization
- validation
- mapping logic
- profile/config interpretation
- export transformation logic
- core record/workflow models
- onboarding logic design
- predictive mapping foundations
- domain-level bulk edit behavior

## B. Application/service layer
These coordinate the workflow and may later be adapted to a web backend:
- import/open flow
- profile loading
- pipeline orchestration
- applying edits/overrides
- recalculation logic
- export requests

## C. Desktop delivery layer
These are useful now but are less reusable later:
- PySide windows
- dialogs
- widget-specific state management
- desktop navigation patterns
- local file selection UX
- widget-specific table behaviors

---

# 3) Strategic rule for ongoing work
During desktop development, prefer work that improves at least one of the following:

- correctness
- test coverage
- portability
- maintainability
- configurability
- consistency

Be cautious about spending large effort on purely desktop-specific polish unless it unlocks clear user value right now.

---

# 4) Core areas to harden before major web migration

## Parsing logic
**Status:** In progress  
**Goal:** Improve resilience against real-world report variation and edge cases while keeping behavior testable and explainable.

### Desired end state
- robust parsing across known input variations
- fixture-backed regression coverage
- minimal reliance on brittle one-off assumptions
- clear separation between extraction and normalization

### Open considerations
- Are any parsing rules still too customer-specific?
- Are ambiguous cases clearly surfaced rather than silently guessed?
- Are low-confidence outcomes represented consistently?

---

## Normalization and mapping abstractions
**Status:** In progress  
**Goal:** Ensure normalization behavior is data-driven, extensible, and increasingly profile-based.

### Desired end state
- raw-first mapping approach where appropriate
- cleaner abstractions for labor/equipment/material normalization
- customer-specific behavior moved into configuration where possible
- future predictive mapping can build on stable normalized concepts

### Open considerations
- Which normalization rules are still too implicit in code?
- Are mappings auditable and easy to reason about?
- Are canonical terms consistent across code, config, and UI?

---

## Validation behavior
**Status:** In progress  
**Goal:** Maintain trustworthy blocker/warning behavior that supports reliable review and export.

### Desired end state
- clear distinction between blockers and warnings
- validation rules aligned with export readiness
- predictable revalidation after edits
- edge-case coverage in tests

### Open considerations
- Are validation rules tied too tightly to UI assumptions?
- Are all export-critical failure modes captured?

---

## Profiles / classifications / rates / templates
**Status:** In progress  
**Goal:** Move toward a cleaner configurable product that can support many use cases without code changes.

### Desired end state
- portable profile abstractions
- consistent terminology
- editable classifications/rates/templates with clear source of truth
- future onboarding can output these structures reliably

### Open considerations
- Which config concepts are reusable vs company-specific?
- What belongs in profile data vs app settings vs export template definitions?

---

## Export model
**Status:** In progress  
**Goal:** Keep export behavior reliable while moving toward a data-driven export architecture.

### Desired end state
- export logic driven by stable recap/export models
- minimal coupling between export behavior and UI behavior
- future visual export editor can sit on top of stable data contracts
- template capacity/validation clearly defined

### Open considerations
- What parts of export behavior are still too template-specific in code?
- What abstractions are needed for future export editor/creator support?

---

## Tests / fixtures / edge-case coverage
**Status:** In progress  
**Goal:** Use tests as the main defense against regressions during product hardening and future migration.

### Desired end state
- parser fixtures for representative inputs
- normalization regression tests
- validation tests
- export mapping/export behavior tests
- bug-fix regression tests

### Open considerations
- Which critical flows still depend on manual confidence rather than automated tests?
- Which edge cases need representative fixtures?

---

# 5) Migration readiness buckets

## Ready or becoming ready for future web reuse
Use this section to list items that are increasingly portable.

- [ ] Parsing logic has stable interfaces and fixture-backed tests
- [ ] Normalization logic is mostly profile/config driven
- [ ] Validation rules are independent of UI widgets
- [ ] Export generation is driven by stable internal models
- [ ] Bulk edit behavior is defined at the domain/workflow level
- [ ] Onboarding outputs are expressed as structured configs/data
- [ ] Predictive mapping is modeled as a service/domain capability, not a UI trick
- [ ] Terminology is consistent across code, config, and UI
- [ ] Application services have clean boundaries from PySide widgets

---

## Still desktop-coupled
Use this section to record areas that are still tightly tied to the desktop delivery model.

- [ ] UI state lives too close to core workflow logic
- [ ] Local file path assumptions remain in workflow code
- [ ] Desktop dialogs or widgets trigger business logic directly
- [ ] Certain editing/review concepts only exist in widget-specific form
- [ ] Settings/profile flows are too tied to local desktop assumptions

### Notes
- Review pipeline orchestration now lives in `services/review_workflow_service`, while Qt signals, selection state, and filtering remain in desktop view-model code for the current migration slice.
- Settings/profile/options/observed-value orchestration now lives in `services/settings_workflow_service`, while dialogs, widget tables, and other Settings screen mechanics remain in the desktop shell.
- Add concise notes here as needed when a change increases or reduces desktop coupling.

---

## Deferred until web model
Use this section for features or decisions that should not be overbuilt in the desktop app.

- [ ] Multi-user collaboration
- [ ] organization/workspace model
- [ ] centralized hosted profile management
- [ ] cloud file storage
- [ ] async/background processing job system
- [ ] subscription/billing/admin model
- [ ] audit history beyond local desktop needs
- [ ] customer-facing onboarding portal
- [ ] large-scale template library sharing

### Notes
- Add concise notes here when a feature is intentionally postponed because it belongs in the web product.

---

# 6) Architecture decisions
Record important decisions briefly. Add newest items at the top.

### [2026-04-05] Phase-1 parity is now enforced through a semantic acceptance harness that compares desktop and accepted web paths
- **Decision:** Added a parity-harness layer under `tests/` that treats the current desktop/core workflow as the reference path, drives the web path through the accepted FastAPI API flow, compares record/order/blocker/edit/export semantics instead of UI state or raw XLSX bytes, and anchors that comparison to a reusable acceptance corpus structure.
- **Reason:** `prd.md` step 8 requires a signoff gate that fails on meaningful business-result drift while ignoring generated ids, timestamps, storage keys, and workbook container noise; `AGENTS.md` also keeps desktop as the fallback until that corpus passes.
- **Impact on desktop MVP:** Desktop behavior is unchanged; the harness only formalizes it as the acceptance reference.
- **Impact on future web product:** Improves parity readiness by creating the first reusable semantic signoff mechanism for desktop-versus-web comparison without weakening the comparison to coarse aggregates.
- **Follow-up:** Expand the corpus from the initial representative case to real customer reports, trusted profiles, scripted edits, and expected workbook semantics before using the harness for pilot or cutover decisions.

### [2026-04-05] Phase-1 web profile usability uses a read-only trusted-profile listing seam, not browser-side profile entry or management
- **Decision:** Added a minimal read-only trusted-profile service and API route that expose the available phase-1 profiles for selection/inspection, and updated the browser workflow to pick from that list instead of accepting a freeform profile name.
- **Reason:** `prd.md` requires web v1 to use trusted profiles correctly, but broader profile editing/import/admin work remains deferred; this closes the pilot usability gap without expanding into profile management.
- **Impact on desktop MVP:** Desktop profile behavior is unchanged; the new route is additive and reuses the existing profile bundle discovery model.
- **Impact on future web product:** Improves portability by giving the browser a stable profile-selection seam while keeping profile resolution and processing rules in the backend/service layer.
- **Follow-up:** If parity-pilot users need richer profile context later, add only narrow read-only detail fields or listing filters before considering any profile-management expansion.

### [2026-04-05] Phase-1 browser delivery stays a thin React shell over the accepted FastAPI workflow
- **Decision:** Added a minimal standalone React/TypeScript browser shell that talks only to the accepted upload, run, review-session, edit, export, and download endpoints, with a tiny fetch client and simple workflow panels instead of re-implementing lineage, blocker, or export-readiness rules in the browser.
- **Reason:** `prd.md` step 7 explicitly asks for the thinnest browser workflow on top of the accepted API surface, while `AGENTS.md` requires `core/` and the existing service layer to remain the source of truth and desktop to stay the fallback.
- **Impact on desktop MVP:** Desktop behavior is unchanged; the browser workflow is additive and uses the already accepted backend/service contracts.
- **Impact on future web product:** Improves portability by proving the immutable-run and append-only review flow can be exercised end to end from a browser without coupling UI state to PySide or mutable active-profile behavior.
- **Follow-up:** Keep browser state thin, add no client-side workflow rewrites, and defer richer profile/admin UX until after parity-harness work.

### [2026-04-05] Phase-1 HTTP delivery is a thin FastAPI layer over the existing immutable-run and review-session services
- **Decision:** Added the first FastAPI backend slice as thin route adapters over the accepted upload, processing-run, review-session, and export services, with explicit API schemas and small response/error-mapping helpers rather than re-implementing workflow logic in HTTP handlers.
- **Reason:** `prd.md` step 6 explicitly starts the HTTP API only after immutable run/session/export lineage is in place, and `AGENTS.md` requires the current service layer to remain the source of truth while desktop stays the fallback.
- **Impact on desktop MVP:** Desktop behavior is unchanged; the new backend is additive and uses the same parsing, normalization, validation, review, and export services underneath.
- **Impact on future web product:** Improves portability by exposing the accepted immutable-run and append-only review workflow through explicit contracts that future browser work can consume without coupling to PySide or mutable desktop state.
- **Follow-up:** Keep the route layer thin as browser work begins, and add broader auth/org concerns only when the minimal browser workflow actually needs them.

### [2026-04-05] Historical export now resolves workbook content from immutable template artifacts instead of the trusted-profile folder
- **Decision:** Added a minimal immutable `TemplateArtifact` seam, persisted exact template workbook bytes by content hash during run snapshot resolution, linked `ProfileSnapshot` and `ExportArtifact` lineage to that artifact, and changed exact-revision export to materialize workbook bytes from persisted lineage rather than from whichever file currently exists on disk for the trusted profile.
- **Reason:** The prior export-from-lineage path still depended on a mutable workbook file in the trusted-profile bundle, which meant a later template replacement could change or block historical exports for an older run.
- **Impact on desktop MVP:** The current trusted-profile/template workflow and workbook export behavior remain the same for day-to-day desktop use; the change only hardens lineage so historical exports replay from captured template content.
- **Impact on future web product:** Improves portability and parity readiness by making historical export reproducibility independent of local mutable files, which is a prerequisite for later API-backed run/export retrieval.
- **Follow-up:** The current artifact storage is intentionally phase-1 minimal and SQLite-backed; later production persistence should move template/export artifact bytes behind a storage adapter without changing the lineage contract.

### [2026-04-05] Review sessions now persist append-only overlays, and export replays one exact revision against the run snapshot
- **Decision:** Added a non-Qt review-session service that reopens one primary `ReviewSession` per `ProcessingRun`, stores user edits only as append-only `ReviewedRecordEdit` overlays keyed by run-scoped `record_key`, rebuilds effective records by replaying those overlays onto immutable `RunRecord`s, and requires export generation to target one explicit `session_revision`.
- **Reason:** `prd.md` sequences review-session overlays and export-from-specific-revision immediately after processing-run persistence, and `AGENTS.md` requires edits to remain non-destructive while exports stay bound to exact run/session lineage.
- **Impact on desktop MVP:** Desktop parsing/normalization/validation behavior is unchanged; this adds a persistence-ready service boundary beneath the current review/export workflow without moving any Qt dialogs, signals, or widget behavior.
- **Impact on future web product:** Improves reuse by giving later API work a tested application-service path for reopen/resume review state, exact revision replay, and export lineage that does not depend on mutable UI state.
- **Follow-up:** Persist template workbooks as first-class artifacts in a later slice so historical exports can be regenerated even if a trusted profile bundle no longer contains the original workbook bytes.

### [2026-04-05] Processing runs now inject an explicit profile-config context instead of relying on the active desktop profile
- **Decision:** Tightened the review-processing seam so processing-run creation passes an explicit selected profile bundle context into parse/normalize/default-omit/validate work, while lower `ConfigLoader()` calls temporarily bind to that injected context through a narrow runtime override rather than silently falling back to whichever profile is globally active in desktop settings.
- **Reason:** The prior run-creation path could snapshot one trusted profile but produce `RunRecord`s from a different active profile, which violated the lineage rule that each `ProcessingRun` must capture the exact selected bundle actually used.
- **Impact on desktop MVP:** Desktop behavior stays the same for normal active-profile review, but the service boundary is now explicit enough to support trusted-profile processing outside the UI shell without leaking desktop state.
- **Impact on future web product:** Improves reuse and parity readiness by making processing services deterministic for selected trusted profiles and by reducing hidden dependence on global single-user profile state.
- **Follow-up:** Reuse the same explicit profile-config context pattern for later export-from-lineage services so run/session/export behavior stays aligned to one exact selected bundle.

### [2026-04-05] Processing-run creation now reloads the selected trusted profile bundle into immutable lineage
- **Decision:** Added a plain Python processing-run service plus a minimal SQLite lineage store that resolve the selected trusted profile from the caller's profile roots at process start, canonicalize the effective bundle into a reusable `ProfileSnapshot`, and persist each processing invocation as a new immutable `ProcessingRun` with ordered `RunRecord`s and run-scoped `record_key`s.
- **Reason:** `prd.md` sequences trusted-profile snapshot resolution and processing-run persistence immediately after the lineage contract, and `AGENTS.md` requires reruns with changed settings to create new immutable lineage instead of mutating older runs.
- **Impact on desktop MVP:** Desktop parsing, normalization, validation, and review behavior are unchanged; this adds a persistence-ready service seam underneath the existing workflow without introducing routes, background work, or UI changes.
- **Impact on future web product:** Improves reuse by giving later API work a tested application-service path for trusted-profile resolution, fixed run creation, and immutable run-record storage.
- **Follow-up:** Build review-session persistence and export-from-specific-revision services on top of this store next, still without jumping ahead into broad HTTP or frontend scaffolding.

### [2026-04-05] Phase-1 lineage is defined as immutable runs plus append-only review revisions
- **Decision:** Added portable lineage models for `Organization`, `User`, `TrustedProfile`, `ProfileSnapshot`, `SourceDocument`, `ProcessingRun`, `RunRecord`, `ReviewSession`, `ReviewedRecordEdit`, and `ExportArtifact`, plus a phase-1 persistence schema contract and pure helpers for canonical snapshot hashing, run-scoped `record_key` assignment, append-only `session_revision` progression, and export-from-exact-revision lineage.
- **Reason:** `prd.md` explicitly sequences lineage/persistence definition before any API work, and `AGENTS.md` requires immutability and review-session lineage rules to be locked down before migration expands into web delivery.
- **Impact on desktop MVP:** Desktop behavior is unchanged; this work defines the persistence contract underneath the current app without introducing database runtime behavior or web scaffolding.
- **Impact on future web product:** Improves reuse by giving later profile snapshot resolution, run persistence, review overlay storage, and export lineage API work a tested contract instead of ad hoc assumptions.
- **Follow-up:** The next persistence slice can build trusted-profile snapshot resolution and processing-run creation on top of this contract, but should still avoid broad API/frontend work until those services are in place.

### [2026-04-05] Settings/profile administration now sits behind a plain Python workflow service
- **Decision:** Profile discovery, active-profile switching, config-table reload shaping, default-omit/rate/mapping/classification saves, cache clearing, and observed-value merging/persistence now live in `services/settings_workflow_service`, while `SettingsViewModel` retains only Qt signal emission and desktop-facing property/method forwarding.
- **Reason:** `prd.md`, `AGENTS.md`, and the migration-execution-tracker workflow all call for extracting remaining non-Qt settings/profile orchestration out of `SettingsViewModel` before any persistence/API/web phases begin.
- **Impact on desktop MVP:** The desktop Settings/Admin dialog keeps the same behavior, but its workflow logic is now reusable and testable without PySide.
- **Impact on future web product:** Improves reuse by creating a non-Qt service seam for trusted-profile selection, read-only inspection, observed mapping suggestions, and profile-backed option shaping.
- **Follow-up:** Keep desktop dialogs/widgets thin, and only move later to lineage/persistence design after both review and settings workflow services are stable and covered.

### [2026-04-05] Review workflow orchestration now sits behind a plain Python service boundary
- **Decision:** The parse -> normalize -> default-omit -> validate review load path, record-update revalidation path, status-text shaping, and edit-option loading now live in `services/review_workflow_service`, while `ReviewViewModel` retains only Qt-facing state, signals, filtering, and selection behavior.
- **Reason:** This is the first approved migration slice from `prd.md` and `AGENTS.md`: move workflow orchestration and business-state shaping out of Qt before persistence/API/web work, and protect parity with non-Qt tests.
- **Impact on desktop MVP:** Desktop behavior stays the same, but the review screen now depends on a reusable service instead of owning the workflow directly.
- **Impact on future web product:** Improves reuse by giving future API/web entry points a review-workflow service seam that is already covered outside PySide.
- **Follow-up:** Continue the same pattern for observed-value persistence and `SettingsViewModel` orchestration so profile/admin workflow logic also moves below the desktop shell.

### [2026-04-01] Default omission stays a review-state policy driven by canonical phase codes
- **Decision:** Default omit rules are stored in profile config, matched through one shared phase-code canonicalization helper, and applied only when building the review dataset by setting the existing `is_omitted` flag.
- **Reason:** This keeps records preserved and manually reversible, avoids hard-coded billing policy in parser/normalizer/export logic, and gives settings/UI a clean config-backed surface.
- **Impact on desktop MVP:** Users can manage default-omitted phases in Settings without editing JSON by hand, while reprocess still rebuilds from parser + normalization + profile defaults.
- **Impact on future web product:** Improves reuse by centralizing phase-code identity and keeping omission policy in profile/workflow config rather than in desktop widgets.
- **Follow-up:** If users need broader phase pick-lists later, add an optional profile phase catalog instead of making ad hoc spreadsheets a runtime dependency.

### [2026-04-01] Company-wide phase reference data lives outside profile-specific omit policy
- **Decision:** Shared phase codes and names are loaded from one app-wide phase catalog, while `review_rules.json` remains profile-scoped behavior that stores canonical phase-code rules only.
- **Reason:** Phase identity is reference data for the whole company, but omission defaults are profile-level workflow policy; keeping them separate avoids mixing company-wide lookup data into per-profile config or relying on currently observed PDFs.
- **Impact on desktop MVP:** Users can edit omitted-by-default phases from a complete named pick-list before any report is loaded, while profiles still control which phases start omitted.
- **Impact on future web product:** Improves reuse by cleanly separating shared reference data from profile behavior, which maps better to future admin/config services.
- **Follow-up:** If users need to maintain the company-wide phase list in-app later, add a small shared catalog admin path rather than duplicating the list into each profile.

### [2026-04-02] Project management is modeled as a first-class non-list recap family
- **Decision:** Phase `25 . . Labor-Project Mgmt` is represented as a dedicated `project_management` family that validates/exports as a summary-only cost, rather than being forced into labor, material, or unresolved `other` behavior.
- **Reason:** PM allocation lines carry real recap cost but do not fit the labor-class, vendor, or equipment-slot contracts used by other families; treating them as a real family keeps parsing/normalization honest and gives export a clean place to sum them.
- **Impact on desktop MVP:** Users can review and export PM allocation records without omitting them, and recap workbooks now show Project Management totals directly in the summary area.
- **Impact on future web product:** Improves reuse by extending the core family model and export payload contract instead of hiding PM behavior in desktop UI corrections or export-only exceptions.
- **Follow-up:** If additional summary-only families are confirmed later, extract a small config-driven summary-total abstraction instead of proliferating hard-coded summary rows.

## Template
### [YYYY-MM-DD] Decision title
- **Decision:**  
- **Reason:**  
- **Impact on desktop MVP:**  
- **Impact on future web product:**  
- **Follow-up:**  

---

# 7) Recent meaningful changes

### [2026-04-05] A semantic desktop-versus-web parity harness now exists with the first reusable acceptance-corpus case
- **What changed:** Added a parity harness under `tests/parity_harness/` plus a stable corpus layout under `tests/parity_corpus/`, including a representative material-vendor-resolution case with a source-report fixture, trusted-profile bundle seed, scripted review edits keyed by `record_key`, expected review semantics, and expected workbook-cell/style semantics. The harness now runs the desktop reference path through the core/services layer, the web path through the accepted FastAPI API, and fails on mismatched records, blockers, correction outcomes, or semantic workbook results.
- **Why:** `prd.md` step 8 requires a conservative acceptance gate before any pilot/cutover thinking, and `AGENTS.md` keeps desktop as the fallback until semantic parity against the corpus is demonstrated.
- **Area:** Tests / Application services / Web delivery
- **Portability impact:** Increased
- **Risks introduced:** Low risk that the corpus is still intentionally small and the initial representative case uses a deterministic parser fixture to focus first on workflow/export parity rather than broad real-PDF coverage.
- **Follow-up needed:** Before pilot/fallback decision-making, expand the acceptance corpus to real customer report/profile combinations and keep expected workbook semantics curated as the signoff source of truth.

### [2026-04-05] Web workflow now uses a read-only trusted-profile picker instead of freeform profile-name entry
- **What changed:** Added a small read-only trusted-profile service plus `GET /api/trusted-profiles`, returned stable phase-1 selection metadata from existing profile bundles, updated the browser upload flow to load/select/inspect trusted profiles from that API, and added backend/browser tests proving the selected picker value drives processing-run creation.
- **Why:** The minimal browser shell still relied on a temporary freeform profile-name input, which left a gap against the PRD’s mandatory web v1 trusted-profile behavior even though broader profile management remains deferred.
- **Area:** Application services / Web delivery / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that profile inspection is intentionally summary-level only, because phase 1 still avoids browser-native profile editing, import/export UI, and broader admin expansion.
- **Follow-up needed:** The main remaining blocker before parity-harness work is no longer profile selection; the next step can stay focused on the acceptance corpus and semantic parity checks rather than on more browser-side profile UX.

### [2026-04-05] A minimal browser workflow now exercises the accepted phase-1 API end to end
- **What changed:** Added a standalone `web/` React/TypeScript shell with a tiny API client, sequential panels for upload/run/review/export, Vite-based local build tooling, and a focused frontend workflow test that mocks the accepted API surface through upload, immutable run inspection, review edit submission, exact-revision export, and artifact download.
- **Why:** `prd.md` step 7 calls for the thinnest browser workflow on top of the accepted FastAPI API, and `AGENTS.md` requires browser delivery to stay thin while preserving the backend/service lineage rules and keeping desktop as the fallback.
- **Area:** Web delivery / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that trusted-profile choice is still a conservative name entry rather than a richer browser-side picker, because broader profile/admin UX remains deferred in phase 1.
- **Follow-up needed:** Before parity-harness work, decide whether the browser needs a tiny read-only trusted-profile listing endpoint or whether the current conservative profile-name input remains sufficient for the pilot workflow.

### [2026-04-05] A minimal FastAPI backend now exposes phase-1 upload, run, review-session, and export endpoints
- **What changed:** Added a new `api/` package with a FastAPI app factory, thin route modules for source upload, run creation/retrieval, review-session open/edit, and exact-revision export/download, plus explicit request/response schemas and small serializer/error helpers. Added local runtime file storage for uploaded PDFs/exported workbooks and API tests covering upload, processing-run creation, immutable run retrieval, review-session open, append-only edit revisioning, exact-revision export, and artifact download.
- **Why:** The approved migration sequence in `prd.md` reaches step 6 only after the service and lineage rules are accepted, so the next conservative move is a narrow HTTP API around those existing services without starting frontend or worker infrastructure.
- **Area:** Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that the current FastAPI slice still uses the phase-1 SQLite store and a local runtime file store, including a small `check_same_thread=False` compatibility shim for sync route execution in FastAPI's worker threads.
- **Follow-up needed:** Before the minimal browser workflow starts, keep the route layer thin and decide whether API startup/config should graduate from the current in-code defaults into a small environment/settings module.

### [2026-04-05] Historical exports now replay from persisted template artifacts rather than mutable on-disk workbooks
- **What changed:** Added an immutable `TemplateArtifact` lineage model plus SQLite persistence for exact workbook bytes, linked snapshots and export artifacts to that template artifact, persisted template content during processing-run creation, and updated review-session export to materialize the historical workbook from stored artifact bytes instead of the trusted-profile directory. Added regressions proving that replacing the on-disk workbook after a run does not change historical export output and that exports still stay tied to one exact revision and template lineage.
- **Why:** The previous review-session export seam still relied on the current trusted-profile workbook file, so historical exports were not fully reproducible if that file changed after the run was created.
- **Area:** Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that template artifacts are currently stored directly in the phase-1 SQLite store, so later production persistence still needs a storage abstraction pass rather than assuming database-embedded blobs remain the final deployment model.
- **Follow-up needed:** Keep the lineage contract stable, but introduce a dedicated artifact-storage adapter before broader API work depends on larger binary payloads or non-SQLite backends.

### [2026-04-05] Review-session overlays and exact-revision export now sit behind a plain Python lineage service
- **What changed:** Added `services/review_session_service.py` plus SQLite store support for `ReviewSession`, `ReviewedRecordEdit`, and `ExportArtifact`; review edits are now persisted as append-only overlays and replayed onto immutable `RunRecord`s when sessions reopen; export now accepts an explicit config context and generates workbooks from one requested `session_revision` only; and new service tests lock overlay immutability, latest-revision reopen behavior, and exact revision export lineage.
- **Why:** The next approved slice in `prd.md` is to implement review-session overlay persistence and export generation from an exact revision on top of existing processing-run lineage, while `AGENTS.md` requires append-only edit behavior and exact export binding to stay explicit before any API or UI buildout.
- **Area:** Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that exact historical export currently verifies the trusted-profile template hash and fails closed if the original workbook has drifted, because template bytes are not yet persisted as first-class lineage artifacts.
- **Follow-up needed:** In a later persistence slice, capture template workbooks as durable artifacts so historical exports can be regenerated without depending on the trusted profile bundle still being present on disk.

### [2026-04-05] Processing-run lineage no longer drifts to the active desktop profile, and snapshot reuse is now behavior-only
- **What changed:** Refactored review processing so `ProcessingRunService` injects the selected profile bundle context into the review pipeline, added explicit config-context binding in `ConfigLoader` for lower parsing/normalization helpers, tightened snapshot hashing to behavioral inputs only while moving selected trusted-profile identity onto `ProcessingRun`, and added regressions for non-active profile processing, metadata-insensitive snapshot reuse, and behaviorally relevant config changes creating a new snapshot/run.
- **Why:** A lineage-integrity review found that run creation could snapshot one trusted profile while `RunRecord`s were still produced from the globally active desktop profile, and that non-behavioral profile metadata could block valid snapshot reuse.
- **Area:** Core engine / Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that the new explicit config-context override depends on careful cache clearing around config-sensitive helpers, though the regression suite now exercises the critical non-active-profile path directly.
- **Follow-up needed:** Keep later export/session lineage work on the same explicit selected-profile seam so no later service reintroduces active-profile drift.

### [2026-04-05] Trusted-profile snapshot resolution and immutable processing-run persistence now sit behind a non-Qt service
- **What changed:** Added `services/processing_run_service.py` and `infrastructure/persistence/sqlite_lineage_store.py` to resolve trusted-profile bundles from the selected profile roots, reuse immutable `ProfileSnapshot`s by content hash, create new `ProcessingRun`s for each processing invocation, persist ordered `RunRecord`s with run-scoped `record_key`s, and added service-focused regression tests covering unchanged-bundle snapshot reuse plus changed-settings rerun lineage.
- **Why:** The next approved slice in `prd.md` is to implement trusted-profile snapshot resolution and processing-run persistence on top of the lineage contract before any HTTP/API or web-shell work begins, while `AGENTS.md` requires old runs to stay fixed when settings change.
- **Area:** Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that the current store is intentionally SQLite-only and phase-1 minimal, so later production database wiring still needs an adapter pass instead of assuming this exact implementation survives unchanged.
- **Follow-up needed:** Add review-session overlay persistence and export-artifact generation on top of the same lineage store, then keep broader API delivery deferred until those rules are fully covered.

### [2026-04-05] Phase-1 lineage models and persistence schema were defined before API work
- **What changed:** Added portable lineage dataclasses under `core/models/lineage.py`, pure lineage helpers in `services/lineage_service.py`, an initial SQL persistence schema contract under `infrastructure/persistence/phase1_lineage_schema.sql`, and regression tests covering immutable profile snapshots, deterministic run-scoped `record_key`s, append-only `session_revision` behavior, exact export revision lineage, and key schema constraints.
- **Why:** The approved migration sequence in `prd.md` calls for defining immutable run/session/export lineage and persistence schema before any API buildout, and `AGENTS.md` requires those rules to stay explicit and test-protected.
- **Area:** Core engine / Application services / Persistence/API prep / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that the current SQL contract is intentionally minimal and runtime-agnostic, so later concrete database implementation still needs careful translation if storage-specific features are introduced.
- **Follow-up needed:** Build trusted-profile snapshot resolution and processing-run persistence services on top of this contract, then delay HTTP/API work until those services are stable.

### [2026-04-05] Settings/profile/options workflow moved out of `SettingsViewModel` into a non-Qt service
- **What changed:** Added `services/settings_workflow_service.py` for profile discovery/switching, active-profile summary shaping, default-omit/mapping/classification/rate save orchestration, cache clearing, and observed-value merge/persistence behavior; rewired `SettingsViewModel` into a thin Qt adapter; moved review observed-value persistence imports to the service layer; and added service-focused regression tests.
- **Why:** This is the next conservative migration slice after review-service extraction: finish pulling remaining non-Qt settings/profile/options/observed-value orchestration out of PySide while keeping dialogs and widget behavior in the desktop shell.
- **Area:** Application services / Desktop UI / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that some helper functions are still shared through the desktop module surface for compatibility during the transition, though the workflow logic itself now lives below the UI layer.
- **Follow-up needed:** Decide whether any helper re-exports should be cleaned up after the new service seam settles, then move to the next approved slice only after staying within the PRD sequence.

### [2026-04-05] Review workflow orchestration moved out of `ReviewViewModel` into a non-Qt service
- **What changed:** Added `services/review_workflow_service.py` for review-load orchestration, record-update revalidation, status-text shaping, and edit-option loading; rewired `ReviewViewModel` to delegate to that service; and added non-Qt service tests plus seam-preserving view-model test updates.
- **Why:** The approved migration slice says to extract plain Python application services from `ReviewViewModel` before later persistence/API/web phases, while proving desktop behavior is preserved with service-level tests.
- **Area:** Application services / Desktop UI / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that some review concerns are still split across the service and view model until observed-value persistence and more settings orchestration are extracted in later slices.
- **Follow-up needed:** Apply the same extraction pattern to `SettingsViewModel` and decide whether observed-value persistence belongs in a shared profile/application service rather than desktop view-model code.

### [2026-04-04] Legacy mapping-shape compatibility was removed in favor of raw-first configs only
- **What changed:** Removed runtime/settings compatibility handling for equipment `keyword_mappings` and old labor mapping keys (`phase_defaults`, `aliases`, `class_mappings`, `apprentice_aliases`), updated shipped config JSON to modern raw-first shapes, and converted compatibility-only tests to raw-first coverage.
- **Why:** Raw mappings and slot-based classification handling are now the authoritative model, so keeping old config-shape support in loader/settings/tests was extra baggage that no longer reflected intended product behavior.
- **Area:** Core engine / Application services / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk for current supported profiles because the bundled/default configs now use the modern shape; externally maintained legacy config files may need migration instead of relying on silent compatibility handling.
- **Follow-up needed:** If external users still rely on old config files, provide a one-time migration script or documented conversion path rather than reintroducing dual-shape runtime support.

### [2026-04-04] Export no longer reroutes permit-family records into police detail by description text
- **What changed:** Removed the export-layer fallback that sent `permit` records to the police-detail section when their raw description contained the word `police`, and added a regression proving permit-family records now stay in the permits section regardless of description text.
- **Why:** Permits and police detail are now distinct families with separate upstream routing, so description-based rerouting in export had become a stale workaround that conflicted with the intended product model.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk; correctly routed police-detail records still export through their own family path, while misclassified permit records are no longer silently rewritten at the export layer.
- **Follow-up needed:** If a real report still reaches export with a police-detail charge mislabeled as `permit`, fix that upstream in parsing/normalization/profile mapping rather than reintroducing text-based export rerouting.

### [2026-04-04] Pass 3 removed dead configured transaction-marker scaffolding
- **What changed:** Removed the unused `_get_transaction_types` parser cache helper, stopped clearing that dead cache in settings, dropped the obsolete `transaction_types` key from the bundled `input_model.json` files, and added a parser regression proving generic `TX mm/dd/yy` record starts still emit records without a configured marker list.
- **Why:** Transaction-boundary detection is already marker-agnostic at runtime, so the old helper and bundled config key were stale compatibility residue rather than active behavior.
- **Area:** Core engine / Application services / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk; loader tolerance for older configs remains intact, and the new regression keeps the intended marker-agnostic parser contract explicit.
- **Follow-up needed:** Leave broader legacy config compatibility paths in place until their removal is backed by an explicit product decision rather than inferred from unused-looking fields.

### [2026-04-04] Pass 2 dropped the obsolete list-order classification rename helper
- **What changed:** Removed the unused `_build_label_rename_map` helper and updated the remaining rename-coverage test to exercise the slot-id-based rename map that the settings workflow actually uses at runtime.
- **Why:** Classification rename propagation is now intentionally anchored to stable slot identities, so the older list-order diff helper was preserving a superseded compatibility model rather than a real product path.
- **Area:** Application services / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk; this narrows cleanup to a production-dead helper and keeps coverage on the authoritative slot-based rename contract.
- **Follow-up needed:** Decide separately whether any other legacy config compatibility surfaces should be formally deprecated before removing their tests or loader support.

### [2026-04-04] Pass 1 cleanup removed only high-confidence dead helpers and debug scaffolding
- **What changed:** Removed a small set of definitely unused helpers from infrastructure/config/view-model/UI/model code, deleted two hard-coded PM export trace scripts under `debug/`, and dropped the unused `recent_output_path` setting key from app settings.
- **Why:** This trims stale MVP hardening residue without changing parser, normalization, validation, export, or profile behavior, which makes future cleanup and agent work less noisy.
- **Area:** Core engine / Application services / Desktop UI / Config
- **Portability impact:** Increased
- **Risks introduced:** Low risk; one direct regression from the cleanup was caught and fixed during the verification pass, and the full automated suite remained green.
- **Follow-up needed:** Keep later cleanup passes limited to separately reviewed medium-confidence compatibility paths instead of broadening this safe deletion pass.

### [2026-04-01] Default-omit settings now use shared phase-code canonicalization
- **What changed:** Added a shared `phase_codes` helper used by parser header extraction, phase-mapping config loading, normalization fallback, review default-omit matching, and the new lightweight Settings tab for editing `review_rules.json` default omit phase rules.
- **Why:** Dotted phase variants such as `29 .999.` and `13 .25 .` need one canonical representation so profile-driven omission stays reliable and users can manage omitted-by-default phases without hard-coded policy logic.
- **Area:** Core engine / Application services / Desktop UI / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that some phase choices in Settings may still need manual entry if they are not present in the current profile config or observed review dataset, though the editor now supports that safely through canonicalized phase codes.
- **Follow-up needed:** Consider an optional profile-backed phase catalog later if users need a fuller preloaded phase pick-list than observed/configured phases provide today.

### [2026-04-01] Default-omit settings now source phases from a shared master catalog
- **What changed:** Added a shared `phase_catalog.json` reference config and updated the Default Omit settings editor to source canonical phase codes and names from that catalog before merging saved rules or observed report phases.
- **Why:** Phase codes and names are company-wide reference data, while default omission remains profile-specific policy, so the settings pick-list needed to stop depending on per-profile phase mappings or currently loaded PDFs.
- **Area:** Core engine / Application services / Desktop UI / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that the shared catalog can drift from company practice if not maintained, though the UI still preserves saved or observed codes as safe fallbacks.
- **Follow-up needed:** If phase reference data eventually needs admin editing, add a dedicated shared catalog editor rather than pushing company-wide phase lists into profile bundles.

### [2026-04-02] Labor normalization now falls back to raw description when class parsing misses
- **What changed:** Labor normalization now uses the parsed `raw_description` as a fallback labor mapping source when a record is already recognized as labor but no structured `labor_class_raw` was extracted, so review/mapping can still proceed without changing the record family.
- **Why:** Rare PR labor variants such as phase-21 multi-trade lines were preserving hours and cost correctly but left labor mapping blank because labor-class parsing only covered the more common prefixed class shapes.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that unusual labor lines now map by a longer raw fallback key, though the original parse warning remains and the behavior is still raw-first and user-reviewable.
- **Follow-up needed:** If more payroll variants surface later, consider expanding structured labor-class extraction patterns without removing the raw-description fallback path.

### [2026-04-02] Review display now separates fallback labor mapping source from effective recap class
- **What changed:** Added an explicit effective labor-class display contract so fallback raw labor mapping sources no longer show up as the record's displayed labor class once a mapped recap labor classification exists, and the detail panel now surfaces recap labor class separately from raw/normalized trace fields.
- **Why:** The raw-description fallback made rare labor rows mappable, but review presentation was still treating that fallback source as if it were the resolved labor classification.
- **Area:** Core engine / Desktop UI / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that unmapped fallback labor rows now show a blank effective labor class until a recap class is chosen, though the raw source remains visible for traceability and mapping.
- **Follow-up needed:** If other review fields develop similar raw-vs-effective ambiguity, consider adding explicit effective-display helpers instead of letting widgets infer from raw trace fields.

## Template
### [YYYY-MM-DD] Change title
- **What changed:**  
- **Why:**  
- **Area:** Core engine / Application services / Desktop UI / Tests / Config  
- **Portability impact:** Increased / Neutral / Reduced  
- **Risks introduced:**  
- **Follow-up needed:**  

### [2026-03-29] Parser preserves phase context for dotted phase headers
- **What changed:** Broadened phase-header recognition to accept dotted subphase formats like `29 .999. Labor-Non-Job Related Time`, so following detail lines inherit the correct active phase context.
- **Why:** A valid PR labor line under phase 29 was being assigned the prior phase 20 context because the phase 29 header format was not recognized.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk of matching an unintended line as a phase header, but the pattern still requires a leading numeric phase code and a letter-led phase name.
- **Follow-up needed:** Add fixture-backed coverage for any other observed phase-header variants if more Vista/Viewpoint reports surface them.

### [2026-03-29] Parser treats JC correction lines as global record boundaries
- **What changed:** Added global JC transaction-start recognition so consecutive JC lines flush and emit as separate parsed records instead of being concatenated.
- **Why:** Review-relevant accounting correction lines were being merged together, hiding individual positive/negative adjustments from the user.
- **Area:** Core engine / Config / Tests
- **Portability impact:** Increased
- **Risks introduced:** Low risk that older customer-specific report variants using JC in a non-transaction context could now split more aggressively, though the required `JC <date>` structure keeps the rule narrow.
- **Follow-up needed:** If JC lines need richer parsing later, add tokenizer-level handling without changing the record-boundary rule.

### [2026-03-29] Parser skips orphan header/filter lines before record emission
- **What changed:** Tightened the report parser so non-transaction lines with no structured fields are dropped instead of becoming low-confidence `other` records, and added parser regression coverage for the Vista/Viewpoint header-filter case.
- **Why:** Report metadata/filter text was leaking into review as junk records and blockers in some PDFs.
- **Area:** Core engine / Tests
- **Portability impact:** Increased
- **Risks introduced:** Very low risk of dropping unsupported orphan lines that have no transaction marker and no parseable structure.
- **Follow-up needed:** Add fixture-backed parser coverage for more report-header variants if additional customer PDFs surface them.

---

# 8) Known migration risks
Track risks that could make a future web transition harder.

## Current known risks
- Core workflow may still contain assumptions tied to local files or single-user desktop behavior.
- Some service boundaries may still be influenced by PySide-driven interaction patterns.
- Export behavior may still depend on template-specific assumptions that need more formal abstraction.
- Certain settings/profile flows may still reflect desktop storage assumptions rather than future organization-level data models.
- Predictive mapping and onboarding concepts may still be partially conceptual rather than fully modeled as reusable services.

## Risk template
### Risk
- **Description:**  
- **Severity:** Low / Medium / High  
- **Why it matters for migration:**  
- **Mitigation path:**  

---

# 9) Questions to keep asking during desktop development
Use these questions to guide future decisions.

- Does this change improve the reusable engine, or only the desktop shell?
- Are we putting business logic in the right layer?
- Is this behavior data-driven enough to support more customers later?
- Would this decision make a future web product easier or harder to build?
- Are we adding technical debt intentionally and documenting it?
- Are tests strong enough to preserve behavior during migration?
- Is this a core feature worth building now, or should it wait for the web version?

---

# 10) Near-term recommended priorities
These should be updated as priorities change.

## Current priorities
1. Fix meaningful parsing/normalization bugs that affect correctness.
2. Add regression tests for known edge cases and bug fixes.
3. Continue improving profile/config abstractions and terminology consistency.
4. Strengthen boundaries between core logic, services, and PySide UI.
5. Keep export behavior reliable while making it more data-driven.
6. Avoid unnecessary investment in desktop-only polish that does not improve the core product.
7. Continue documenting decisions that affect future portability.

---

# 11) Future web transition trigger
A serious web migration should likely begin once most of the following are true:

- [ ] Core parsing/normalization/validation behavior is stable and trusted
- [ ] Regression coverage is strong for core workflows
- [ ] Profile/config abstractions are mature enough to support broader reuse
- [ ] Export model is sufficiently data-driven
- [ ] Application services are reasonably well separated from the PySide UI
- [ ] Major desktop-only architectural uncertainty has been reduced
- [ ] The product scope is clear enough to define a realistic first web MVP

---

# 12) Notes
Use this section for short, high-value notes only.

- Keep entries concise.
- Prefer decisions and implications over narration.
- This file should help future product and architecture decisions, not become a diary.
