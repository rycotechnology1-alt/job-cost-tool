# Job Cost Tool

## Purpose

The Job Cost Tool is a modular Windows desktop application for processing job cost report PDFs, normalizing extracted data with business rules, supporting user review, and preparing recap output for Excel templates.

This repository currently contains the initial project scaffold only. Parsing logic, UI implementation, and Excel export behavior are intentionally deferred.

## High-Level Architecture

- `app/`: Application startup and future desktop entry points.
- `core/`: Domain-focused packages for models, parsing, normalization, validation, and configuration concerns.
- `services/`: Service-layer orchestration for parsing, normalization, and validation workflows.
- `infrastructure/`: Filesystem and external resource adapters.
- `config/`: JSON mapping files that will drive business rule behavior without hardcoding values in application logic.
- `tests/`: Automated test package for future unit and integration coverage.

## Design Notes

The system is structured as a production-oriented, modular application rather than a one-off script.

The architecture is intentionally config-driven so labor, equipment, and phase mappings can evolve through managed configuration files instead of direct code changes.

## Current Status

- Project scaffolding is in place.
- Placeholder services exist for parsing, normalization, and validation.
- No PDF parsing, UI, or Excel export logic has been implemented yet.
