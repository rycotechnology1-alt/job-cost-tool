"""Report parsing flow for converting extracted PDF text into raw Record objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from job_cost_tool.core.models.record import OTHER, Record
from job_cost_tool.core.parsing.line_classifier import (
    extract_phase_header,
    infer_record_type_from_phase,
    is_blank_line,
    is_detail_candidate,
    is_header_or_footer,
    is_phase_header,
    is_total_line,
    is_transaction_start,
)
from job_cost_tool.core.parsing.types import PDFPageData

_PROJECT_HEADER_RE = re.compile(r"^(?P<job_number>\d+)\.\s+(?P<job_name>.+?)(?:\s+-\s+Continued)?$")
_TRANSACTION_RE = re.compile(r"^(?P<transaction_type>[A-Z]{2})\s+(?P<date>\d{2}/\d{2}/\d{2})\s+(?P<body>.+)$")
_HOURS_TYPE_COST_RE = re.compile(r"(?P<body>.+?)\s+(?P<hours>\d+\.\d{2})\s+(?P<hour_type>ST|OT|DT)\s+(?P<cost>[\d,]+\.\d{2})(?:\s+|$)")
_HOURS_COST_RE = re.compile(r"(?P<body>.+?)\s+(?P<hours>\d+\.\d{2})\s+(?P<cost>[\d,]+\.\d{2})(?:\s+|$)")
_EMPLOYEE_SPLIT_RE = re.compile(r"^(?P<prefix>.*?)\s*/\s*(?P<employee_id>\d+)\s*/\s*(?P<remaining>.+)$")
_EQUIPMENT_DETAIL_RE = re.compile(r"^(?P<employee_name>.+?)\s+(?P<equipment_description>\d+/\d{4}.+?)\s*/\s*\d+\s*$")
_LABOR_TAIL_RE = re.compile(r"^(?P<employee_name>.+?)\s*\d+\s+Regular Earnings\s*$")
_CLASS_PREFIX_WITH_FACTOR_RE = re.compile(r"^(?:(?P<union_code>\d+)\s*/\s*)?(?P<labor_class_raw>.+?)\s+(?P<factor>\d+\.\d{2})$")
_CLASS_PREFIX_RE = re.compile(r"^(?P<union_code>\d+)\s*/\s*(?P<labor_class_raw>.+)$")


@dataclass(slots=True)
class _ParseContext:
    """Current parsing context derived from headers encountered in the report."""

    job_number: Optional[str] = None
    job_name: Optional[str] = None
    phase_code: Optional[str] = None
    phase_name_raw: Optional[str] = None
    record_type: str = OTHER


@dataclass(slots=True)
class _PendingLine:
    """A logical detail line assembled from one or more PDF text lines."""

    source_page: int
    text: str
    started_with_transaction: bool


def parse_report_pages(pages: List[PDFPageData]) -> List[Record]:
    """Parse extracted PDF pages into raw Record objects."""
    context = _ParseContext()
    records: List[Record] = []
    pending_line: Optional[_PendingLine] = None

    for page in pages:
        page_number = page["page_number"]
        page_text = page.get("text", "")
        for raw_line in page_text.splitlines():
            line = _normalize_line(raw_line)
            if is_blank_line(line):
                continue

            project_header = _extract_project_header(line)
            if project_header is not None:
                pending_line = _flush_pending_line(pending_line, context, records)
                context.job_number, context.job_name = project_header
                continue

            if is_phase_header(line):
                pending_line = _flush_pending_line(pending_line, context, records)
                phase_header = extract_phase_header(line)
                if phase_header is not None:
                    context.phase_code, context.phase_name_raw = phase_header
                    context.record_type = infer_record_type_from_phase(context.phase_name_raw)
                continue

            if is_total_line(line) or is_header_or_footer(line):
                pending_line = _flush_pending_line(pending_line, context, records)
                continue

            if not is_detail_candidate(line):
                continue

            if is_transaction_start(line):
                pending_line = _flush_pending_line(pending_line, context, records)
                pending_line = _PendingLine(
                    source_page=page_number,
                    text=line,
                    started_with_transaction=True,
                )
                continue

            if pending_line is not None:
                pending_line.text = f"{pending_line.text} {line}".strip()
                continue

            pending_line = _PendingLine(
                source_page=page_number,
                text=line,
                started_with_transaction=False,
            )

        pending_line = _flush_pending_line(pending_line, context, records)

    return records


def _flush_pending_line(
    pending_line: Optional[_PendingLine],
    context: _ParseContext,
    records: List[Record],
) -> None:
    """Convert the pending logical line into a Record and append it."""
    if pending_line is None:
        return None

    records.append(_build_record_from_line(pending_line, context))
    return None


def _build_record_from_line(pending_line: _PendingLine, context: _ParseContext) -> Record:
    """Build a raw Record from an assembled detail line."""
    warnings: List[str] = []
    confidence = 0.3
    record_type = context.record_type or OTHER
    raw_description = pending_line.text
    transaction_type: Optional[str] = None
    cost: Optional[float] = None
    hours: Optional[float] = None
    hour_type: Optional[str] = None
    union_code: Optional[str] = None
    labor_class_raw: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_id_raw: Optional[str] = None
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None
    equipment_description: Optional[str] = None

    if context.phase_code is None:
        warnings.append("No active phase context was identified for this line.")
    if record_type == OTHER:
        warnings.append("Section type is not yet confidently classified.")

    transaction_match = _TRANSACTION_RE.match(pending_line.text)
    if transaction_match is None:
        warnings.append("Ambiguous detail line preserved for review.")
    else:
        transaction_type = transaction_match.group("transaction_type")
        body = transaction_match.group("body").strip()
        raw_description = body

        body_without_amounts, hours, hour_type, cost = _extract_amount_fields(body)
        raw_description = body_without_amounts

        if transaction_type == "AP":
            vendor_id_raw, vendor_name = _parse_ap_source_fields(body_without_amounts)
        elif transaction_type == "PR":
            (
                union_code,
                labor_class_raw,
                employee_id,
                employee_name,
                equipment_description,
            ) = _parse_pr_source_fields(body_without_amounts)
        else:
            warnings.append(
                f"Transaction type '{transaction_type}' is not yet explicitly handled by the parser."
            )

        confidence = 0.6
        if context.phase_code and pending_line.started_with_transaction:
            confidence = 0.9 if record_type != OTHER else 0.6

    if not pending_line.started_with_transaction:
        confidence = 0.3
        warnings.append("Line did not begin with a recognized transaction marker.")

    if employee_id and employee_name is None:
        warnings.append("Employee identifier was found but employee name was not parsed cleanly.")
    if transaction_type == "AP" and vendor_id_raw and vendor_name is None:
        warnings.append("Vendor identifier was found but vendor name was not parsed cleanly.")

    return Record(
        record_type=record_type,
        phase_code=context.phase_code,
        cost=cost,
        hours=hours,
        hour_type=hour_type,
        union_code=union_code,
        labor_class_normalized=None,
        vendor_name=vendor_name,
        equipment_description=equipment_description,
        equipment_category=None,
        confidence=confidence,
        raw_description=raw_description,
        labor_class_raw=labor_class_raw,
        job_number=context.job_number,
        job_name=context.job_name,
        transaction_type=transaction_type,
        phase_name_raw=context.phase_name_raw,
        employee_id=employee_id,
        employee_name=employee_name,
        vendor_id_raw=vendor_id_raw,
        source_page=pending_line.source_page,
        source_line_text=pending_line.text,
        warnings=warnings,
    )


def _extract_project_header(line: str) -> Optional[tuple[str, str]]:
    """Extract the current job context from the project header line."""
    if "all phases" in line.casefold() or line.casefold().startswith("jobs:"):
        return None

    match = _PROJECT_HEADER_RE.match(line.strip())
    if not match:
        return None
    return match.group("job_number"), match.group("job_name").strip()


def _extract_amount_fields(body: str) -> tuple[str, Optional[float], Optional[str], Optional[float]]:
    """Extract hours, hour type, and cost from a detail body."""
    typed_match = _find_last_match(_HOURS_TYPE_COST_RE, body)
    if typed_match is not None:
        raw_description = _merge_body_segments(
            typed_match.group("body"),
            body[typed_match.end():],
        )
        return (
            raw_description,
            _to_float(typed_match.group("hours")),
            typed_match.group("hour_type"),
            _to_float(typed_match.group("cost")),
        )

    generic_match = _find_last_match(_HOURS_COST_RE, body)
    if generic_match is not None:
        raw_description = _merge_body_segments(
            generic_match.group("body"),
            body[generic_match.end():],
        )
        return (
            raw_description,
            _to_float(generic_match.group("hours")),
            None,
            _to_float(generic_match.group("cost")),
        )

    return body, None, None, None


def _parse_ap_source_fields(body: str) -> tuple[Optional[str], Optional[str]]:
    """Extract raw vendor fields from an AP detail body when possible."""
    parts = body.split(maxsplit=1)
    if not parts:
        return None, None
    if not parts[0].isdigit():
        return None, None

    vendor_id_raw = parts[0]
    remainder = parts[1] if len(parts) > 1 else ""
    vendor_name = _extract_vendor_name(remainder)
    return vendor_id_raw, vendor_name


def _extract_vendor_name(remainder: str) -> Optional[str]:
    """Extract a likely vendor name prefix from an AP detail line."""
    tokens = remainder.split()
    name_tokens: List[str] = []
    for token in tokens:
        if any(character.isdigit() for character in token):
            break
        if token.startswith("/") or token.upper().startswith("TR#"):
            break
        name_tokens.append(token)

    if not name_tokens:
        return None
    return " ".join(name_tokens)


def _parse_pr_source_fields(
    body: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract raw payroll-related fields from a PR detail body when possible."""
    match = _EMPLOYEE_SPLIT_RE.match(body)
    if not match:
        return None, None, None, None, None

    prefix = match.group("prefix").strip()
    employee_id = match.group("employee_id")
    remaining = match.group("remaining").strip()

    union_code, labor_class_raw = _parse_class_prefix(prefix)
    employee_name, equipment_description = _parse_employee_and_equipment(remaining)
    return union_code, labor_class_raw, employee_id, employee_name, equipment_description


