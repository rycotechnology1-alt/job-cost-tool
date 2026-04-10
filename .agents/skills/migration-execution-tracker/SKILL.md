---
name: migration-execution-tracker
description: Use this skill for meaningful repo changes so work stays aligned with the current web-first product state, preserves desktop fallback stability, and keeps the live transition tracker concise and current.
---

# Migration Execution Tracker Skill

## Purpose
Despite the skill name, this repo is no longer in an early migration-only phase.

Use this skill to keep meaningful work aligned with the current reality:
- the repo is web-first now
- desktop still exists as a fallback and reference shell
- the most valuable behavior still lives in shared engine/service logic
- the live tracker should stay short and current instead of becoming a full historical diary

This skill is for execution discipline, current-state awareness, and tracker hygiene.

---

## Files This Skill Governs
Read these first for meaningful work:
- `AGENTS.md`
- `docs/transition_tracker.md`

Read `docs/transition_tracker_archive.md` only when the task depends on older architecture or historical decisions.

---

## Current Repository Stance
Treat the repository as:
- a shared Python product engine in `core/`
- a shared orchestration layer in `services/`
- a thin API layer in `api/`
- a thin browser delivery shell in `web/`
- a desktop fallback/reference shell in `app/`

Default stance:
- web/API work is normal in-scope
- desktop stability still matters when touched
- reusable business logic belongs below delivery shells
- avoid unnecessary platform expansion unless the task requires it

---

## When To Use This Skill
Use this skill for meaningful work, including:
- workflow behavior changes
- parsing/normalization/validation/export changes
- profile/config/model changes
- service-boundary changes
- API contract changes
- browser workflow changes
- desktop changes that affect behavior
- meaningful tests or regression coverage
- tracker or architecture guidance updates

---

## Lightweight Context Workflow
Before meaningful work:
1. Read `AGENTS.md`.
2. Read the previous day's entries in `docs/transition_tracker.md` by default.
3. Search older live-tracker entries or the archive only if the task touches older decisions, delivery boundaries, or historical constraints.

Do not load the full archive by default.

---

## Execution Rules
Before implementing, classify the task into one or more buckets:
- Core engine
- Application services
- Persistence/API
- Web delivery
- Desktop shell
- Tests
- Config/docs
- Bug fix

Then check:
- Does this preserve product rules and lineage boundaries?
- Does shared logic live in the right layer?
- Does this keep desktop stable when desktop is touched?
- Does this avoid unnecessary platform sprawl?
- Does this require a live-tracker update because current behavior, architecture, risks, or priorities changed?

---

## Tracker Update Rules
Update `docs/transition_tracker.md` when the task meaningfully changes:
- current product state
- architecture or delivery boundaries
- workflow behavior
- profile/config behavior
- parsing/normalization/validation/export behavior
- active risks
- active priorities
- important follow-up guidance

Keep updates:
- concise
- decision-oriented
- current-state focused
- easy to scan

Do not bloat the live tracker with deep history. When history must be preserved, keep it in `docs/transition_tracker_archive.md`.

---

## Output Expectations
After meaningful work, summarize:
- files changed
- why they changed
- affected areas
- test impact
- notable risks or follow-up items
- whether the live tracker was updated

---

## Success Condition
This skill is working correctly when:
- shared engine/service behavior stays protected
- web/API work reflects the actual current product state
- desktop remains stable when touched
- lineage and publish boundaries stay intact
- the live tracker stays short and useful
- older history is consulted only when it is actually relevant
