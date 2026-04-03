"""Reusable detail-line tokenization helpers for raw job cost records."""

from __future__ import annotations

import re
from typing import Any, Optional

from job_cost_tool.core.models.record import (
    EQUIPMENT,
    LABOR,
    MATERIAL,
    OTHER,
    PERMIT,
    POLICE_DETAIL,
    PROJECT_MANAGEMENT,
    SUBCONTRACTOR,
)
from job_cost_tool.core.parsing.line_classifier import infer_record_type_from_phase_context
from job_cost_tool.core.parsing.types import TokenizationResult

_TRANSACTION_RE = re.compile(r"^(?P<transaction_type>[A-Z]{2})\s+(?P<date>\d{2}/\d{2}/\d{2})\s+(?P<body>.+)$")
_HOURS_TYPE_COST_RE = re.compile(
    r"(?P<body>.+?)\s+(?P<hours>[-+]?\d+\.\d{2})\s+(?P<hour_type>ST|OT|DT)\s+(?P<cost>[-+]?[\d,]+\.\d{2})(?:\s+|$)"
)
_HOURS_COST_RE = re.compile(
    r"(?P<body>.+?)\s+(?P<hours>[-+]?\d+\.\d{2})\s+(?P<cost>[-+]?[\d,]+\.\d{2})(?:\s+|$)"
)
_EMPLOYEE_SPLIT_RE = re.compile(r"^(?P<prefix>.*?)\s*/\s*(?P<employee_id>\d+)\s*/\s*(?P<remaining>.+)$")
_EQUIPMENT_DETAIL_RE = re.compile(
    r"^(?P<employee_name>.+?)\s+(?P<equipment_description>\d+/(?:(?:\d{4}\b)|[A-Za-z]).+?)\s*/\s*\d+\s*$"
)
_EQUIPMENT_TRAILING_COUNT_RE = re.compile(r"^(?P<equipment_description>.+?)\s*/\s*\d+\s*$")
_EQUIPMENT_FALLBACK_NAME_RE = re.compile(
    r"^(?P<employee_name>.+?,\s*[^,]+?)\s+(?P<equipment_description>.+)$"
)
_LABOR_TAIL_RE = re.compile(r"^(?P<employee_name>.+?)\s*\d+\s+Regular Earnings\s*$")
_CLASS_PREFIX_WITH_FACTOR_RE = re.compile(
    r"^(?:(?P<union_code>\d+)\s*/\s*)?(?P<labor_class_raw>.+?)\s+(?P<factor>\d+\.\d{2})$"
)
_CLASS_PREFIX_RE = re.compile(r"^(?P<union_code>\d+)\s*/\s*(?P<labor_class_raw>.+)$")
_FACTOR_ONLY_RE = re.compile(r"^\d+\.\d{2}$")
_AMOUNT_HINT_RE = re.compile(r"(?:\bST\b|\bOT\b|\bDT\b|\d+\.\d{2})")


def tokenize_detail_line(
    line: str,
    transaction_type: Optional[str],
    phase_code: Optional[str],
    phase_name_raw: Optional[str],
) -> TokenizationResult:
    """Tokenize a raw detail line and return extracted raw fields."""
    warnings: list[str] = []
    parsed_transaction_type = transaction_type
    body = line.strip()

    if parsed_transaction_type is None:
        transaction_match = _TRANSACTION_RE.match(body)
        if transaction_match is not None:
            parsed_transaction_type = transaction_match.group("transaction_type")
            body = transaction_match.group("body").strip()

    raw_description, hours, hour_type, cost, amount_warnings = _extract_amount_fields(body)
    warnings.extend(amount_warnings)

    result = _base_result(
        transaction_type=parsed_transaction_type,
        raw_description=raw_description,
        cost=cost,
        hours=hours,
        hour_type=hour_type,
        line_family=infer_record_type_from_phase_context(phase_code, phase_name_raw),
    )
    result["warnings"].extend(warnings)

    if parsed_transaction_type == "PR":
        pr_result = tokenize_pr_line(raw_description, phase_code, phase_name_raw)
        _merge_result(result, pr_result)
    elif parsed_transaction_type == "AP":
        ap_result = tokenize_ap_line(raw_description, phase_code, phase_name_raw)
        _merge_result(result, ap_result)
    elif parsed_transaction_type is None:
        result["warnings"].append("Detail line did not contain a recognized transaction marker.")
    else:
        # Unknown transaction codes still use generic phase-aware parsing.
        # Preserve the line instead of treating it as unhandled junk.
        pass

    result["parsed_field_count"] = _count_structured_fields(result)
    result["has_meaningful_fields"] = result["parsed_field_count"] > 0
    result["warnings"] = _dedupe_warnings(result["warnings"])
    return result


