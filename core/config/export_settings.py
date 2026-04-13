"""Helpers for normalizing and validating export-only settings."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def normalize_export_settings_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize persisted export settings into one stable shape."""
    raw_config = dict(raw_config) if isinstance(raw_config, dict) else {}
    raw_rule = raw_config.get("labor_minimum_hours", {})
    normalized_rule = _normalize_labor_minimum_hours_rule(raw_rule)
    return {
        "labor_minimum_hours": normalized_rule,
    }


def default_export_settings_editor_state() -> dict[str, Any]:
    """Return the editor-ready default export settings shape."""
    return {
        "labor_minimum_hours": {
            "enabled": False,
            "threshold_hours": "",
            "minimum_hours": "",
        }
    }


def build_export_settings_editor_state(export_settings: dict[str, Any]) -> dict[str, Any]:
    """Convert normalized export settings into editor-friendly string fields."""
    normalized = normalize_export_settings_config(export_settings)
    rule = normalized.get("labor_minimum_hours", {})
    return {
        "labor_minimum_hours": {
            "enabled": bool(rule.get("enabled")),
            "threshold_hours": _stringify_decimal(rule.get("threshold_hours")),
            "minimum_hours": _stringify_decimal(rule.get("minimum_hours")),
        }
    }


def build_export_settings_config(
    existing_settings: dict[str, Any],
    editor_state: dict[str, Any],
) -> dict[str, Any]:
    """Validate and build the persisted export settings payload."""
    next_settings = normalize_export_settings_config(existing_settings)
    raw_rule = editor_state.get("labor_minimum_hours", {}) if isinstance(editor_state, dict) else {}
    enabled = bool(raw_rule.get("enabled"))
    threshold_text = str(raw_rule.get("threshold_hours", "")).strip()
    minimum_text = str(raw_rule.get("minimum_hours", "")).strip()

    if not enabled and not threshold_text and not minimum_text:
        next_settings["labor_minimum_hours"] = {
            "enabled": False,
            "threshold_hours": None,
            "minimum_hours": None,
        }
        return next_settings

    threshold_hours = _parse_optional_decimal(threshold_text, "Labor minimum-hours threshold")
    minimum_hours = _parse_optional_decimal(minimum_text, "Labor minimum-hours value")

    if enabled:
        if threshold_hours is None or minimum_hours is None:
            raise ValueError("Labor minimum-hours export rule needs both a threshold and a minimum.")
        if threshold_hours <= 0:
            raise ValueError("Labor minimum-hours threshold must be greater than 0.")
        if minimum_hours <= 0:
            raise ValueError("Labor minimum-hours value must be greater than 0.")
        if minimum_hours < threshold_hours:
            raise ValueError("Labor minimum-hours value must be greater than or equal to the threshold.")

    next_settings["labor_minimum_hours"] = {
        "enabled": enabled,
        "threshold_hours": _to_number(threshold_hours) if threshold_hours is not None else None,
        "minimum_hours": _to_number(minimum_hours) if minimum_hours is not None else None,
    }
    return next_settings


def get_labor_minimum_hours_rule(export_settings: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized labor minimum-hours export rule."""
    normalized = normalize_export_settings_config(export_settings)
    rule = normalized.get("labor_minimum_hours", {})
    return dict(rule) if isinstance(rule, dict) else {
        "enabled": False,
        "threshold_hours": None,
        "minimum_hours": None,
    }


def _normalize_labor_minimum_hours_rule(raw_rule: Any) -> dict[str, Any]:
    """Normalize one labor minimum-hours rule payload."""
    raw_rule = dict(raw_rule) if isinstance(raw_rule, dict) else {}
    enabled = bool(raw_rule.get("enabled"))
    threshold_hours = _parse_optional_decimal(raw_rule.get("threshold_hours"), "Labor minimum-hours threshold")
    minimum_hours = _parse_optional_decimal(raw_rule.get("minimum_hours"), "Labor minimum-hours value")
    return {
        "enabled": enabled,
        "threshold_hours": _to_number(threshold_hours) if threshold_hours is not None else None,
        "minimum_hours": _to_number(minimum_hours) if minimum_hours is not None else None,
    }


def _parse_optional_decimal(value: Any, label: str) -> Decimal | None:
    """Parse one optional non-negative decimal value."""
    if value in {None, ""}:
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if parsed < 0:
        raise ValueError(f"{label} must be greater than or equal to 0.")
    return parsed


def _stringify_decimal(value: Any) -> str:
    """Return a user-editable string for a saved numeric value."""
    if value in {None, ""}:
        return ""
    return str(value)


def _to_number(value: Decimal) -> int | float:
    """Return a JSON-friendly numeric value without stringy integers."""
    integral = value.to_integral_value()
    if value == integral:
        return int(integral)
    return float(value)
