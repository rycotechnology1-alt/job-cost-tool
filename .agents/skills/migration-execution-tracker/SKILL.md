---
name: migration-execution-tracker
description: Use this skill when making meaningful changes to the recap tool during the desktop-to-web migration so implementation stays aligned with the approved migration sequence, desktop stability is preserved, and the transition tracker remains current.
---

# Migration Execution Tracker Skill

## Purpose
This skill keeps development aligned with the current reality of the repository:

1. The desktop app is still a working MVP and must remain stable.
2. The repo is now in an active, controlled migration toward a web-based delivery model.
3. The most valuable product behavior remains in reusable engine/workflow logic, not the desktop shell.
4. Migration should happen in safe, reviewable slices rather than broad platform buildout.

Use this skill whenever a task involves meaningful code, architecture, workflow, config, test, migration, or feature changes.

This skill is not a generic changelog workflow. It is a **migration-execution discipline and tracker-awareness workflow**.

---

## Files this skill governs
Always read these files before doing meaningful work:

- `AGENTS.md`
- `docs/transition_tracker.md`

If either file conflicts with direct user instructions, follow the user’s instructions but preserve as much of the tracker workflow and migration discipline as reasonably possible.

---

## Current approved migration stance
The repository is no longer merely “migration-aware.” It is in an active migration program.

The current approved migration direction is:

- preserve `core/` as the product engine
- use a strangler approach
- extract non-Qt application services before rebuilding UI
- keep the desktop app operational until web parity is accepted
- prefer safe, incremental implementation over broad platform scaffolding

### Current approved implementation slice
Unless the user explicitly requests a later migration phase, the default approved implementation scope is:

- extract plain Python application services from `ReviewViewModel` and `SettingsViewModel`
- keep workflow orchestration and business-state shaping out of Qt
- add non-Qt application-service tests proving extracted services preserve current desktop behavior

### Current default out-of-scope items
Do **not** introduce the following unless the current task explicitly asks for them:

- PostgreSQL persistence/schema implementation
- FastAPI route buildout
- React/frontend scaffolding
- worker infrastructure / background job queue
- broad API contract implementation
- full profile/admin web tooling
- true multi-tenant behavior
- broad rewrites outside the approved migration slice

---

## When to use this skill
Use this skill for any meaningful change, including:

- parsing logic changes
- normalization changes
- validation changes
- export behavior changes
- profile/config/model changes
- classification/rate/template changes
- service extraction work
- workflow orchestration refactors
- persistence model preparation
- API contract preparation
- parity harness work
- desktop refactors that affect workflow structure
- test additions that protect important behavior
- bug fixes that change behavior or architecture
- changes that increase or reduce portability to the future web model

---

## When not to use this skill
Do not update the tracker for trivial changes unless they affect architecture, workflow behavior, portability, or migration risk.

Usually skip tracker updates for:
- formatting-only edits
- typo fixes
- copy changes with no behavioral significance
- local comments that do not affect design intent
- tiny UI polish with no workflow or architecture impact

You may still read the tracker for context, but do not create unnecessary tracker churn.

---

## Required workflow

### Step 1: Read context first
Before making meaningful changes:

1. Read `AGENTS.md`
2. Read `docs/transition_tracker.md`

Pay special attention to:
- current product status
- approved migration phase
- architecture decisions
- known migration risks
- near-term priorities
- parity requirements
- desktop fallback expectations

---

### Step 2: Classify the requested work
Before editing code, classify the task into one or more buckets:

- **Core reusable improvement**
- **Service extraction / application orchestration**
- **Desktop shell-only change**
- **Persistence / API preparation**
- **Web delivery implementation**
- **Temporary migration debt**
- **Bug fix**
- **Test protection / parity coverage**

Use this classification to guide implementation decisions and tracker updates.

---

### Step 3: Check the work against the current migration phase
Before implementing, explicitly ask:

- Is this work inside the currently approved migration slice?
- Does it preserve desktop MVP stability?
- Does it protect or improve reusable engine/workflow behavior?
- Does it avoid premature backend/platform buildout?
- Does it require a tracker update because it changes migration readiness, architecture, or risk?

If the work goes beyond the currently approved slice, do not assume it is allowed. Only proceed if the current task explicitly requests that later phase.

---

### Step 4: Prefer the right kind of implementation
When multiple valid approaches are possible, prefer the one that best supports this order:

1. correctness
2. maintainability
3. preservation of hardened behavior
4. portability to the future web model
5. desktop-specific polish

Do not force artificial abstractions. However, avoid adding business logic directly into PySide UI code when a service/domain location is cleaner.

Prefer:
- small targeted changes
- stable interfaces
- explicit data flow
- data-driven behavior
- profile/config-based behavior
- tests for meaningful changes
- limited blast radius
- incremental migration progress

Avoid:
- broad rewrites unless requested
- mixing unrelated concerns in one change
- hard-coding customer-specific assumptions into core logic
- allowing widget/UI structures to define domain behavior
- using the migration as an excuse to scaffold major backend/web infrastructure too early

---

### Step 5: Keep business logic and UI glue separate
When refactoring desktop code, treat these as likely application logic candidates:

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
- other PySide-only mechanics

If moving logic, prefer moving it downward into reusable services/modules rather than sideways into more UI code.

---

### Step 6: Update the tracker when required
After meaningful changes, update `docs/transition_tracker.md` if the task affected any of the following:

