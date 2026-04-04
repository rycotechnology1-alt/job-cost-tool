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
