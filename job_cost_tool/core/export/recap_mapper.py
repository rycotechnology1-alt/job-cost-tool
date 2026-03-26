"""Build recap-oriented export payloads from validated normalized records."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER, PERMIT, SUBCONTRACTOR, Record

POLICE_DETAIL = "police_detail"
_ALLOWED_HOUR_TYPES = {"ST", "OT", "DT"}
_SUPPORTED_FAMILIES = {LABOR, EQUIPMENT, MATERIAL, SUBCONTRACTOR, PERMIT, POLICE_DETAIL}


@lru_cache(maxsize=1)
def _get_target_labor_classifications() -> set[str]:
    """Return the configured target labor recap classifications."""
    config = ConfigLoader().get_target_labor_classifications()
    return {str(item).strip() for item in config.get("classifications", []) if str(item).strip()}


@lru_cache(maxsize=1)
def _get_target_equipment_classifications() -> set[str]:
    """Return the configured target equipment recap classifications."""
    config = ConfigLoader().get_target_equipment_classifications()
    return {str(item).strip() for item in config.get("classifications", []) if str(item).strip()}


def build_recap_payload(records: list[Record]) -> dict[str, Any]:
    """Build recap-oriented aggregated output from validated normalized records."""
    if not records:
        raise ValueError("There are no reviewed records available for export.")

    _validate_records_for_export(records)

    labor_values = _build_labor_values(records)
    equipment_values = _build_equipment_values(records)
    materials_values = _build_material_values(records)
    subcontractor_values = _build_subcontractor_values(records)
    permits_values = _build_permit_values(records)
    police_values = _build_police_values(records)

    return {
        "header": _build_header_values(records),
        "labor": labor_values,
        "equipment": equipment_values,
        "materials": materials_values,
        "subcontractors": subcontractor_values,
        "permits_fees": permits_values,
        "police_detail": police_values,
    }


def _validate_records_for_export(records: list[Record]) -> None:
    """Validate that each reviewed record can be expressed in the recap payload."""
    valid_labor_targets = _get_target_labor_classifications()
    valid_equipment_targets = _get_target_equipment_classifications()

    for record in records:
        family = _normalized_family(record)
        if family in {"", OTHER}:
            raise ValueError(_record_error(record, "Record family is unresolved and cannot be exported."))
        if family not in _SUPPORTED_FAMILIES:
            raise ValueError(
                _record_error(record, f"Record family '{family}' is not supported by the recap export workflow.")
            )

        if family == LABOR:
            classification = (record.recap_labor_classification or "").strip()
            if not classification:
                raise ValueError(_record_error(record, "Recap labor classification is missing."))
            if classification not in valid_labor_targets:
                raise ValueError(
                    _record_error(record, f"Recap labor classification '{classification}' is not a configured target.")
                )
            if record.hours is None:
                raise ValueError(_record_error(record, "Labor hours are missing for export."))
            hour_type = (record.hour_type or "").strip().upper()
            if hour_type not in _ALLOWED_HOUR_TYPES:
                raise ValueError(_record_error(record, f"Unsupported labor hour type '{record.hour_type}'."))
        elif family == EQUIPMENT:
            category = (record.equipment_category or "").strip()
            if not category:
                raise ValueError(_record_error(record, "Equipment recap category is missing."))
            if category not in valid_equipment_targets:
                raise ValueError(
                    _record_error(record, f"Equipment category '{category}' is not a configured target.")
                )
            if record.hours is None:
                raise ValueError(_record_error(record, "Equipment hours or quantity are missing for export."))
        elif family == MATERIAL:
            vendor_name = (record.vendor_name_normalized or record.vendor_name or "").strip()
            if not vendor_name:
                raise ValueError(_record_error(record, "Material vendor name is missing for export."))
            if record.cost is None:
                raise ValueError(_record_error(record, "Material amount is missing for export."))
        elif family == SUBCONTRACTOR:
            if not (record.vendor_name_normalized or record.vendor_name or "").strip():
                raise ValueError(_record_error(record, "Subcontractor name is missing for export."))
            if not (record.raw_description or "").strip():
                raise ValueError(_record_error(record, "Subcontractor description is missing for export."))
            if record.cost is None:
                raise ValueError(_record_error(record, "Subcontractor amount is missing for export."))
        elif family == PERMIT:
            if not (record.raw_description or "").strip():
                raise ValueError(_record_error(record, "Permit or fee description is missing for export."))
            if record.cost is None:
                raise ValueError(_record_error(record, "Permit or fee amount is missing for export."))
        elif family == POLICE_DETAIL:
            if not (record.raw_description or "").strip():
                raise ValueError(_record_error(record, "Police detail description is missing for export."))
            if record.cost is None:
                raise ValueError(_record_error(record, "Police detail amount is missing for export."))


def _build_header_values(records: list[Record]) -> dict[str, Optional[str]]:
    """Build header values that are actually known from the reviewed record set."""
    job_number = _get_single_consistent_value(records, "job_number")
    job_name = _get_single_consistent_value(records, "job_name")

    return {
        "project": job_name,
        "description": None,
        "prepared_by": None,
        "job_number": job_number,
        "date": None,
        "report_or_co_number": None,
    }


def _build_labor_values(records: list[Record]) -> dict[str, dict[str, float]]:
    """Aggregate labor hours by recap labor classification and hour type."""
    labor_totals: OrderedDict[str, dict[str, Decimal]] = OrderedDict()

    for record in records:
        if _normalized_family(record) != LABOR:
            continue

        classification = str(record.recap_labor_classification).strip()
        hour_type = str(record.hour_type).strip().upper()

        if classification not in labor_totals:
            labor_totals[classification] = {"ST": Decimal("0"), "OT": Decimal("0"), "DT": Decimal("0")}
        labor_totals[classification][hour_type] += Decimal(str(record.hours))

    return {
        classification: {hour_type: _to_number(value) for hour_type, value in totals.items()}
        for classification, totals in labor_totals.items()
    }


def _build_equipment_values(records: list[Record]) -> dict[str, float]:
    """Aggregate equipment hours or quantities by recap equipment category."""
    equipment_totals: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _normalized_family(record) != EQUIPMENT:
            continue

        category = str(record.equipment_category).strip()
        equipment_totals.setdefault(category, Decimal("0"))
        equipment_totals[category] += Decimal(str(record.hours))

    return {category: _to_number(value) for category, value in equipment_totals.items()}


def _build_material_values(records: list[Record]) -> list[dict[str, Any]]:
    """Aggregate material-oriented records by normalized vendor name."""
    material_totals: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _infer_list_section(record) != "materials":
            continue

        vendor_name = (record.vendor_name_normalized or record.vendor_name or "").strip()
        material_totals.setdefault(vendor_name, Decimal("0"))
        material_totals[vendor_name] += Decimal(str(record.cost))

    return [
        {"name": vendor_name, "amount": _to_number(amount)}
        for vendor_name, amount in material_totals.items()
    ]


def _build_subcontractor_values(records: list[Record]) -> list[dict[str, Any]]:
    """Group subcontractor-oriented records into recap rows."""
    grouped_values: OrderedDict[tuple[str, str], Decimal] = OrderedDict()

    for record in records:
        if _infer_list_section(record) != "subcontractors":
            continue

        name = (record.vendor_name_normalized or record.vendor_name or "").strip()
        description = (record.raw_description or "").strip()
        key = (name, description)
        grouped_values.setdefault(key, Decimal("0"))
        grouped_values[key] += Decimal(str(record.cost))

    return [
        {"name": name, "description": description, "amount": _to_number(amount)}
        for (name, description), amount in grouped_values.items()
    ]


def _build_permit_values(records: list[Record]) -> list[dict[str, Any]]:
    """Group permit and fee records into recap rows."""
    grouped_values: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _infer_list_section(record) != "permits_fees":
            continue

        description = (record.raw_description or "").strip()
        grouped_values.setdefault(description, Decimal("0"))
        grouped_values[description] += Decimal(str(record.cost))

    return [
        {"description": description, "amount": _to_number(amount)}
        for description, amount in grouped_values.items()
    ]


def _build_police_values(records: list[Record]) -> list[dict[str, Any]]:
    """Group police-detail records into recap rows."""
    grouped_values: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _infer_list_section(record) != POLICE_DETAIL:
            continue

        description = (record.raw_description or "").strip()
        grouped_values.setdefault(description, Decimal("0"))
        grouped_values[description] += Decimal(str(record.cost))

    return [
        {"description": description, "amount": _to_number(amount)}
        for description, amount in grouped_values.items()
    ]


def _infer_list_section(record: Record) -> Optional[str]:
    """Infer the recap list section for non-fixed-row export content."""
    family = _normalized_family(record)
    if family == MATERIAL or (family not in {LABOR, EQUIPMENT, SUBCONTRACTOR, PERMIT, POLICE_DETAIL} and record.phase_code == "50"):
        return "materials"
    if family == SUBCONTRACTOR:
        return "subcontractors"
    if family == POLICE_DETAIL:
        return POLICE_DETAIL
    if family == PERMIT:
        description = (record.raw_description or "").casefold()
        return POLICE_DETAIL if "police" in description else "permits_fees"
    return None


def _normalized_family(record: Record) -> str:
    """Return the normalized family label for downstream export decisions."""
    return (record.record_type_normalized or record.record_type or "").strip().casefold()


def _get_single_consistent_value(records: list[Record], attribute_name: str) -> Optional[str]:
    """Return one consistent non-empty attribute value across all records."""
    values = {
        str(value).strip()
        for record in records
        if (value := getattr(record, attribute_name)) not in {None, ""}
        and str(value).strip()
    }
    if not values:
        return None
    if len(values) > 1:
        joined_values = ", ".join(sorted(values))
        raise ValueError(
            f"Export header field '{attribute_name}' has multiple conflicting values: {joined_values}"
        )
    return next(iter(values))


def _to_number(value: Decimal) -> int | float:
    """Return a numeric export value without converting integers to stringy floats."""
    integral_value = value.to_integral_value()
    if value == integral_value:
        return int(integral_value)
    return float(value)


def _record_error(record: Record, message: str) -> str:
    """Build a human-readable export error for one record."""
    page_label = f"page {record.source_page}" if record.source_page is not None else "unknown page"
    phase_label = record.phase_code or "unknown phase"
    description = (record.raw_description or record.source_line_text or "record").strip()
    return f"Record on {page_label} (phase {phase_label}): {message} Source: {description}"