def tokenize_pr_line(
    line: str,
    phase_code: Optional[str],
    phase_name_raw: Optional[str],
) -> TokenizationResult:
    """Tokenize PR-style detail lines such as labor or equipment records."""
    phase_family = infer_record_type_from_phase_context(phase_code, phase_name_raw)
    result = _base_result(
        transaction_type="PR",
        raw_description=line.strip(),
        cost=None,
        hours=None,
        hour_type=None,
        line_family=phase_family,
    )

    match = _EMPLOYEE_SPLIT_RE.match(line.strip())
    if match is None:
        result["warnings"].append("PR detail line was recognized but employee structure was not parsed cleanly.")
        return result

    prefix = match.group("prefix").strip()
    result["employee_id"] = match.group("employee_id")
    remaining = match.group("remaining").strip()

    union_code, labor_class_raw = _parse_class_prefix(prefix)
    result["union_code"] = union_code
    result["labor_class_raw"] = labor_class_raw

    employee_name, equipment_description = _parse_employee_and_equipment(
        remaining,
        prefer_equipment_fallback=phase_family == EQUIPMENT,
    )
    result["employee_name"] = employee_name
    result["equipment_description"] = equipment_description

    if equipment_description is not None:
        result["line_family"] = EQUIPMENT
    elif _looks_like_labor_detail(remaining) or phase_family == LABOR:
        result["line_family"] = LABOR
    elif phase_family == EQUIPMENT:
        result["line_family"] = EQUIPMENT
    elif phase_family in {MATERIAL, SUBCONTRACTOR, PERMIT, POLICE_DETAIL, PROJECT_MANAGEMENT}:
        # Some valid report-body PR lines live under non-payroll sections such
        # as Other Job Cost. When detailed PR parsing is weak, inherit the
        # section/header family rather than downgrading the line back to an
        # ambiguous review blocker.
        result["line_family"] = phase_family
    else:
        result["line_family"] = OTHER

    if result["employee_id"] is None:
        result["warnings"].append("PR detail line was recognized but employee identifier was not parsed cleanly.")
    if result["employee_name"] is None:
        result["warnings"].append("PR detail line was recognized but employee name was not parsed cleanly.")
    if result["line_family"] == LABOR and result["labor_class_raw"] is None:
        result["warnings"].append("PR labor detail line was recognized but labor class was not parsed cleanly.")
    if result["line_family"] == EQUIPMENT and result["equipment_description"] is None:
        result["warnings"].append(
            "PR equipment detail line was recognized but equipment description was not parsed cleanly."
        )
    if result["line_family"] == OTHER:
        result["warnings"].append("PR detail line family is ambiguous and should be reviewed.")

    return result


