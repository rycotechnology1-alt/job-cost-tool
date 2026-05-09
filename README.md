# Job Cost Tool

## Overview

Job Cost Tool is a hosted web job cost recap product for turning Vista/Viewpoint-style T&M job cost PDF reports into reviewed, export-ready Excel recap workbooks.

The supported delivery surfaces are `api/` and `web/`, backed by shared Python engine, service, and infrastructure layers. The hosted deployment model uses Vercel-hosted API/web delivery, Neon Postgres for lineage and profile persistence, and Vercel Blob for uploaded and generated artifacts. This is not a generic OCR pipeline or a one-click "trust everything" converter. The product preserves report-body fidelity and traceability, applies config-driven normalization and validation, supports review/correction, and exports through a template-driven workbook flow.

## What The Tool Does

Input:
- PDF job cost detail reports

Output:
- Excel recap workbooks based on the selected published profile version's template and recap template map

Core workflow:
1. Read and extract PDF pages.
2. Parse phase headers and transaction-like detail lines.
3. Tokenize lines into structured record fields.
4. Apply phase-aware family routing and config-driven normalization.
5. Validate recap readiness and surface blocking issues.
6. Let a user review, correct, or omit records in the browser workspace.
7. Reopen stored runs later from the Run Library in either latest reviewed mode or original processed mode.
8. Export reviewed records into the configured recap workbook template.

## Product Principles

- Preserve raw report fidelity and traceability.
- Valid report-body lines should survive parsing unless they are intentionally omitted or clearly boilerplate.
- Phase context matters heavily for family/type routing.
- Record families are intentional and distinct.
- Export-only shaping rules should stay in export instead of leaking back into parsing or normalization.
- Configuration should drive mappings, slots, rates, and workbook behavior wherever practical.
- Review, export, and profile authoring must respect immutable processing snapshots and exact revision lineage.

## Supported Record Families

The current pipeline intentionally distinguishes these recap-relevant concepts:

- labor
- equipment
- material
- subcontractor
- permit / permits & fees
- police detail
- project management

These families participate in parsing, normalization, validation, and export in different ways. They are not treated as interchangeable buckets.

## Current Workflow

### 1. Parse

The parser reads PDF text, preserves report-body lines, detects phase headers, and starts records from transaction-like lines such as `PR`, `AP`, `JC`, `IC`, and other `TX mm/dd/yy` variants that fit the report format.

Important behavior:
- raw description and source line text are preserved
- page/source traceability is preserved
- unknown-but-valid transaction-like lines are retained instead of silently dropped
- phase codes and dotted subphases matter

### 2. Normalize

Normalization is config-driven and phase-aware. It applies the current supported mapping model:

- labor normalization uses exact raw-first labor mappings
- equipment normalization uses exact derived raw equipment mapping keys
- vendor normalization is config-driven
- phase mapping can assign families directly
- slot-based recap classification/category handling is used where recap rows need stable identities

### 3. Validate

Validation determines whether the reviewed record set is export-ready. It surfaces blocking issues instead of letting bad data fail late during export.

Typical blockers include:
- missing recap labor classification
- missing equipment category
- unresolved vendor normalization where export requires it
- missing hour type for export-relevant labor hours
- unresolved family/normalization ambiguity

### 4. Review And Correct

The product is a review-assisted workflow, not just a fire-and-forget batch converter.

The browser workspace supports:
- filtering records
- inspecting record details and warnings
- correcting recap labor classification
- correcting labor hour type
- correcting equipment category
- correcting normalized vendor name
- omitting records intentionally

Review changes are stored as append-only overlays on top of immutable run records. That means the durable historical artifact is:
- immutable processed run data
- one review session per run with exact revisions
- export history tied to exact review revisions

### 5. Run Library And Reopen Modes

The browser now includes a dedicated Run Library workspace for browsing prior processing runs and reopening them without the original PDF.

Supported reopen modes:
- `Latest reviewed state`
- `Original processed state`

Opening `Original processed state` first shows a revision-0 preview. If the user chooses to continue from that baseline, the system appends a new reset-to-original review revision so future edits and exports continue from the restored original state while preserving the earlier review history.

Runs can also be archived. Archived runs remain reopenable, editable, and exportable, but they stop participating in live trusted-profile drift warnings because the run row no longer keeps the live trusted-profile linkage.

### 6. Export

Export is template-driven. The tool builds a recap payload from the validated record set and writes it into the selected published profile version's recap workbook template using the configured recap template map and rates.

Export behavior is intentionally separate from parsing/normalization behavior.

## Architecture Overview

The repo is organized around a reusable product core, shared orchestration services, hosted persistence/runtime seams, and web delivery.

- `core/`
  Domain and product-engine code:
  - parsing
  - normalization
  - validation
  - export payload shaping and workbook writing
  - profile/config interpretation
  - record models and supporting helpers

- `services/`
  Workflow orchestration and lineage-aware behavior:
  - processing runs
  - review sessions and append-only edits
  - trusted-profile authoring
  - export orchestration
  - profile resolution

