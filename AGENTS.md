# AGENTS.md

Use `.\.venv\Scripts\python.exe` for all Python commands, tests, and dependency checks in this repo.

## Current Product State
This repository is a web-first job cost recap product built around a shared Python engine and service layer.

Current delivery model:
- `web/` is the primary operator-facing shell.
- `api/` is the primary backend boundary for browser workflows.
- `app/` remains a valuable desktop fallback and reference implementation.

Current product surface:
- browser upload, processing, review, and export workflows are active
- browser trusted-profile selection and profile-settings authoring are active
- shared persistence, lineage, and runtime-storage seams now support local and hosted-oriented workflows
- desktop still matters as a fallback and as a correctness reference when shared behavior is touched

This repo no longer carries a repo-local tracker workflow. Use the current code, tests, `README.md`, and active plan/spec docs for context when needed.

---

## Current Working Stance
Treat this repo as:
- a reusable product engine in `core/`
- a reusable orchestration layer in `services/`
- a persistence/runtime layer in `infrastructure/`
- a web-first delivery system with desktop fallback

Default assumptions:
- prefer reusable engine/service logic over delivery-specific logic
- preserve lineage, immutability, and published-version rules
- keep API and UI layers thin
- keep desktop stable when desktop code is touched
- avoid unnecessary platform sprawl or speculative infrastructure
- treat one-organization internal use as the default unless the task explicitly expands scope

Avoid assuming the right answer is broad platform buildout such as billing, background workers, admin consoles, or generalized multi-tenant infrastructure unless the current task clearly needs it.

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
- review and export behavior must continue to respect immutable processing snapshots and exact revision lineage

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
- trusted-profile authoring/edit orchestration
- blocker/warning shaping
- export-readiness decisions
- export generation orchestration

### 3. Persistence / runtime layer
Infrastructure concerns behind stable seams:
- lineage-store implementations
- schema and migrations
- runtime storage
- hosted/local runtime composition

### 4. Delivery layers
Interface-specific behavior:
- FastAPI routes and schemas
- React/browser UI
- PySide windows, dialogs, tables, and widget refreshes

Keep business logic out of route glue and UI glue when a service, core, or infrastructure seam is cleaner.

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
- mixing unrelated refactor, feature, and UI redesign in one change
- embedding business rules directly in React components, FastAPI routes, or PySide widgets
- speculative platform buildout that is not needed for the task

Web/API work is normal in-scope, but it should stay thin over the accepted service and product rules rather than turning into infrastructure sprawl.

---

## Lineage And Immutability Rules
Any work touching processing, review, profile authoring, or export should preserve these rules:

- each `ProcessingRun` is a fixed snapshot
- reprocessing with new logic or settings creates a new `ProcessingRun`
- a `ReviewSession` belongs to one specific `ProcessingRun`
- review edits are append-only overlays or deltas, not destructive rewrites of run records
- every run captures the exact profile/config snapshot and engine context used at process time
- later profile/config changes do not mutate old runs, review sessions, exports, or prior results
- profile authoring changes become processable only through the published-version path, not through mutable in-progress state
- export should remain bound to the reviewed run or revision that produced it, and profile-setting changes must not silently rewrite prior review meaning

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
- optimistic-concurrency and persistence conflict behavior
- org-scoped persistence or hosted runtime behavior when touched
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
- do not assume single-instance local-disk behavior where runtime storage or hosted composition already provides a cleaner seam

---

## Documentation Guidance
Keep the docs that remain in this repo aligned with the actual current state.

Prefer:
- updating `AGENTS.md` when repo guidance or engineering stance changes
- updating `README.md` when operator-visible capabilities or architecture summaries change
- keeping dated plan/spec docs under `docs/superpowers/` as historical implementation context when useful

Avoid:
- reintroducing a repo-local transition tracker or archive unless explicitly requested
- creating process-heavy guidance that duplicates current README or code truth without adding real decision value

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

---

## Success Condition
This file is being followed correctly when:

- the web product continues to improve without unnecessary platform sprawl
- shared engine/service behavior stays protected
- desktop remains stable when touched
- lineage and published-version rules stay intact
- guidance docs stay aligned with the real repo state
- repo guidance stays useful without relying on a separate tracker workflow