- product architecture
- workflow behavior
- parsing/normalization/validation behavior
- export behavior
- config/profile abstractions
- desktop coupling
- migration readiness
- parity readiness
- known risks
- deferred work
- recommended priorities
- important decisions
- significant bug-fix implications

Make concise, useful updates only.

---

## How to update the tracker

### A. Update “Recent meaningful changes”
Add a short entry when the task caused a meaningful change.

Use this format:
- date
- change title
- what changed
- why
- area
- portability impact
- risks introduced
- follow-up needed

Do not over-explain.

---

### B. Update “Architecture decisions” when a decision was made
Add an entry when the task includes a real design decision such as:
- where logic belongs
- whether behavior becomes data-driven
- whether desktop coupling is preserved or reduced
- whether a feature is deferred to a later migration phase
- how configs/models should be represented
- how services should be separated from UI
- how lineage, parity, or migration boundaries are enforced

Only add an architecture decision entry when there is a real decision, not just routine coding.

---

### C. Update migration buckets when status materially changed
Update checkboxes or notes in sections such as:
- Ready or becoming ready for future web reuse
- Still desktop-coupled
- In active service extraction
- Deferred until later migration phase
- Known migration risks
- Near-term recommended priorities
- Parity readiness

Only change these when the task materially moved the product forward or introduced new constraints.

---

### D. Record intentional debt honestly
If a change intentionally increases desktop coupling or introduces expedient migration/MVP debt, record that clearly and briefly.

Do not hide temporary compromises.

Use labels like:
- provisional
- temporary
- desktop-only
- migration-staged
- deferred to later phase

---

## Decision rules for tracker updates

### Add a “Recent meaningful changes” entry when:
- behavior changed
- a bug fix changed workflow or output
- a test suite was meaningfully expanded
- a service boundary improved
- portability improved or worsened
- config/model abstractions changed
- migration scope or execution posture changed

### Add an “Architecture decisions” entry when:
- a structural choice was made
- a feature was intentionally deferred
- domain logic was moved out of UI
- config/data modeling direction changed
- a migration-related design choice was made
- a parity, lineage, or persistence boundary was defined

### Update risks when:
- new migration obstacles appear
- a known risk is reduced or eliminated
- a design choice introduces future rewrite cost
- work drifts outside the approved migration slice

### Skip tracker edits when:
- the change is trivial
- the impact is purely cosmetic
- there is no real behavior or design consequence

---

## Output expectations after code changes
After meaningful work, provide a concise summary that includes:

- files changed
- why each changed file changed
- classification of the change:
  - Core engine
  - Application services
  - Desktop shell
  - Persistence/API prep
  - Web delivery
  - Tests
  - Config
- migration impact:
  - Increased portability
  - Neutral
  - Increased desktop coupling
- notable risks
- follow-up items

If the tracker was updated, mention that it was updated.

If the tracker was intentionally not updated because the task was trivial, do not force an update.

---

## Project-specific guidance for this repository

### Treat the current desktop app correctly
This project is not throwaway desktop code.

It is:
- a working MVP
- a valuable internal tool
- a proven workflow shell
- the current production fallback during migration
- a reference implementation for the future web product

Respect the current app, but do not assume the current desktop UI is the long-term delivery model.

---

### Protect the true product core
The most strategically valuable parts of the product are likely:
- parsing logic
- normalization logic
- validation rules
- profile/config abstractions
- classification/rate/template models
- export transformation behavior
- workflow-level edit behavior
- service-layer orchestration
- parity fixtures/tests
- acceptance-corpus support

Prefer strengthening those areas over investing heavily in desktop-only polish.

---

### Be careful with desktop lock-in
Desktop-only improvements are acceptable when they provide real user value now, but avoid:
- embedding business logic in widgets
- tying workflow rules to local dialogs/tables
- assuming local file-only models in core services
- making PySide state the source of truth for domain behavior

When possible, push logic downward into reusable modules/services.

---

### Think in current migration boundaries
When it helps, think in terms of separable layers:

- domain/product engine
- application/service orchestration
- delivery interface

At the current phase, prefer strengthening:
- engine reliability
- service extraction boundaries
- parity protection

Do not over-engineer prematurely, but do not let desktop UI remain the permanent home of workflow logic.

---

### Respect the approved migration sequence
Unless explicitly instructed otherwise, prefer work that supports this order:

1. service extraction
2. parity/service-level tests
3. lineage/persistence design
4. API layer
5. minimal web delivery layer
6. later profile/admin expansion

Do not skip ahead casually.

---

## Editing style for tracker updates
Tracker updates should be:
- concise
- decision-oriented
- honest
- high signal
- easy to scan later

Do not turn `docs/transition_tracker.md` into:
- a diary
- a long narrative
- a duplicate changelog
- a place for trivial noise

---

## Example mental checklist
Before finishing meaningful work, ask:

- Did this change improve the reusable engine or only the shell?
- Did I put business logic in the right layer?
- Did I stay inside the approved migration slice?
- Did I improve or worsen portability?
- Did I introduce customer-specific assumptions into the core?
- Should this be recorded as a decision, a risk, or a meaningful change?
- Did I add or update tests where needed?
- Is the tracker now missing something important because of this work?

---

## Success condition
This skill is working correctly when:

- the desktop app remains stable and usable
- the repo progresses through migration in controlled slices
- `core/` and reusable workflow behavior stay protected
- meaningful architectural decisions are documented
- desktop-only lock-in is visible rather than accidental
- the transition tracker remains concise, current, and useful
- Codex does not prematurely build beyond the currently approved migration phase