def tokenize_ap_line(
    line: str,
    phase_code: Optional[str],
    phase_name_raw: Optional[str],
) -> TokenizationResult:
    """Tokenize AP-style detail lines such as materials or other job cost records."""
    phase_family = infer_record_type_from_phase_context(phase_code, phase_name_raw)
    result = _base_result(
        transaction_type="AP",
        raw_description=line.strip(),
        cost=None,
        hours=None,
        hour_type=None,
        line_family=phase_family if phase_family != OTHER else MATERIAL,
    )

    vendor_id_raw, vendor_name = _parse_ap_vendor_fields(line.strip())
    result["vendor_id_raw"] = vendor_id_raw
    result["vendor_name"] = vendor_name

    if result["vendor_id_raw"] is None:
        result["warnings"].append("AP detail line was recognized but vendor identifier was not parsed cleanly.")
    if result["vendor_name"] is None:
        result["warnings"].append("AP detail line was recognized but vendor name was not parsed cleanly.")

    return result


def _base_result(
    transaction_type: Optional[str],
    raw_description: str,
    cost: Optional[float],
    hours: Optional[float],
    hour_type: Optional[str],
    line_family: str,
) -> TokenizationResult:
    """Create a TokenizationResult with default values."""
    return TokenizationResult(
        transaction_type=transaction_type,
        raw_description=raw_description,
        cost=cost,
        hours=hours,
        hour_type=hour_type,
        union_code=None,
        labor_class_raw=None,
        vendor_id_raw=None,
        vendor_name=None,
        employee_id=None,
        employee_name=None,
        equipment_description=None,
        warnings=[],
        line_family=line_family,
        has_meaningful_fields=False,
        parsed_field_count=0,
    )


def _merge_result(base: TokenizationResult, incoming: TokenizationResult) -> None:
    """Merge specialized tokenization output into the base result."""
    mergeable_fields = (
        "union_code",
        "labor_class_raw",
        "vendor_id_raw",
        "vendor_name",
        "employee_id",
        "employee_name",
        "equipment_description",
    )
    for field_name in mergeable_fields:
        if incoming[field_name] is not None:
            base[field_name] = incoming[field_name]

    if incoming["line_family"] != OTHER:
        base["line_family"] = incoming["line_family"]
    base["warnings"].extend(incoming["warnings"])


def _extract_amount_fields(
    body: str,
) -> tuple[str, Optional[float], Optional[str], Optional[float], list[str]]:
    """Extract hours, hour type, and cost from a detail body."""
    warnings: list[str] = []

    typed_match = _find_last_match(_HOURS_TYPE_COST_RE, body)
    if typed_match is not None:
        raw_description = _merge_body_segments(
            typed_match.group("body"),
            body[typed_match.end() :],
        )
        return (
            raw_description,
            _to_float(typed_match.group("hours")),
            typed_match.group("hour_type"),
            _to_float(typed_match.group("cost")),
            warnings,
        )

    generic_match = _find_last_match(_HOURS_COST_RE, body)
    if generic_match is not None:
        raw_description = _merge_body_segments(
            generic_match.group("body"),
            body[generic_match.end() :],
        )
        return (
            raw_description,
            _to_float(generic_match.group("hours")),
            None,
            _to_float(generic_match.group("cost")),
            warnings,
        )

    if _AMOUNT_HINT_RE.search(body):
        warnings.append("Detail line appears to contain amount tokens but they were not parsed cleanly.")

    return body, None, None, None, warnings


def _parse_ap_vendor_fields(body: str) -> tuple[Optional[str], Optional[str]]:
    """Extract raw vendor fields from an AP detail body when possible."""
    parts = body.split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        return None, None

    vendor_id_raw = parts[0]
    remainder = parts[1] if len(parts) > 1 else ""
    vendor_name = _extract_vendor_name(remainder)
    return vendor_id_raw, vendor_name


def _extract_vendor_name(remainder: str) -> Optional[str]:
    """Extract a likely vendor name prefix from an AP detail line."""
    tokens = remainder.split()
    name_tokens: list[str] = []
    for token in tokens:
        if token.startswith("/") or token.upper().startswith("TR#"):
            break
        if any(character.isdigit() for character in token):
            break
        name_tokens.append(token)

    if not name_tokens:
        return None
    return " ".join(name_tokens)


