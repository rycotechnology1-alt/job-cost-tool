"""Service contract for exporting reviewed records into the recap workbook."""

from __future__ import annotations

import os
import sys
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from typing import List

from core.config import ConfigLoader
from core.export.excel_exporter import export_to_excel
from core.export.recap_mapper import build_recap_payload
from core.models.record import Record
from services.validation_service import validate_records


def _export_debug_enabled() -> bool:
    """Return True when export debug instrumentation is enabled."""
    return str(os.getenv("JOB_COST_TOOL_EXPORT_DEBUG") or "").strip().casefold() not in {"", "0", "false", "no", "off"}


def _debug_log(message: str) -> None:
    """Emit guarded export debug logging."""
    if _export_debug_enabled():
        print(f"[export-debug][export_service] {message}", file=sys.stderr, flush=True)


def _normalized_family(record: Record) -> str:
    """Return the best available normalized family label for debug summaries."""
    return str(record.record_type_normalized or record.record_type or "").strip().casefold()


def _summarize_records(records: List[Record]) -> str:
    """Build a compact debug summary of record families and PM costs."""
    family_counts = Counter(_normalized_family(record) or "<blank>" for record in records)
    pm_rows = [
        {
            "phase": record.phase_code,
            "family": _normalized_family(record),
            "cost": record.cost,
            "omitted": record.is_omitted,
            "raw": record.raw_description,
        }
        for record in records
        if _normalized_family(record) == "project_management"
    ]
    return f"module={__file__} record_count={len(records)} family_counts={dict(family_counts)} pm_rows={pm_rows}"


def export_records_to_recap(
    records: List[Record],
    template_path: str,
    output_path: str,
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> None:
    """Validate export readiness, build a recap payload, and write the recap workbook."""
    with _config_context(config_dir=config_dir, legacy_config_dir=legacy_config_dir):
        _debug_log(f"starting export template={template_path} output={output_path}")
        _debug_log(f"input {_summarize_records(records)}")
        validated_records, blocking_issues = validate_records(records)
        _debug_log(f"validated {_summarize_records(validated_records)} blocking_issues={blocking_issues}")
        if blocking_issues:
            issue_list = "\n".join(f"- {issue}" for issue in blocking_issues)
            raise ValueError(f"Export blocked until all blocking issues are resolved:\n{issue_list}")

        recap_payload = build_recap_payload(validated_records)
        export_to_excel(template_path=template_path, output_path=output_path, recap_payload=recap_payload)


def _config_context(
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
):
    """Return an explicit config context when export must avoid active-profile drift."""
    if config_dir is None:
        return nullcontext()
    resolved_config_dir = Path(config_dir).resolve()
    resolved_legacy_dir = Path(legacy_config_dir).resolve() if legacy_config_dir is not None else None
    return ConfigLoader.use_explicit_context(
        config_dir=resolved_config_dir,
        legacy_config_dir=resolved_legacy_dir,
    )
