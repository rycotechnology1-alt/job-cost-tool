"""Application service for review workflow orchestration outside Qt."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path

from core.config import ConfigLoader
from core.models.record import Record
from core.review_defaults import apply_default_omit_rules
from services.normalization_service import normalize_records
from services.parsing_service import parse_pdf
from services.validation_service import validate_records

EDITABLE_FIELDS = {
    "recap_labor_classification",
    "equipment_category",
    "vendor_name_normalized",
    "is_omitted",
}


@dataclass(slots=True)
class ReviewLoadResult:
    """Review workflow state produced when a source document is loaded."""

    review_records: list[Record]
    records: list[Record]
    blocking_issues: list[str]
    status_text: str


@dataclass(slots=True)
class ReviewUpdateResult:
    """Review workflow state produced after a manual record update."""

    review_records: list[Record]
    records: list[Record]
    blocking_issues: list[str]
    status_text: str


def load_review_data(
    file_path: str,
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> ReviewLoadResult:
    """Run the parse-normalize-default-omit-validate workflow for one file."""
    with _config_context(config_dir=config_dir, legacy_config_dir=legacy_config_dir):
        parsed_records = parse_pdf(file_path)
        normalized_records = normalize_records(parsed_records)
        review_rules = _build_loader(
            config_dir=config_dir,
            legacy_config_dir=legacy_config_dir,
        ).get_review_rules().get("default_omit_rules", [])
        review_records = list(apply_default_omit_rules(normalized_records, review_rules))
        records, blocking_issues = validate_records(review_records)
        return ReviewLoadResult(
            review_records=review_records,
            records=list(records),
            blocking_issues=list(blocking_issues),
            status_text=build_status_text(file_path, list(records), list(blocking_issues)),
        )


def update_review_record(
    review_records: list[Record],
    record_index: int,
    updates: dict[str, object],
    *,
    file_path: str | None = None,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> ReviewUpdateResult | None:
    """Apply one record edit, then re-run validation for the full review dataset."""
    if record_index < 0 or record_index >= len(review_records):
        return None

    allowed_updates = prepare_review_updates(
        updates,
        config_dir=config_dir,
        legacy_config_dir=legacy_config_dir,
    )
    if not allowed_updates:
        return None
    next_review_records = list(review_records)
    next_review_records[record_index] = replace(next_review_records[record_index], **allowed_updates)
    records, blocking_issues = validate_records(next_review_records)
    return ReviewUpdateResult(
        review_records=next_review_records,
        records=list(records),
        blocking_issues=list(blocking_issues),
        status_text=build_status_text(
            file_path or "current session",
            list(records),
            list(blocking_issues),
            prefix="Changes applied.",
        ),
    )


def prepare_review_updates(
    updates: dict[str, object],
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> dict[str, object]:
    """Normalize one requested review edit into the persisted overlay field set."""
    allowed_updates = _normalize_editable_updates(updates)
    if not allowed_updates:
        return {}
    _apply_slot_backed_updates(
        allowed_updates,
        config_dir=config_dir,
        legacy_config_dir=legacy_config_dir,
    )
    return allowed_updates


def load_edit_options(
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> tuple[list[str], list[str]]:
    """Load config-driven correction options for labor and equipment fields."""
    try:
        loader = _build_loader(config_dir=config_dir, legacy_config_dir=legacy_config_dir)
        labor_config = loader.get_target_labor_classifications()
        equipment_config = loader.get_target_equipment_classifications()
    except Exception:
        return [], []

    labor_options = [str(item) for item in labor_config.get("classifications", []) if str(item).strip()]
    equipment_options = [str(item) for item in equipment_config.get("classifications", []) if str(item).strip()]
    return labor_options, equipment_options


def build_status_text(
    file_path: str,
    records: list[Record],
    blocking_issues: list[str],
    prefix: str = "",
) -> str:
    """Build the high-level review status text shared by desktop and future services."""
    prefix_text = f"{prefix} " if prefix else ""
    if not records:
        return f"{prefix_text}No records found for: {file_path}".strip()

    if blocking_issues:
        return (
            f"{prefix_text}Processed {len(records)} records from {file_path}. "
            f"Export blocked by {len(blocking_issues)} issue(s)."
        ).strip()

    return f"{prefix_text}Processed {len(records)} records from {file_path}. Ready for review.".strip()


def _normalize_editable_updates(updates: dict[str, object]) -> dict[str, object]:
    """Filter and normalize record edits to the supported review fields."""
    allowed_updates: dict[str, object] = {}
    for key, value in updates.items():
        if key not in EDITABLE_FIELDS:
            continue
        if key == "is_omitted":
            allowed_updates[key] = bool(value)
        else:
            allowed_updates[key] = value if value not in {"", None} else None
    return allowed_updates


def _apply_slot_backed_updates(
    allowed_updates: dict[str, object],
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> None:
    """Resolve stable slot ids for edited labor and equipment selections."""
    try:
        loader = _build_loader(config_dir=config_dir, legacy_config_dir=legacy_config_dir)
    except Exception:
        return

    if "recap_labor_classification" in allowed_updates:
        label = str(allowed_updates.get("recap_labor_classification") or "").strip()
        if not label:
            allowed_updates["recap_labor_slot_id"] = None
        else:
            slot = loader.get_labor_slot_lookup().get(label.casefold())
            allowed_updates["recap_labor_slot_id"] = (
                str(slot.get("slot_id") or "").strip() if isinstance(slot, dict) else None
            ) or None

    if "equipment_category" in allowed_updates:
        label = str(allowed_updates.get("equipment_category") or "").strip()
        if not label:
            allowed_updates["recap_equipment_slot_id"] = None
        else:
            slot = loader.get_equipment_slot_lookup().get(label.casefold())
            allowed_updates["recap_equipment_slot_id"] = (
                str(slot.get("slot_id") or "").strip() if isinstance(slot, dict) else None
            ) or None


def _build_loader(
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
) -> ConfigLoader:
    """Build a config loader explicitly when a profile bundle was supplied."""
    resolved_config_dir = Path(config_dir).resolve() if config_dir is not None else None
    resolved_legacy_dir = Path(legacy_config_dir).resolve() if legacy_config_dir is not None else None
    return ConfigLoader(
        config_dir=resolved_config_dir,
        legacy_config_dir=resolved_legacy_dir,
    )


def _config_context(
    *,
    config_dir: str | Path | None = None,
    legacy_config_dir: str | Path | None = None,
):
    """Return an explicit config context when review processing must avoid global active-profile state."""
    if config_dir is None:
        return nullcontext()
    resolved_config_dir = Path(config_dir).resolve()
    resolved_legacy_dir = Path(legacy_config_dir).resolve() if legacy_config_dir is not None else None
    return ConfigLoader.use_explicit_context(
        config_dir=resolved_config_dir,
        legacy_config_dir=resolved_legacy_dir,
    )