- `infrastructure/`
  Hosted persistence and runtime seams:
  - Postgres lineage stores
  - runtime storage implementations
  - schema and migration support
  - hosted/local composition helpers

- `api/`
  Thin FastAPI contracts over shared services:
  - uploads
  - processing runs
  - review sessions
  - exports
  - trusted profiles and profile drafts

- `web/`
  Browser delivery shell:
  - upload and processing flows
  - run library and reopen flows
  - grouped review workflow
  - export actions
  - trusted-profile settings and authoring

- `profiles/`
  Profile bundles and fixtures, including the bundled default profile in `profiles/default/`.

- `tests/`
  Focused unit and regression coverage for parser behavior, normalization rules, export behavior, profile/config loading, lineage rules, API contracts, and hosted runtime seams.

- `tools/`
  Small diagnostic utilities such as parsed-record CSV dumping.

## Config / Profile Model

### Supported Model

The current supported config model is the modern raw-first model.

For mappings, the authoritative persisted shapes are:

- labor mapping:
  - `raw_mappings`
  - `saved_mappings`

- equipment mapping:
  - `raw_mappings`
  - `saved_mappings`

Legacy compatibility shapes such as `keyword_mappings`, `phase_defaults`, `aliases`, `class_mappings`, and `apprentice_aliases` are no longer the supported model.

### Profiles

Published trusted-profile versions define the active recap behavior bundle:

- parsing/input interpretation
- phase mapping
- vendor normalization
- labor/equipment mappings
- recap slot definitions
- rates
- recap template mapping
- workbook template
- review defaults

The bundled default profile metadata lives at:
- `profiles/default/profile.json`

Filesystem profile bundles remain useful as fixtures and seed assets, but the supported operational model is persisted trusted profiles and published versions used by API workflows.

### Slot-Based Recap Handling

Labor and equipment recap classifications use fixed-capacity slot definitions rather than loose rename-by-position behavior. That gives the export layer stable slot identities even when displayed labels change.

Relevant profile-side files include:
- `target_labor_classifications.json`
- `target_equipment_classifications.json`
- `recap_template_map.json`

## Hosted Deployment Model

Production deployment is hosted-only:

- `web/` builds the browser client deployed on Vercel
- `api/` provides the ASGI app for hosted API execution
- Neon Postgres stores processing lineage, review data, and trusted-profile authoring state
- Vercel Blob stores uploaded source documents and generated artifacts

Temporary upload retention remains separate from durable run history. A staged upload blob can expire from opportunistic cleanup, but persisted processing runs, review sessions, and export lineage remain reopenable from stored data.

The supported runtime should fail clearly when required hosted configuration is missing rather than silently falling back to local-disk assumptions.

## Running Locally

Install Python dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the API locally:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.index:app --reload
```

The API now loads the repo-root `.env` automatically for local startup. Keep your real local values in `.env`.

If you ever need to force dotenv loading explicitly during troubleshooting, this fallback still works:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.index:app --reload --env-file .env
```

Run the web app locally:

```powershell
npm --prefix web install
npm --prefix web run dev
```

## Environment

Hosted verification and deployment depend on environment variables for:

- database provider and Neon Postgres connection strings
- runtime storage provider configuration
- Vercel Blob token/configuration
- any API-facing app settings required by the current hosted runtime

Use `.env.example` and the current API/runtime configuration code as the source of truth for exact variable names.

## Testing

Run the targeted Python verification used by the hosted product surface:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/repo_shape_tests.py tests/api_tests.py tests/processing_run_service_tests.py tests/review_session_service_tests.py tests/profile_authoring_service_tests.py tests/trusted_profile_authoring_repository_tests.py tests/postgres_lineage_store_tests.py tests/runtime_storage_tests.py tests/profile_config_tests.py -q
```

Run the web checks:

```powershell
npm --prefix web test
npm --prefix web run build
vercel build
```

## Current Status

This repository is a working internal hosted product with substantial parser, normalization, validation, review, lineage, trusted-profile authoring, and export behavior.

Current status in plain terms:
- hosted web/API product
- browser upload, run-library, review, export, and profile-settings workflows are active product surfaces
- review-assisted rather than fully automatic
- heavily config-driven
- template-driven Excel export
- actively hardened against real report edge cases

## Development Notes

- Prefer changes in `core/`, `services/`, and `infrastructure/` when behavior should stay reusable.
- Keep API and React layers thin; business rules belong in domain/config/service layers where possible.
- Preserve immutable processing-run, review-session, and published-profile lineage.
- Add regression tests for parser, normalization, validation, export, workflow, persistence, and hosted-runtime changes.
- Keep `AGENTS.md` and `README.md` aligned with meaningful architecture or workflow changes.

## Future Direction

This repo should be treated as a shared product engine plus a hosted web/API delivery system.

Future work should continue improving:
- web review, export, and profile-settings reliability
- shared parsing, normalization, validation, and lineage behavior
- hosted persistence and runtime storage reliability
- export portability and traceability
