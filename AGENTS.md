# AGENTS.md

## Project context
This repository contains a Python application that currently delivers a working desktop recap tool through PySide6. Its purpose is to automate T&M recap creation from Vista/Viewpoint-style job cost reports.

The desktop app is not throwaway code. It is:
- a working MVP
- a valuable internal production tool
- the current production fallback during migration
- a reference implementation for the workflow and rules that define the product

At the same time, this repository is now in an active, controlled migration toward a web-based delivery model.

This repo should be treated as:

- a **reusable product engine and workflow core**
- with a **desktop delivery shell that must remain stable during migration**
- while future **web delivery layers** are introduced in controlled phases

---

## Current migration direction
The approved migration direction is:

- preserve `core/` as the product engine
- use a strangler approach
- extract non-Qt application services before rebuilding delivery interfaces
- keep the desktop app alive until web parity is accepted
- keep desktop as the production fallback until the parity corpus passes
- move in safe, reviewable slices rather than broad platform buildout
- phase 1 targets one deployed customer / one organization, not full multi-tenant SaaS
- remain organization-ready, but do not introduce unnecessary multi-tenant provisioning/billing/org-management complexity in phase 1

Unless the user explicitly asks for a later migration phase, do **not** assume broad backend/web platform implementation is in scope.

---

## Current approved implementation scope
The current default approved implementation slice is:

1. extract plain Python application services from `ReviewViewModel` and `SettingsViewModel`
2. keep workflow orchestration and business-state shaping out of Qt
3. add non-Qt application-service tests proving extracted services preserve current desktop behavior

By default, the following are **out of scope** unless the user explicitly requests them in the current task:

- PostgreSQL persistence/schema implementation
- FastAPI route buildout
- React/frontend scaffolding
- worker infrastructure / background job queue
- broad API contract implementation
- full profile/admin web tooling
- true multi-tenant behavior
- broad rewrites outside the currently approved slice

---

## Product rules that must be preserved
Meaningful development work must preserve these product realities:

- raw report fidelity and traceability matter
- if a line is confidently part of the report body, it should survive as a record unless intentionally omitted
- phase context matters heavily
- family/type separation must remain intentional
- export-only behavior must stay in export, not leak into parsing/normalization
- raw mapping source and resolved recap/export classification must stay separate
- hardened desktop behavior is the baseline that migration must preserve

---

## Primary development objective
When making changes, prioritize work that strengthens the following platform-independent product capabilities:

- parsing logic
- normalization logic
- validation logic
- profile/config abstractions
- classification/rate/template modeling
- export mapping and export generation behavior
- workflow/domain edit behavior
- application/service orchestration
- terminology consistency
- tests, fixtures, and edge-case coverage
- parity acceptance support

Avoid over-investing in desktop-only polish when the same effort could improve the reusable engine or service boundary.

---

## Architecture expectations
Prefer a clean separation between these layers:

### 1. Core domain / product engine
Reusable logic that should remain portable across delivery models:
- record models
- parsing
- normalization
- validation
- mapping logic
- export transformation logic
- profile/config interpretation
- workflow rules

### 2. Application / service layer
Orchestration logic that coordinates the workflow:
- document ingest/open
- profile resolution
- parse/normalize/validate pipeline execution
- application of edits/overrides
- recalculation of blocker/warning state
- export-readiness decisions
- export generation orchestration
- issue/blocker shaping
- options loading

### 3. Delivery / interface layer
Interface-specific concerns:
- PySide windows, dialogs, tables, panels, view-models, widget refreshes
- future HTTP/API delivery concerns
- future browser/frontend delivery concerns

Business logic should not be added directly to PySide widgets, window classes, or UI glue unless absolutely necessary. Prefer to keep interface code thin and delegate workflow logic to reusable services/domain modules.

---

## Service extraction guidance
When refactoring current desktop code, treat these as likely application/service logic candidates:

- workflow orchestration
- correction application
- validation/blocker state changes
- export readiness rules
- profile resolution
- option loading
- issue/blocker shaping

Treat these as desktop UI glue unless there is a strong reason otherwise:

- Qt signals
- widget refreshes
- row coloring
- dialogs
- screen-management behavior
- PySide-only mechanics

If logic is being moved, prefer moving it downward into reusable services/modules rather than sideways into more UI code.

---

## Parity and migration guardrails
Migration work must preserve the current business result of the desktop app.

### Phase-1 parity definition
For phase 1, parity means the web workflow must produce the same usable business result as desktop for the same input report and trusted profile. At minimum that means:

- the same surviving review records
- the same normalized family/type outcomes
- the same blockers/warnings
- the same correction results
- materially the same export workbook output

Full browser-native profile/admin parity is deferred unless a narrow subset is explicitly required for go-live.

### Fallback rule
Desktop remains the production system of record until the parity corpus passes and the user explicitly approves broader cutover.

Do not treat desktop retirement as implied.

---

## Immutability and lineage expectations
Any migration-related design or implementation must respect these rules:

