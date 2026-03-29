# AGENTS.md

## Project context
This repository contains a Python desktop application built with PySide6 for automating T&M recap creation from Vista/Viewpoint-style job cost reports.

The current product is a working desktop MVP. It is highly valuable in its current form and should continue to be improved. At the same time, the long-term product direction may evolve into a scalable web-based application. Because of that, all meaningful development work in this repository should balance two goals:

1. Improve the current desktop product in practical, shippable ways.
2. Preserve and strengthen the parts of the system that can later be reused in a web architecture.

This repository should be treated as a **desktop delivery layer around a reusable product engine**, not as a permanently desktop-only product.

---

## Primary development objective
When making changes, prioritize work that strengthens the following platform-independent product capabilities:

- parsing logic
- normalization logic
- validation logic
- profile/config abstractions
- classification/rate/template modeling
- export mapping and export generation behavior
- onboarding/setup question flow and config outputs
- predictive mapping foundations
- bulk edit behavior at the workflow/domain level
- terminology consistency
- tests, fixtures, and edge-case coverage

Avoid over-investing in desktop-only polish when the same effort could improve the reusable product core.

---

## Architecture expectations
Prefer a clean separation between these layers:

### 1. Core domain / product engine
Reusable logic that should remain portable to a future web product:
- record models
- parsing
- normalization
- validation
- mapping logic
- export transformation logic
- profile/config interpretation
- workflow rules

### 2. Application/service layer
Orchestration logic that coordinates the workflow:
- open/import document
- load profile
- run parse/normalize/validate pipeline
- apply edits/overrides
- recalculate state
- generate export output

### 3. Interface layer
Desktop-specific PySide UI concerns:
- windows
- dialogs
- tables
- panels
- view models tightly tied to widgets
- desktop-only navigation behavior

Business logic should not be added directly to PySide widgets or window classes unless absolutely necessary. Prefer to keep UI code thin and delegate logic to services/domain modules.

---

## Desktop-vs-web decision rule
When implementing a feature or bug fix, prefer the approach that best fits the following order:

1. Correctness
2. Maintainability
3. Reusability in a future web model
4. Desktop UX polish

This does **not** mean avoiding useful desktop improvements. It means desktop-specific implementation details should not contaminate core logic when a cleaner boundary is possible.

---

## Change strategy
Keep changes targeted and reviewable.

Prefer:
- small focused changes
- explicit reasoning
- clear boundaries
- tests for meaningful behavior changes
- minimal blast radius
- documenting architectural consequences

Avoid:
- broad rewrites unless requested
- mixing refactor + new feature + UI redesign in one step
- embedding configuration or business rules in UI code
- hard-coded assumptions that reduce portability

---

## Testing expectations
For any non-trivial change, include or update tests when appropriate.

Especially protect:
- parsing behavior
- normalization behavior
- validation outcomes
- mapping behavior
- export generation behavior
- bug fixes for previously observed edge cases

If a bug is fixed, prefer adding a regression test that would have caught it.

If a behavior change is intentional, make the tests clearly reflect the intended new behavior.

---

## Configuration and profile expectations
This product is increasingly configuration-driven. Changes should preserve or improve that direction.

Prefer:
- data-driven mappings
- profile-based behavior
- reusable abstractions
- terminology consistency across config, code, and UI
- minimizing hard-coded customer-specific assumptions

Avoid:
- baking one company’s exact workflow too deeply into core logic
- forcing future customers into current naming conventions if a cleaner abstraction is possible

---

## Migration-awareness expectations
For any meaningful change, consider whether it falls into one of these buckets:

- **Core reusable improvement**
- **Desktop delivery layer only**
- **Web migration preparation**
- **Technical debt introduced temporarily for MVP speed**

Make implementation choices with this future question in mind:

**Will this make the future web product easier or harder to build?**

Not every change must optimize for migration, but meaningful architectural changes should be made consciously.

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
- portability to a future web model
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
- whether it increased or reduced desktop coupling
- whether it improved future web portability
- any migration risks introduced
- any important follow-up work
- whether the change is considered stable, provisional, or deferred

---

## Output expectations for coding tasks
After meaningful code changes, provide a concise summary that includes:
- files changed
- why each file changed
- whether the change primarily affected core logic, application services, or desktop UI
- test impact
- migration impact
- any risks or follow-up items

---

## Preferred mindset
Treat the current desktop app as:
- a valuable production tool
- a proving ground for the workflow
- a reference implementation for the future product engine

Do not treat the current desktop UI as the final architectural destination.

Build the product so that the **workflow, rules, configurations, and export behaviors** become increasingly portable and reliable over time.