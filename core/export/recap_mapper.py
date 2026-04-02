"""Build recap-oriented export payloads from validated normalized records."""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.config.classification_slots import build_slot_lookup, get_active_slots
from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER, PERMIT, POLICE_DETAIL, SUBCONTRACTOR, Record
from job_cost_tool.core.phase_codes import canonicalize_phase_code

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


@lru_cache(maxsize=1)
def _get_active_labor_slots() -> list[dict[str, Any]]:
    """Return active labor slots keyed by stable slot id and current label."""
    config = ConfigLoader().get_target_labor_classifications()
    return get_active_slots(config, slot_prefix="labor")


@lru_cache(maxsize=1)
def _get_active_equipment_slots() -> list[dict[str, Any]]:
    """Return active equipment slots keyed by stable slot id and current label."""
    config = ConfigLoader().get_target_equipment_classifications()
    return get_active_slots(config, slot_prefix="equipment")


@lru_cache(maxsize=1)
def _get_active_labor_slot_lookup() -> dict[str, dict[str, Any]]:
    """Return active labor slot lookup by current label."""
    return build_slot_lookup(_get_active_labor_slots())


@lru_cache(maxsize=1)
def _get_active_equipment_slot_lookup() -> dict[str, dict[str, Any]]:
    """Return active equipment slot lookup by current label."""
    return build_slot_lookup(_get_active_equipment_slots())


@lru_cache(maxsize=1)
def _get_rates() -> dict[str, Any]:
    """Return the configured rate bundle for the active profile."""
    return ConfigLoader().get_rates()


@lru_cache(maxsize=1)
def _get_material_section_capacity() -> int:
    """Return the current template capacity for material vendor rows."""
    mapping = ConfigLoader().get_recap_template_map()
    section_mapping = mapping.get("materials_section", {}) if isinstance(mapping.get("materials_section"), dict) else {}
    try:
        start_row = int(section_mapping["start_row"])
        end_row = int(section_mapping["end_row"])
    except (KeyError, TypeError, ValueError):
        return 0
    return max(0, end_row - start_row + 1)