- once a report is processed, that `ProcessingRun` is a fixed snapshot
- reprocessing with new logic or new settings creates a new `ProcessingRun`
- a `ReviewSession` belongs to one specific `ProcessingRun`
- edits are stored as overlays/deltas, never as destructive overwrites of run records
- every run captures the exact profile/config snapshot and engine build/version used at process time
- later profile/config changes do not affect old runs, review sessions, exports, or prior results
- rerunning with new settings creates a new run whose export reflects the new settings

Do not implement migration-related persistence, API, or review behavior in a way that violates these rules.

---

## Desktop-vs-web decision rule
When implementing a feature, bug fix, or migration step, prefer the approach that best fits this order:

1. correctness
2. maintainability
3. preservation of hardened product behavior
4. portability to the approved migration model
5. desktop-specific polish

This does **not** mean avoiding useful desktop improvements. It means desktop-specific implementation details should not contaminate core or service logic when a cleaner boundary is possible.

---

## Change strategy
Keep changes targeted, reviewable, and phase-appropriate.

Prefer:
- small focused changes
- explicit reasoning
- clear boundaries
- stable interfaces
- tests for meaningful behavior changes
- minimal blast radius
- migration slices that can be reviewed independently

Avoid:
- broad rewrites unless requested
- mixing refactor + feature + UI redesign in one step
- embedding configuration or business rules in UI code
- hard-coded assumptions that reduce portability
- using migration as an excuse to scaffold major backend/web infrastructure too early

---

## Testing expectations
For any non-trivial change, include or update tests when appropriate.

Especially protect:
- parsing behavior
- normalization behavior
- validation outcomes
- mapping behavior
- export generation behavior
- workflow-level edit behavior
- bug fixes for previously observed edge cases
- service extraction parity against current desktop behavior

If a bug is fixed, prefer adding a regression test that would have caught it.

If a behavior change is intentional, make the tests clearly reflect the intended new behavior.

When working in the current migration phase, prefer tests that prove extracted services behave the same as the existing desktop workflow.

---

## Configuration and profile expectations
This product is configuration-driven and should remain so.

Prefer:
- data-driven mappings
- profile-based behavior
- reusable abstractions
- terminology consistency across config, code, and UI
- minimizing hard-coded customer-specific assumptions

Avoid:
- baking one company’s exact workflow too deeply into core logic
- forcing future customers into current naming conventions if a cleaner abstraction is possible

During the current migration phase:
- web v1 must use trusted profiles correctly
- labor/equipment classification behavior is mandatory in v1
- browser-native profile editing/admin is deferred unless explicitly required for go-live

---

## Migration phase decision rule
Before implementing meaningful work, explicitly ask:

- Is this inside the currently approved migration slice?
- Does this preserve desktop MVP stability?
- Does this strengthen reusable engine/service behavior?
- Does this improve or preserve parity readiness?
- Does this prematurely introduce backend/web platform complexity?

If the work goes beyond the currently approved migration phase, do not assume it is allowed. Only proceed if the user explicitly requests that later phase.

---

## Required tracker workflow
This repo should maintain a living migration/design tracker at:

`docs/transition_tracker.md`

When making any meaningful change, read that file first and update it if the task changes any of the following:

- architecture
- workflow behavior
- parsing/normalization/validation behavior
- export behavior
- profile/config abstractions
- desktop coupling
- service extraction status
- migration readiness
- parity readiness
- known migration risks
- major technical debt
- deferred work
- recommended next steps

Do **not** update the tracker for trivial edits unless they affect architecture, workflow, or migration readiness.

Tracker updates should be concise and useful, not verbose.

---

## What to record in the tracker
When appropriate, update the tracker with:
- what changed
- why it changed
- whether it improved core engine quality
- whether it affected the service boundary
- whether it increased or reduced desktop coupling
- whether it improved future web portability
- whether it changed parity readiness
- any migration risks introduced
- any important follow-up work
- whether the change is considered stable, provisional, or deferred

---

## Output expectations for coding tasks
After meaningful code changes, provide a concise summary that includes:

- files changed
- why each file changed
- whether the change primarily affected:
  - core logic
  - application/services
  - desktop shell
  - persistence/API prep
  - web delivery
  - tests
  - config
- test impact
- migration impact
- any risks or follow-up items

If the tracker was updated, say so.

If the tracker was intentionally not updated because the change was trivial, do not force an update.

---

## Preferred mindset
Treat the current desktop app as:
- a valuable production tool
- the current fallback during migration
- a proving ground for the workflow
- a reference implementation for the future product engine and service layer

Do not treat the current desktop UI as the final architectural destination.
Do not treat the current desktop app as disposable.
Do not treat future web delivery as permission for uncontrolled platform buildout.

Build the product so that the **workflow, rules, configurations, service boundaries, and export behaviors** become increasingly portable, testable, and reliable over time.

---

## Success condition
This file is being followed correctly when:

- the desktop app remains stable and usable
- the repo progresses through migration in controlled slices
- `core/` and reusable workflow behavior stay protected
- meaningful architectural decisions are documented
- desktop-only lock-in is visible rather than accidental
- the transition tracker remains concise, current, and useful
- work does not prematurely jump ahead of the approved migration phase