def _parse_class_prefix(prefix: str) -> tuple[Optional[str], Optional[str]]:
    """Parse raw union and labor class hints from the leading PR segment."""
    if not prefix or _FACTOR_ONLY_RE.match(prefix):
        return None, None

    match = _CLASS_PREFIX_WITH_FACTOR_RE.match(prefix)
    if match:
        labor_class_raw = match.group("labor_class_raw").strip()
        return match.group("union_code"), labor_class_raw or None

    match = _CLASS_PREFIX_RE.match(prefix)
    if match:
        labor_class_raw = match.group("labor_class_raw").strip()
        return match.group("union_code"), labor_class_raw or None

    return None, None


def _parse_employee_and_equipment(
    remaining: str,
    *,
    prefer_equipment_fallback: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """Parse employee and equipment text from the remaining PR detail body.

    Equipment extraction is intentionally permissive when a PR line already sits
    inside an equipment phase. Equipment descriptions may start with either
    ``asset_id/4-digit-year ...`` or ``asset_id/description ...``; preserving a
    messy-but-usable raw equipment tail is safer for downstream review and
    keyword normalization than dropping the description entirely when one narrow
    detail pattern misses.
    """
    equipment_match = _EQUIPMENT_DETAIL_RE.match(remaining)
    if equipment_match:
        return (
            equipment_match.group("employee_name").strip(),
            equipment_match.group("equipment_description").strip(),
        )

    labor_match = _LABOR_TAIL_RE.match(remaining)
    if labor_match:
        return labor_match.group("employee_name").strip(), None

    stripped = remaining.strip()
    if not stripped:
        return None, None

    if prefer_equipment_fallback and not _looks_like_labor_detail(stripped):
        return _build_equipment_fallback_fields(stripped)

    return stripped, None


def _build_equipment_fallback_fields(remaining: str) -> tuple[Optional[str], Optional[str]]:
    """Return a conservative raw equipment fallback when the strict pattern misses."""
    equipment_description = remaining.strip()
    trailing_count_match = _EQUIPMENT_TRAILING_COUNT_RE.match(equipment_description)
    if trailing_count_match:
        equipment_description = trailing_count_match.group("equipment_description").strip()

    employee_name = remaining.strip()
    name_match = _EQUIPMENT_FALLBACK_NAME_RE.match(equipment_description)
    if name_match:
        employee_name = name_match.group("employee_name").strip()
        equipment_description = name_match.group("equipment_description").strip()

    return (employee_name or None), (equipment_description or None)


def _looks_like_labor_detail(remaining: str) -> bool:
    """Return True when the remaining PR text resembles a labor payroll tail."""
    if _LABOR_TAIL_RE.match(remaining):
        return True
    return "regular earnings" in remaining.casefold()


def _count_structured_fields(result: TokenizationResult) -> int:
    """Count extracted structured fields beyond the raw description."""
    field_names = (
        "cost",
        "hours",
        "hour_type",
        "union_code",
        "labor_class_raw",
        "vendor_id_raw",
        "vendor_name",
        "employee_id",
        "employee_name",
        "equipment_description",
    )
    return sum(1 for field_name in field_names if result[field_name] is not None)


def _find_last_match(pattern: re.Pattern[str], body: str) -> Optional[re.Match[str]]:
    """Return the last regex match found in a detail body."""
    matches = list(pattern.finditer(body))
    if not matches:
        return None
    return matches[-1]


def _merge_body_segments(prefix: str, suffix: str) -> str:
    """Merge description text that may appear before and after numeric columns."""
    merged = f"{prefix.strip()} {suffix.strip()}".strip()
    return re.sub(r"\s+", " ", merged)


def _to_float(value: str) -> Optional[float]:
    """Convert a numeric string containing optional thousands separators."""
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    """Return warnings with duplicates removed while preserving order."""
    unique_warnings: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning not in seen:
            unique_warnings.append(warning)
            seen.add(warning)
    return unique_warnings