def build_recap_payload(records: list[Record]) -> dict[str, Any]:
    """Build recap-oriented aggregated output from validated normalized records."""
    if not records:
        raise ValueError("There are no reviewed records available for export.")

    included_records = [record for record in records if not record.is_omitted]
    _validate_records_for_export(included_records)

    labor_values = _build_labor_values(included_records)
    equipment_values = _build_equipment_values(included_records)
    materials_values = _build_material_values(included_records)
    subcontractor_values = _build_subcontractor_values(included_records)
    permits_values = _build_permit_values(included_records)
    police_values = _build_police_values(included_records)

    return {
        "header": _build_header_values(records),
        "labor": labor_values,
        "labor_rates": _build_labor_rate_values(),
        "equipment": equipment_values,
        "equipment_rates": _build_equipment_rate_values(),
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
            slot_id = _resolve_labor_slot_id(record)
            if not classification:
                raise ValueError(_record_error(record, "Recap labor classification is missing."))
            if classification not in valid_labor_targets:
                raise ValueError(
                    _record_error(record, f"Recap labor classification '{classification}' is not a configured target.")
                )
            if not slot_id:
                raise ValueError(_record_error(record, "Recap labor slot is missing or inactive."))
            if record.hours is None:
                raise ValueError(_record_error(record, "Labor hours are missing for export."))
            hour_type = (record.hour_type or "").strip().upper()
            if not hour_type:
                raise ValueError(_record_error(record, "Labor hour type is missing for export."))
            if hour_type not in _ALLOWED_HOUR_TYPES:
                raise ValueError(_record_error(record, f"Unsupported labor hour type '{record.hour_type}'."))
        elif family == EQUIPMENT:
            category = (record.equipment_category or "").strip()
            slot_id = _resolve_equipment_slot_id(record)
            if not category:
                raise ValueError(_record_error(record, "Equipment recap category is missing."))
            if category not in valid_equipment_targets:
                raise ValueError(
                    _record_error(record, f"Equipment category '{category}' is not a configured target.")
                )
            if not slot_id:
                raise ValueError(_record_error(record, "Equipment recap slot is missing or inactive."))
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
    """Aggregate labor hours by stable labor slot id and hour type."""
    labor_totals: OrderedDict[str, dict[str, Decimal]] = OrderedDict()

    for record in records:
        if _normalized_family(record) != LABOR:
            continue

        slot_id = _resolve_labor_slot_id(record)
        if not slot_id:
            continue
        hour_type = str(record.hour_type).strip().upper()

        if slot_id not in labor_totals:
            labor_totals[slot_id] = {"ST": Decimal("0"), "OT": Decimal("0"), "DT": Decimal("0")}
        labor_totals[slot_id][hour_type] += Decimal(str(record.hours))

    return {
        slot_id: {hour_type: _to_number(value) for hour_type, value in totals.items()}
        for slot_id, totals in labor_totals.items()
    }


def _build_labor_rate_values() -> dict[str, dict[str, float]]:
    """Return configured labor rates keyed by stable labor slot id."""
    rates_bundle = _get_rates()
    raw_labor_rates = rates_bundle.get("labor_rates", {}) if isinstance(rates_bundle.get("labor_rates"), dict) else {}

    payload: dict[str, dict[str, float]] = {}
    for slot in _get_active_labor_slots():
        label = str(slot.get("label") or "").strip()
        slot_id = str(slot.get("slot_id") or "").strip()
        if not label or not slot_id:
            continue
        raw_entry = raw_labor_rates.get(label)
        if raw_entry is None:
            continue

        if isinstance(raw_entry, dict):
            standard_rate = _coerce_optional_rate(raw_entry.get("standard_rate"), f"{label} standard rate")
            overtime_rate = _coerce_optional_rate(raw_entry.get("overtime_rate"), f"{label} overtime rate")
            double_time_rate = _coerce_optional_rate(raw_entry.get("double_time_rate"), f"{label} double time rate")
        else:
            standard_rate = _coerce_optional_rate(raw_entry, f"{label} standard rate")
            overtime_rate = None
            double_time_rate = None

        rate_values: dict[str, float] = {}
        if standard_rate is not None:
            rate_values["ST"] = standard_rate
        if overtime_rate is not None:
            rate_values["OT"] = overtime_rate
        if double_time_rate is not None:
            rate_values["DT"] = double_time_rate
        if rate_values:
            payload[slot_id] = rate_values

    return payload


def _build_equipment_values(records: list[Record]) -> dict[str, float]:
    """Aggregate equipment hours or quantities by stable equipment slot id."""
    equipment_totals: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _normalized_family(record) != EQUIPMENT:
            continue

        slot_id = _resolve_equipment_slot_id(record)
        if not slot_id:
            continue
        equipment_totals.setdefault(slot_id, Decimal("0"))
        equipment_totals[slot_id] += Decimal(str(record.hours))

    return {slot_id: _to_number(value) for slot_id, value in equipment_totals.items()}


def _build_equipment_rate_values() -> dict[str, float]:
    """Return configured equipment rates keyed by stable equipment slot id."""
    rates_bundle = _get_rates()
    raw_equipment_rates = (
        rates_bundle.get("equipment_rates", {})
        if isinstance(rates_bundle.get("equipment_rates"), dict)
        else {}
    )

    payload: dict[str, float] = {}
    for slot in _get_active_equipment_slots():
        label = str(slot.get("label") or "").strip()
        slot_id = str(slot.get("slot_id") or "").strip()
        if not label or not slot_id:
            continue
        raw_entry = raw_equipment_rates.get(label)
        if raw_entry is None:
            continue
        if isinstance(raw_entry, dict):
            rate = _coerce_optional_rate(raw_entry.get("rate"), f"{label} equipment rate")
        else:
            rate = _coerce_optional_rate(raw_entry, f"{label} equipment rate")
        if rate is not None:
            payload[slot_id] = rate

    return payload


def _build_material_values(records: list[Record]) -> list[dict[str, Any]]:
    """Aggregate material-oriented records by normalized vendor name.

    Material vendor export order is explicit: vendors keep the order of first
    appearance in the reviewed record list so overflow preservation is stable
    and predictable across repeated exports of the same inputs.
    """
    vendor_order: list[str] = []
    material_totals: dict[str, Decimal] = {}

    for record in records:
        if _infer_list_section(record) != "materials":
            continue

        vendor_name = (record.vendor_name_normalized or record.vendor_name or "").strip()
        if vendor_name not in material_totals:
            vendor_order.append(vendor_name)
            material_totals[vendor_name] = Decimal("0")
        material_totals[vendor_name] += Decimal(str(record.cost))

    rows = [
        {"name": vendor_name, "amount": _to_number(material_totals[vendor_name])}
        for vendor_name in vendor_order
    ]
    return _collapse_material_overflow_rows(rows, _get_material_section_capacity())


def _collapse_material_overflow_rows(rows: list[dict[str, Any]], capacity: int) -> list[dict[str, Any]]:
    """Collapse vendor overflow into the template's final material row.

    This is an export-only shaping rule driven by the current template
    capacity. It preserves the first capacity-1 vendor rows and combines all
    remaining vendors into the final available row as ``Additional Vendors``.
    """
    if capacity <= 0 or len(rows) <= capacity:
        return rows

    preserved_rows = rows[: max(0, capacity - 1)]
    overflow_rows = rows[max(0, capacity - 1) :]
    overflow_amount = sum(Decimal(str(row.get("amount", 0) or 0)) for row in overflow_rows)
    preserved_rows.append({"name": "Additional Vendors", "amount": _to_number(overflow_amount)})
    return preserved_rows


def _build_subcontractor_values(records: list[Record]) -> list[dict[str, Any]]:
    """Group subcontractor-oriented records into recap rows.

    The export currently leaves subcontractor descriptions blank on purpose.
    We still keep the underlying raw description available on records and in the
    grouping key so future richer export behavior can opt back into it without
    changing parsing or normalization.
    """
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
        {"name": name, "description": "", "amount": _to_number(amount)}
        for (name, _description), amount in grouped_values.items()
    ]


