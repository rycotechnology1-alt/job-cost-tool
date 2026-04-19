# Web-Only Vercel/Postgres Migration Design

## Goal

Remove the desktop product surface and desktop-era runtime assumptions from this repository so the product can operate as a web-first, hosted-only system deployed on Vercel with Neon Postgres persistence.

## Desired End State

The repository retains these active layers:

- `core/` for reusable parsing, normalization, validation, export transformation, and profile/config interpretation
- `services/` for workflow orchestration, review lineage behavior, trusted-profile authoring, and export orchestration
- `infrastructure/` for Postgres-backed persistence and hosted runtime storage
- `api/` and `web/` as the only delivery surfaces

The repository no longer treats desktop delivery, desktop sync, filesystem-managed local profiles, or desktop parity as first-class product concerns.

## Non-Goals

- Broad feature redesign of the browser workflow
- Rewriting stable parser, normalization, or export rules that are not required by desktop removal
- Generalized multi-tenant platform expansion beyond the existing hosted/runtime seams
- Replacing the current lineage or immutable snapshot model

## Product Invariants To Preserve

The migration must preserve these behaviors:

- each `ProcessingRun` remains an immutable snapshot
- each `ReviewSession` remains bound to one exact `ProcessingRun`
- review edits remain append-only overlays or deltas
- published trusted-profile versions remain immutable inputs to processing/export
- later profile changes do not rewrite historical runs, revisions, or exports
- parsing, normalization, validation, and export behavior remain shared, testable product logic rather than moving into API or React glue

## Current Problems

The current repository still carries desktop-era behavior in multiple places:

- the `app/` PySide6 shell is still present
- `PySide6` remains in the root Python runtime dependency set, which breaks Vercel Python bundle limits
- API and web still expose desktop-sync concepts that no longer match the intended product direction
- shared code still carries compatibility seams for filesystem-managed profiles and legacy config fallback
- deployment posture is ambiguous because hosted behavior exists but is not the canonical default runtime

## Proposed Approach

Use one staged migration that removes desktop code and desktop-facing product affordances while preserving the shared product engine and lineage rules.

This is not a broad rewrite. The migration should focus on removing unused delivery surfaces and compatibility branches, promoting hosted runtime configuration to the default operational model, and tightening tests/docs around the web/API product.

## Architecture

The architecture becomes a web-hosted product with four active layers:

1. `core/` remains the portable domain engine.
2. `services/` remains the orchestration layer for processing, review, trusted-profile authoring, and export behavior.
3. `infrastructure/` becomes the canonical hosted persistence/runtime layer, centered on Neon Postgres and blob-backed artifacts.
4. `api/` + `web/` become the only supported delivery shells.

`app/` is removed entirely. Shared abstractions that only exist to support desktop compatibility should be removed or narrowed so the remaining code reflects the actual product.

## Component Design

### 1. Remove the desktop delivery surface

Delete the `app/` package and remove `PySide6` from Python runtime dependencies.

Delete tests that only validate:

- desktop UI behavior
- desktop viewmodels/widgets
- desktop-as-reference parity flows

Retain tests that validate shared engine or API/browser product behavior.

### 2. Remove desktop-specific product affordances

Remove the desktop-sync export flow from:

- API routes
- schemas
- serializers
- services
- browser UI and browser tests
- documentation

After the migration, the web product should only expose hosted workflows that remain meaningful in a browser-first deployment.

### 3. Collapse desktop-era compatibility seams

Shared code currently carries several compatibility concepts that should be reduced or removed:

- filesystem-bootstrap assumptions
- desktop-managed active-profile behavior
- legacy config fallback as an equal runtime mode
- desktop-vs-web parity harness concepts

The desired runtime source of truth is:

- persisted trusted profiles and published versions in lineage storage
- materialized published bundles used for processing/export execution
- hosted request/runtime context used by API flows

Filesystem profile bundles may remain only where they serve as seed/bootstrap assets or deterministic test fixtures. They should no longer define the supported operational runtime model.

### 4. Make hosted runtime the canonical configuration

Hosted deployment should assume:

- Neon Postgres for lineage persistence
- Vercel Blob-backed artifact storage for uploads and generated artifacts
- Vercel-hosted API execution

