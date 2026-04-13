"""Helpers for deriving and normalizing recap template metadata."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def build_template_metadata(
    raw_template_metadata: dict[str, Any] | None,
    *,
    recap_template_map: dict[str, Any],
    template_filename: str | None = None,
    template_artifact_ref: str | None = None,
    template_file_hash: str | None = None,
) -> dict[str, Any]:
    """Return one normalized template metadata payload."""
    raw_template_metadata = (
        dict(raw_template_metadata)
        if isinstance(raw_template_metadata, dict)
        else {}
    )
    resolved_template_filename = str(
        raw_template_metadata.get("template_filename")
        or template_filename
        or raw_template_metadata.get("template_artifact_ref")
        or template_artifact_ref
        or ""
    ).strip() or None
    resolved_template_artifact_ref = str(
        raw_template_metadata.get("template_artifact_ref")
        or template_artifact_ref
        or resolved_template_filename
        or ""
    ).strip() or None
    resolved_template_file_hash = str(
        raw_template_metadata.get("template_file_hash")
        or template_file_hash
        or ""
    ).strip() or None
    template_id = str(raw_template_metadata.get("template_id") or "").strip()
    if not template_id:
        template_id = _derive_template_id(
            resolved_template_filename,
            resolved_template_artifact_ref,
            resolved_template_file_hash,
        )

    display_label = str(raw_template_metadata.get("display_label") or "").strip()
    if not display_label:
        display_label = _derive_display_label(
            resolved_template_filename,
            resolved_template_artifact_ref,
            template_id,
        )

    labor_rows = _normalize_row_definitions(
        raw_template_metadata.get("labor_rows"),
        fallback_rows=recap_template_map.get("labor_rows", {}),
        row_prefix="labor_row",
    )
    equipment_rows = _normalize_row_definitions(
        raw_template_metadata.get("equipment_rows"),
        fallback_rows=recap_template_map.get("equipment_rows", {}),
        row_prefix="equipment_row",
    )
    export_behaviors = _normalize_export_behaviors(raw_template_metadata.get("export_behaviors"))

    return {
        "template_id": template_id,
        "display_label": display_label,
        "template_filename": resolved_template_filename,
        "template_artifact_ref": resolved_template_artifact_ref,
        "template_file_hash": resolved_template_file_hash,
        "labor_active_slot_capacity": len(labor_rows),
        "equipment_active_slot_capacity": len(equipment_rows),
        "labor_rows": labor_rows,
        "equipment_rows": equipment_rows,
        "export_behaviors": export_behaviors,
    }


def _normalize_row_definitions(
    raw_rows: Any,
    *,
    fallback_rows: Any,
    row_prefix: str,
) -> list[dict[str, Any]]:
    """Normalize fixed-row definitions while preserving row order."""
    normalized_rows: list[dict[str, Any]] = []
    if isinstance(raw_rows, list):
        for index, raw_row in enumerate(raw_rows, start=1):
            if not isinstance(raw_row, dict):
                continue
            mapping = raw_row.get("mapping", {})
            if not isinstance(mapping, dict) or not mapping:
                continue
            row_id = str(raw_row.get("row_id") or f"{row_prefix}_{index}").strip() or f"{row_prefix}_{index}"
            normalized_rows.append(
                {
                    "row_id": row_id,
                    "template_label": str(raw_row.get("template_label") or "").strip(),
                    "mapping": {
                        str(key): str(value).strip()
                        for key, value in mapping.items()
                        if str(value).strip()
                    },
                }
            )
    if normalized_rows:
        return normalized_rows

    fallback_mapping = fallback_rows if isinstance(fallback_rows, dict) else {}
    return [
        {
            "row_id": f"{row_prefix}_{index}",
            "template_label": str(template_label).strip(),
            "mapping": {
                str(key): str(value).strip()
                for key, value in row_mapping.items()
                if str(value).strip()
            },
        }
        for index, (template_label, row_mapping) in enumerate(fallback_mapping.items(), start=1)
        if isinstance(row_mapping, dict) and row_mapping
    ]


def _normalize_export_behaviors(raw_behaviors: Any) -> dict[str, Any]:
    """Normalize template export behavior flags."""
    normalized = dict(raw_behaviors) if isinstance(raw_behaviors, dict) else {}
    return {
        "collapse_inactive_classifications": bool(
            normalized.get("collapse_inactive_classifications", True)
        ),
    }


def _derive_template_id(
    template_filename: str | None,
    template_artifact_ref: str | None,
    template_file_hash: str | None,
) -> str:
    """Build a stable logical template id for current single-template usage."""
    for candidate in (template_filename, template_artifact_ref):
        stem = Path(str(candidate or "")).stem.strip()
        if stem:
            slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-")
            if slug:
                return slug
    if template_file_hash:
        return f"template-{str(template_file_hash).strip()[:12]}"
    return "default-recap"


def _derive_display_label(
    template_filename: str | None,
    template_artifact_ref: str | None,
    template_id: str,
) -> str:
    """Build a user-facing template label when one is not persisted."""
    for candidate in (template_filename, template_artifact_ref):
        stem = Path(str(candidate or "")).stem.strip()
        if stem:
            return stem.replace("_", " ").replace("-", " ")
    return template_id.replace("-", " ").title()
