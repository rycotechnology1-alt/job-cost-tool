"""Helpers for profile-driven default omit behavior in review workflows."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from job_cost_tool.core.models.record import Record

JsonDict = dict[str, Any]


def canonicalize_phase_code(value: object) -> str:
    """Return a conservative normalized phase-code string for rule matching."""
    return " ".join(str(value or "").strip().split())


def normalize_review_rules_config(loaded_config: JsonDict) -> JsonDict:
    """Normalize review-rule config into a stable in-memory shape.

    The first MVP only supports matching by phase_code, but the rule object
    structure is intentionally kept as a list of objects so it can grow
    without redesigning the profile config shape later.
    """
    normalized_config = dict(loaded_config)
    raw_rules = loaded_config.get("default_omit_rules", [])
    normalized_rules: list[JsonDict] = []
    seen_phase_codes: set[str] = set()

    if isinstance(raw_rules, list):
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            phase_code = canonicalize_phase_code(rule.get("phase_code"))
            if not phase_code:
                continue
            normalized_key = phase_code.casefold()
            if normalized_key in seen_phase_codes:
                continue
            seen_phase_codes.add(normalized_key)
            normalized_rules.append({"phase_code": phase_code})

    normalized_config["default_omit_rules"] = normalized_rules
    return normalized_config


def record_matches_default_omit_rule(record: Record, rule: JsonDict) -> bool:
    """Return True when a normalized record matches one default-omit rule."""
    phase_code = canonicalize_phase_code(rule.get("phase_code"))
    if phase_code:
        return canonicalize_phase_code(record.phase_code).casefold() == phase_code.casefold()
    return False


def apply_default_omit_rules(records: list[Record], rules: list[JsonDict]) -> list[Record]:
    """Return records with the existing omit flag set for matching review rules."""
    if not rules:
        return list(records)

    updated_records: list[Record] = []
    for record in records:
        should_omit = any(record_matches_default_omit_rule(record, rule) for rule in rules)
        if should_omit and not record.is_omitted:
            updated_records.append(replace(record, is_omitted=True))
        else:
            updated_records.append(record)
    return updated_records