def _build_permit_values(records: list[Record]) -> list[dict[str, Any]]:
    """Group permit and fee records into recap rows.

    Permit rows should prefer a parsed vendor/display name when one exists.
    Raw description remains the conservative fallback for traceability when a
    permit-style record does not carry a usable vendor name.
    """
    grouped_values: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _infer_list_section(record) != "permits_fees":
            continue

        description = (
            (record.vendor_name_normalized or record.vendor_name or "").strip()
            or (record.raw_description or "").strip()
        )
        grouped_values.setdefault(description, Decimal("0"))
        grouped_values[description] += Decimal(str(record.cost))

    return [
        {"description": description, "amount": _to_number(amount)}
        for description, amount in grouped_values.items()
    ]


def _build_police_values(records: list[Record]) -> list[dict[str, Any]]:
    """Group police-detail records into recap rows.

    Police-detail rows should prefer a parsed vendor/display name when one
    exists. Raw description remains the conservative fallback when vendor data
    is unavailable.
    """
    grouped_values: OrderedDict[str, Decimal] = OrderedDict()

    for record in records:
        if _infer_list_section(record) != POLICE_DETAIL:
            continue

        description = (
            (record.vendor_name_normalized or record.vendor_name or "").strip()
            or (record.raw_description or "").strip()
        )
        grouped_values.setdefault(description, Decimal("0"))
        grouped_values[description] += Decimal(str(record.cost))

    return [
        {"description": description, "amount": _to_number(amount)}
        for description, amount in grouped_values.items()
    ]


def _resolve_labor_slot_id(record: Record) -> Optional[str]:
    """Resolve the active labor slot id for a record."""
    slot_id = str(record.recap_labor_slot_id or "").strip()
    if slot_id:
        return slot_id
    label = str(record.recap_labor_classification or "").strip()
    if not label:
        return None
    slot = _get_active_labor_slot_lookup().get(label.casefold())
    if not slot:
        return None
    return str(slot.get("slot_id") or "").strip() or None


def _resolve_equipment_slot_id(record: Record) -> Optional[str]:
    """Resolve the active equipment slot id for a record."""
    slot_id = str(record.recap_equipment_slot_id or "").strip()
    if slot_id:
        return slot_id
    label = str(record.equipment_category or "").strip()
    if not label:
        return None
    slot = _get_active_equipment_slot_lookup().get(label.casefold())
    if not slot:
        return None
    return str(slot.get("slot_id") or "").strip() or None


def _infer_list_section(record: Record) -> Optional[str]:
    """Infer the recap list section for non-fixed-row export content."""
    family = _normalized_family(record)
    if family == MATERIAL or (
        family not in {LABOR, EQUIPMENT, SUBCONTRACTOR, PERMIT, POLICE_DETAIL}
        and canonicalize_phase_code(record.phase_code) == "50"
    ):
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


def _coerce_optional_rate(value: Any, label: str) -> float | None:
    """Convert a configured optional rate to a numeric export value."""
    if value in {None, ""}:
        return None
    try:
        decimal_value = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Configured rate '{label}' must be numeric.") from exc
    return _to_number(decimal_value)


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