Local SQLite/local filesystem behavior may remain only as an explicit local-development path if still useful, but it must stop being the implied production default.

The runtime should fail fast and clearly when deployed with invalid hosted settings instead of silently falling back to local disk assumptions.

### 5. Make deployment shape explicit

The repository should declare a clear deployment contract for:

- frontend build/output from `web/`
- Python ASGI app entrypoint for API traffic
- required environment variables for hosted runtime
- production-safe defaults and disallowed fallback modes

The deployment shape should be documented and testable rather than inferred from current local-dev layout.

## Data Flow

The intended hosted workflow is:

1. Browser uploads a source document through the hosted API.
2. Runtime storage persists the upload in blob-backed storage.
3. API resolves the selected published trusted-profile version and materializes the exact bundle needed for execution.
4. Processing creates an immutable `ProcessingRun` and persisted run records in Postgres.
5. Review edits append immutable deltas against that run.
6. Export generates an exact-revision artifact and stores it in hosted artifact storage.
7. Browser downloads the generated hosted artifact.

No step in this supported path should depend on desktop UI code, PySide types, or desktop-sync packaging.

## Error Handling

Error handling should become more hosted-oriented and more explicit.

The system should clearly distinguish:

- invalid deployed environment configuration
- missing or invalid persisted profile/version data
- storage provider failures
- persistence/database failures
- user-correctable workflow validation errors

Messages and branches that refer to desktop sync, local desktop ownership, or filesystem-managed profile responsibility should be removed where they no longer describe supported behavior.

## Testing Strategy

Keep and expand coverage for:

- parsing behavior
- normalization behavior
- validation outcomes
- export generation
- immutable processing/review lineage
- trusted-profile authoring and publishing
- Postgres persistence behavior
- blob-backed runtime storage behavior
- API contract behavior
- browser workflow behavior

Remove coverage whose primary purpose is:

- desktop UI validation
- desktop reference-path execution
- desktop-vs-web parity comparison

Add or strengthen coverage for:

- hosted runtime configuration selection
- failure behavior for invalid hosted env configuration
- API/browser behavior after desktop-only endpoints and actions are removed
- Vercel/hosted artifact flows that matter to the supported runtime

## Documentation Impact

Update repository guidance to match the new product reality:

- `README.md` should describe the repo as a web/API product with shared engine and hosted runtime
- `AGENTS.md` should remove desktop-fallback language and align with the hosted-only stance
- deployment documentation should describe Vercel + Neon + blob-backed runtime expectations

Historical plans/specs may remain as historical context, but active guidance must stop describing desktop as a supported delivery path.

## Risks

### Risk: removing desktop compatibility changes shared behavior accidentally

Mitigation:

- keep parser/normalization/export regression coverage focused on shared behavior
- avoid unrelated rewrites during removal
- remove compatibility branches in small, test-backed increments

### Risk: hosted defaults are incomplete and break local development

Mitigation:

- explicitly define which local-dev paths remain supported
- separate local-dev configuration from production deployment configuration
- add tests for runtime selection and hosted misconfiguration failure cases

### Risk: desktop concepts remain partially exposed in web/API behavior

Mitigation:

- inventory and remove desktop-sync/UI copy, routes, schemas, tests, and docs as one tracked workstream
- verify browser tests and API contract tests reflect the final product surface

## Recommended Execution Order

1. Remove desktop dependencies and the `app/` surface.
2. Remove desktop-only tests and desktop parity/reference infrastructure.
3. Remove desktop-sync and other desktop-facing product affordances from API/web/services.
4. Narrow or remove shared compatibility seams that only exist for desktop/filesystem support.
5. Promote hosted runtime configuration and deployment shape to the canonical supported model.
6. Update tests and docs to match the new hosted-only product stance.

## Success Criteria

This migration is successful when:

- the repository contains no desktop delivery surface
- Vercel deployment no longer bundles desktop dependencies
- the supported product surface is clearly web + API only
- Neon Postgres and hosted runtime storage are the explicit deployment model
- immutable run/review/profile lineage rules remain intact
- tests protect shared behavior and hosted workflows without relying on desktop parity
- docs accurately describe the repository as a hosted web-first product with no desktop fallback