def _parse_class_prefix(prefix: str) -> tuple[Optional[str], Optional[str]]:
    """Parse raw union and labor class hints from the leading PR segment."""
    if not prefix:
        return None, None

    match = _CLASS_PREFIX_WITH_FACTOR_RE.match(prefix)
    if match:
        return match.group("union_code"), match.group("labor_class_raw").strip()

    match = _CLASS_PREFIX_RE.match(prefix)
    if match:
        return match.group("union_code"), match.group("labor_class_raw").strip()

    return None, None


def _parse_employee_and_equipment(remaining: str) -> tuple[Optional[str], Optional[str]]:
    """Parse employee and equipment text from the remaining PR detail body."""
    equipment_match = _EQUIPMENT_DETAIL_RE.match(remaining)
    if equipment_match:
        return (
            equipment_match.group("employee_name").strip(),
            equipment_match.group("equipment_description").strip(),
        )

    labor_match = _LABOR_TAIL_RE.match(remaining)
    if labor_match:
        return labor_match.group("employee_name").strip(), None

    return remaining.strip() or None, None


def _normalize_line(line: str) -> str:
    """Normalize whitespace while preserving line semantics."""
    return re.sub(r"\s+", " ", line).strip()


def _to_float(value: str) -> Optional[float]:
    """Convert a numeric string containing optional thousands separators."""
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None

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


