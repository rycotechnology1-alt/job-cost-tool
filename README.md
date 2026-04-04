# Job Cost Tool

## Overview

Job Cost Tool is a Python desktop recap tool for turning Vista/Viewpoint-style T&M job cost PDF reports into reviewed, export-ready Excel recap workbooks.

The current product is a hardened internal desktop MVP built with PySide6. It is not a generic OCR pipeline or a one-click "trust everything" converter. The tool parses report-body lines, preserves traceability back to the source PDF, applies config-driven normalization and validation, supports human review/correction, and then exports into a template-driven recap workbook.

## What The Tool Does

Input:
- PDF job cost detail reports

Output:
- Excel recap workbooks based on the active profile's template and recap template map

Core workflow:
1. Read and extract PDF pages.
2. Parse phase headers and transaction-like detail lines.
3. Tokenize lines into structured record fields.
4. Apply phase-aware family routing and config-driven normalization.
5. Validate recap readiness and surface blocking issues.
6. Let a user review, correct, or omit records in the desktop UI.
7. Export reviewed records into the configured recap workbook template.

## Product Principles

- Preserve raw report fidelity and traceability.
- Valid report-body lines should survive parsing unless they are intentionally omitted or clearly boilerplate.
- Phase context matters heavily for family/type routing.
- Record families are intentional and distinct.
- Export-only shaping rules should stay in export instead of leaking back into parsing or normalization.
- Configuration should drive mappings, slots, rates, and workbook behavior wherever practical.

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

The desktop UI is a review-assisted workflow, not just a fire-and-forget batch converter.

The review layer supports:
- filtering records
- inspecting record details and warnings
- correcting recap labor classification
- correcting equipment category
- correcting normalized vendor name
- omitting records intentionally

### 5. Export

Export is template-driven. The tool builds a recap payload from the validated record set and writes it into the active profile's recap workbook template using the configured recap template map and rates.

Export behavior is intentionally separate from parsing/normalization behavior.

## Architecture Overview

The repo is organized around a reusable product core plus a desktop delivery layer.

- `core/`
  Domain and product-engine code:
  - parsing
  - normalization
  - validation
  - export payload shaping and workbook writing
  - config/profile interpretation
  - record models and supporting helpers

- `services/`
  Thin orchestration layer for the main pipeline:
  - parse PDF
  - normalize records
  - validate records
  - export reviewed records

- `app/`
  PySide6 desktop UI:
  - main window
  - review workflow widgets
  - settings dialog
  - review/settings view-models

- `profiles/`
  Profile bundles. The bundled default profile lives in `profiles/default/`.

- `config/`
  Shared app-level and fallback config files. This includes app settings and shared reference config such as the phase catalog.

- `tests/`
  Focused unit/regression coverage for parser behavior, normalization rules, export behavior, profile/config loading, and review display behavior.

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

Profiles define the active recap behavior bundle:

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

In practice, profile bundles live under `profiles/<profile_name>/` and are managed through the profile system used by the desktop app.

### Slot-Based Recap Handling

Labor and equipment recap classifications now use fixed-capacity slot definitions rather than loose rename-by-position behavior. That gives the export layer stable slot identities even when displayed labels change.

Relevant profile-side files include:
- `target_labor_classifications.json`
- `target_equipment_classifications.json`
- `recap_template_map.json`

### Shared Config

Some app-level/shared files still live under `config/`, including:
- `app_settings.json`
- `phase_catalog.json`

The active profile is tracked in app settings, while the actual business bundle is the active profile under `profiles/` when available.

## Export Model

Export is driven by:

- the active profile's recap template workbook
- `recap_template_map.json`
- configured labor/equipment rates
- normalized record families and recap slot assignments

The export stack is intentionally template-driven:
- `core/export/recap_mapper.py` builds the recap payload
- `core/export/excel_exporter.py` writes workbook output

This repo does not try to infer arbitrary workbook layouts at runtime. Export behavior is explicit and profile-configured.

## Repo Structure

High-value directories and files:

- `app/main.py`: desktop entry point
- `app/window.py`: main review window
- `app/viewmodels/`: review/settings workflow coordination
- `app/widgets/`: PySide UI widgets
- `core/parsing/`: PDF page extraction, line classification, tokenizer, report parser
- `core/normalization/`: labor, equipment, material, and family normalization
- `core/validation/`: export-readiness validation rules
- `core/export/`: recap payload mapping and workbook writing
- `core/config/`: profile/config loading, slot handling, profile management
- `services/`: thin pipeline orchestration
- `profiles/default/`: bundled default profile
- `config/`: shared app/fallback config
- `tests/`: regression-focused automated coverage
- `tools/debug_dump_parsed_records.py`: diagnostic parser dump utility

## Running Locally

Install dependencies:

```powershell
pip install -r requirements.txt
```

Launch the desktop app:

```powershell
python -m app.main
```

## Testing

Run the full test suite:

```powershell
python -m unittest discover -s tests -p "*_tests.py"
```

Common focused suites include:

```powershell
python -m unittest tests.report_parser_tests tests.tokenizer_tests tests.normalization_tests tests.export_tests
python -m unittest tests.profile_config_tests
```

## Current Status

This repository is no longer an early scaffold. It is a working, hardened desktop MVP with substantial real-world parser, normalization, validation, review, and export behavior.

Current status in plain terms:
- desktop-first internal tool
- review-assisted rather than fully automatic
- heavily config-driven
- template-driven Excel export
- actively hardened against real report edge cases
- not migrated to a web product

## Current Limitations

- The tool still depends on report text quality from PDF extraction.
- Human review is still an intentional part of the workflow.
- Export is designed around configured recap templates, not arbitrary workbook discovery.
- The long-term web direction is still future-facing; the current product is a desktop application.
- Some cleanup/refactor opportunities may remain, but the supported runtime model is the modern raw-first/slot-based model reflected in the current configs and tests.

## Development Notes

- Prefer changes in `core/` and `services/` when behavior should remain portable to a future web architecture.
- Keep PySide widget code thin; business rules belong in domain/config/service layers where possible.
- Add regression tests for parser, normalization, validation, export, and config-loading changes.
- Keep `docs/transition_tracker.md` current for meaningful architecture/workflow changes.

## Future Direction

This repo should be treated as a valuable desktop delivery layer around a reusable product engine.

The current desktop tool remains the production focus, but future work should continue improving:
- parsing reliability
- config/profile abstractions
- normalization and validation coverage
- export portability
- separation between domain logic, orchestration, and UI

The future web direction is aspirational, not already implemented.
