# AGENTS.md

Use .\.venv\Scripts\python.exe for all Python commands, tests, and dependency checks in this repo.

## Project Context
This repository is now a web-first job cost recap product built around a shared Python engine and service layer.

Current delivery model:
- `web/` is the primary operator-facing delivery shell.
- `api/` is the primary backend boundary for browser workflows.
- `app/` remains a valuable desktop fallback and reference implementation.

The desktop app is not throwaway code. It still matters as:
- a production fallback when needed
- a reference for hardened workflow behavior
- a secondary delivery shell that should remain stable when touched

At the same time, the repo is no longer in an early migration stance where web/API work is assumed out of scope. Web and API work are normal in-scope parts of the product now.

---

## Current Working Stance
Treat this repo as:
- a reusable product engine in `core/`
- a reusable orchestration layer in `services/`
- a web-first delivery system with desktop fallback

Default assumptions:
- prefer reusable engine/service logic over delivery-specific logic
- preserve current lineage and immutability rules
- keep desktop stable when desktop code is touched
- avoid unnecessary platform sprawl or speculative infrastructure
- treat one-organization internal use as the default unless the task explicitly expands scope

Avoid assuming that the right answer is to build broad multi-tenant provisioning, billing, background-worker infrastructure, or other platform-heavy features unless the current task clearly asks for them.

---

## Product Rules That Must Be Preserved
Meaningful work should preserve these product realities:

- raw report fidelity and traceability matter
- valid report-body lines should survive as records unless intentionally omitted or clearly non-body noise
- phase context matters heavily
- family/type separation is intentional
- export-only behavior should stay in export, not leak backward into parsing or normalization
- raw mapping source and resolved recap/export classification must stay separate
- profile/config behavior should remain data-driven
- current hardened desktop behavior is still a useful correctness reference when shared logic is touched

---

## Architecture Expectations
Prefer a clean separation between these layers.

### 1. Core domain / product engine
Reusable logic that should stay portable:
- record models
- parsing
- normalization
- validation
- mapping logic
- export transformation logic
- profile/config interpretation
- workflow rules

### 2. Application / service layer
Workflow orchestration and behavior shaping:
- document ingest/open
- profile resolution
- processing-run creation and lineage capture
- review edit application and revision behavior
- profile authoring/edit orchestration
- blocker/warning shaping
- export-readiness decisions
- export generation orchestration

### 3. Delivery layers
Interface-specific behavior:
- FastAPI routes and schemas
- React/browser UI
- PySide windows, dialogs, tables, and widget refreshes

Keep business logic out of UI glue when a service or core location is cleaner.

---

## Implementation Guidance
When multiple valid approaches exist, prefer this order:

1. correctness
2. maintainability
3. preservation of hardened product behavior
4. clear reusable boundaries
5. delivery-shell polish

Prefer:
- small focused changes
- explicit reasoning
- stable interfaces
- regression tests for meaningful behavior
- shared helpers/services for business behavior

Avoid:
- broad rewrites unless requested
- mixing unrelated refactor + feature + UI redesign in one change
- embedding business rules directly in browser widgets or PySide UI code
- speculative platform buildout that is not needed for the task

Web/API work is normal in-scope, but it should still be thin over the accepted service and product rules rather than turning into infrastructure sprawl.

---

## Lineage And Immutability Rules
Any work touching processing, review, profile authoring, or export should preserve these rules:

- each `ProcessingRun` is a fixed snapshot
- reprocessing with new logic or settings creates a new `ProcessingRun`
- a `ReviewSession` belongs to one specific `ProcessingRun`
- review edits are append-only overlays/deltas, not destructive rewrites of run records
- every run captures the exact profile/config snapshot and engine context used at process time
- later profile/config changes do not mutate old runs, review sessions, exports, or prior results
- profile authoring changes become processable only through the published-version path, not through mutable in-progress state

Do not introduce persistence, API, or UI behavior that weakens these boundaries.

---

## Testing Expectations
For non-trivial changes, add or update tests where appropriate.

Especially protect:
- parsing behavior
- normalization behavior
- validation outcomes
- mapping behavior
- export generation behavior
- workflow-level edit behavior
- review lineage behavior
- trusted-profile authoring behavior
- browser workflow regressions
- bug fixes for previously observed trust-eroding issues

If a bug is fixed, prefer a regression test that would have caught it.

---

## Desktop And Web Guidance
The web product is the primary delivery path, but desktop still matters.

When touching desktop code:
- preserve stability
- keep UI glue thin
- avoid reintroducing desktop-only ownership of shared workflow logic

When touching web/API code:
- treat the existing web/API stack as a real product surface, not scaffolding
- keep behavior anchored in shared services/helpers when possible
- avoid widening into unrelated platform/admin work unless requested

---

## Tracker Workflow
The live tracker is:

`docs/transition_tracker.md`

The historical archive is:

`docs/transition_tracker_archive.md`

For meaningful work:
1. read `AGENTS.md`
2. read the previous day's entries in `docs/transition_tracker.md` by default
3. widen to older live-tracker entries or the archive only when the task depends on older decisions, architecture, or historical context

Update the live tracker when a task changes:
- architecture or delivery boundaries
- workflow behavior
- parsing/normalization/validation/export behavior
- profile/config behavior
- current product stance
- active risks or priorities
- meaningful technical debt or follow-up guidance

Do not update the tracker for trivial edits or purely local cleanup with no behavior or architecture impact.

Tracker updates should stay concise and current-state oriented.

---

## Output Expectations For Coding Tasks
After meaningful code changes, provide a concise summary that includes:

- files changed
- why each changed file changed
- whether the change primarily affected:
  - core logic
  - application/services
  - persistence/API
  - web delivery
  - desktop shell
  - tests
  - config/docs
- test impact
- desktop/web impact when relevant
- any notable risks or follow-up items

If the tracker was updated, say so.

---

## Success Condition
This file is being followed correctly when:

- the web product continues to improve without unnecessary platform sprawl
- shared engine/service behavior stays protected
- desktop remains stable when touched
- lineage and published-version rules stay intact
- guidance docs stay aligned with the real repo state
- the live tracker remains short, current, and useful
