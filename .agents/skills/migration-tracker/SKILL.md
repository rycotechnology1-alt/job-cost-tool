---
name: migration-tracker
description: Use this skill when making meaningful changes to the desktop recap tool so the repo's transition tracker stays current and development remains aligned with a future web migration path.
---

# Migration Tracker Skill

## Purpose
This skill keeps development aligned with two simultaneous goals:

1. Continue improving the current desktop MVP in practical, shippable ways.
2. Preserve and strengthen the parts of the product that can later support a scalable web-based application.

Use this skill whenever a task involves meaningful code, architecture, workflow, config, test, or feature changes.

This skill is not a generic changelog workflow. It is a **decision and migration-awareness workflow**.

---

## Files this skill governs
Always read these files before doing meaningful work:

- `AGENTS.md`
- `docs/transition_tracker.md`

If either file conflicts with ad hoc user instructions, follow the user’s instructions but preserve as much of the tracker workflow as reasonably possible.

---

## When to use this skill
Use this skill for any meaningful change, including:

- parsing logic changes
- normalization changes
- validation changes
- export behavior changes
- profile/config/model changes
- classification/rate/template changes
- bulk edit behavior changes
- onboarding/setup logic changes
- predictive mapping work
- service-layer refactors
- UI refactors that affect workflow structure
- test additions that protect important behavior
- bug fixes that change behavior or architecture
- changes that increase or reduce portability to a future web app

---

## When not to use this skill
Do not update the tracker for trivial changes unless they affect architecture, workflow behavior, portability, or risk.

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
- strategic rules
- core hardening priorities
- known migration risks
- architecture decisions
- near-term recommended priorities
- web transition triggers

---

### Step 2: Classify the requested work
Before editing code, classify the task into one or more buckets:

- **Core reusable improvement**
- **Application/service-layer improvement**
- **Desktop delivery layer improvement**
- **Web migration preparation**
- **Temporary MVP debt**
- **Bug fix**
- **Test protection / regression coverage**

Use this classification to guide implementation decisions.

---

### Step 3: Prefer the right kind of implementation
When multiple valid approaches are possible, prefer the one that best supports this order:

1. correctness
2. maintainability
3. portability to a future web model
4. desktop-specific polish

Do not force artificial abstractions. However, avoid adding business logic directly into PySide UI code when a service/domain location is cleaner.

Prefer:
- small targeted changes
- stable interfaces
- explicit data flow
- data-driven behavior
- profile/config-based behavior
- tests for meaningful changes
- limited blast radius

Avoid:
- broad rewrites unless requested
- mixing unrelated concerns in one change
- hard-coding customer-specific assumptions into core logic
- allowing UI/widget structures to define domain behavior unnecessarily

---

### Step 4: Update the tracker when required
After meaningful changes, update `docs/transition_tracker.md` if the task affected any of the following:

- product architecture
- workflow behavior
- parsing/normalization/validation behavior
- export behavior
- config/profile abstractions
- desktop coupling
- migration readiness
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
- whether to preserve or reduce desktop coupling
- whether a feature is deferred to the web version
- how configs/models should be represented
- how services should be separated from UI

Only add an architecture decision entry when there is a real decision, not just routine coding.

---

### C. Update migration buckets when status materially changed
Update checkboxes or notes in sections such as:
- Ready or becoming ready for future web reuse
- Still desktop-coupled
- Deferred until web model
- Known migration risks
- Near-term recommended priorities

Only change these when the task materially moved the product forward or introduced new constraints.

---

### D. Record intentional debt honestly
If a change intentionally increases desktop coupling or introduces expedient MVP debt, record that clearly and briefly.

Do not hide temporary compromises.

Use labels like:
- provisional
- temporary
- desktop-only
- deferred to web model

---

## Decision rules for tracker updates

### Add a “Recent meaningful changes” entry when:
- behavior changed
- a bug fix changed workflow or output
- a test suite was meaningfully expanded
- a service boundary improved
- portability improved or worsened
- config/model abstractions changed

### Add an “Architecture decisions” entry when:
- a structural choice was made
- a feature was intentionally deferred
- domain logic was moved out of UI
- config/data modeling direction changed
- a migration-related design choice was made

### Update risks when:
- new migration obstacles appear
- a known risk is reduced or eliminated
- a design choice introduces future rewrite cost

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
  - Desktop UI
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
This project is not “throwaway desktop code.”
It is:
- a working MVP
- a valuable internal tool
- a proving ground for the workflow
- a reference implementation for a future scalable product

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
- onboarding/setup outputs
- predictive mapping foundations
- workflow-level edit behavior
- tests and fixtures

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

### Think in future service boundaries
When it helps, think in terms of future separable layers:

- domain/product engine
- application/service orchestration
- delivery interface

Do not over-engineer prematurely, but prefer clean boundaries when they are practical.

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

- Did this change improve the reusable engine or only the desktop shell?
- Did I put business logic in the right layer?
- Did I improve or worsen portability?
- Did I introduce customer-specific assumptions into the core?
- Should this be recorded as a decision, a risk, or a meaningful change?
- Did I add or update tests where needed?
- Is the tracker now missing something important because of this work?

---

## Success condition
This skill is working correctly when:

- the current desktop app keeps improving
- the repo preserves awareness of future web migration needs
- meaningful architectural decisions are documented
- desktop-only lock-in is visible rather than accidental
- the transition tracker remains concise, current, and useful