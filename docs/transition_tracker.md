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

## Template
### [YYYY-MM-DD] Decision title
- **Decision:**  
- **Reason:**  
- **Impact on desktop MVP:**  
- **Impact on future web product:**  
- **Follow-up:**  

---

# 7) Recent meaningful changes
This section should only include meaningful product/architecture changes, not every edit.

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