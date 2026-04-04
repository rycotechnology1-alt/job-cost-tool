"""Report parsing flow for converting extracted PDF text into raw Record objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from core.models.record import (
    EQUIPMENT,
    LABOR,
    MATERIAL,
    OTHER,
    PROJECT_MANAGEMENT,
    SUBCONTRACTOR,
    Record,
)
from core.parsing.line_classifier import (
    extract_phase_header,
    infer_record_type_from_phase_context,
    is_blank_line,
    is_detail_candidate,
    is_header_or_footer,
    is_phase_header,
    is_total_line,
    is_transaction_start,
)
from core.parsing.tokenizer import tokenize_detail_line
from core.parsing.types import PDFPageData, TokenizationResult

_PROJECT_HEADER_RE = re.compile(r"^(?P<job_number>\d+)\.\s+(?P<job_name>.+?)(?:\s+-\s+Continued)?$")


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
    """Parse extracted PDF pages into raw Record objects.

    The current implementation intentionally flushes pending detail lines at the
    end of each page. That keeps line assembly conservative for this phase and
    avoids speculative cross-page stitching until a dedicated continuation
    strategy is implemented.
    """
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

            if is_total_line(line) or is_header_or_footer(line):
                pending_line = _flush_pending_line(pending_line, context, records)
                continue

            if is_phase_header(line):
                pending_line = _flush_pending_line(pending_line, context, records)
                phase_header = extract_phase_header(line)
                if phase_header is not None:
                    context.phase_code, context.phase_name_raw = phase_header
                    context.record_type = infer_record_type_from_phase_context(context.phase_code, context.phase_name_raw)
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
) -> Optional[_PendingLine]:
    """Convert the pending logical line into a Record and append it."""
    if pending_line is None:
        return None

    tokenized = tokenize_detail_line(
        line=pending_line.text,
        transaction_type=None,
        phase_code=context.phase_code,
        phase_name_raw=context.phase_name_raw,
    )
    if not _should_emit_record(pending_line, tokenized):
        return None

    records.append(_build_record_from_line(pending_line, context, tokenized))
    return None


def _build_record_from_line(
    pending_line: _PendingLine,
    context: _ParseContext,
    tokenized: Optional[TokenizationResult] = None,
) -> Record:
    """Build a raw Record from an assembled detail line."""
    warnings: list[str] = []
    if context.phase_code is None:
        warnings.append("No active phase context was identified for this line.")

    tokenized = tokenized or tokenize_detail_line(
        line=pending_line.text,
        transaction_type=None,
        phase_code=context.phase_code,
        phase_name_raw=context.phase_name_raw,
    )
    warnings.extend(tokenized["warnings"])

    record_type = _resolve_record_type(context.record_type, tokenized)
    if record_type == OTHER:
        warnings.append("Section type is not yet confidently classified.")

    if not pending_line.started_with_transaction:
        warnings.append("Line did not begin with a recognized transaction marker.")
        confidence = 0.3
    elif tokenized["transaction_type"] is None:
        confidence = 0.3
    elif context.phase_code and tokenized["has_meaningful_fields"] and not warnings:
        confidence = 0.9
    else:
        confidence = 0.6

    warnings = _dedupe_warnings(warnings)

    return Record(
        record_type=record_type,
        phase_code=context.phase_code,
        cost=tokenized["cost"],
        hours=tokenized["hours"],
        hour_type=tokenized["hour_type"],
        union_code=tokenized["union_code"],
        labor_class_normalized=None,
        vendor_name=tokenized["vendor_name"],
        equipment_description=tokenized["equipment_description"],
        equipment_category=None,
        confidence=confidence,
        raw_description=tokenized["raw_description"],
        labor_class_raw=tokenized["labor_class_raw"],
        job_number=context.job_number,
        job_name=context.job_name,
        transaction_type=tokenized["transaction_type"],
        phase_name_raw=context.phase_name_raw,
        employee_id=tokenized["employee_id"],
        employee_name=tokenized["employee_name"],
        vendor_id_raw=tokenized["vendor_id_raw"],
        source_page=pending_line.source_page,
        source_line_text=pending_line.text,
        warnings=warnings,
    )


def _resolve_record_type(context_record_type: str, tokenized: TokenizationResult) -> str:
    """Resolve the raw record type from phase context and tokenization hints."""
    if context_record_type != OTHER:
        return context_record_type

    tokenized_family = tokenized["line_family"]
    if tokenized_family in {LABOR, EQUIPMENT, MATERIAL, SUBCONTRACTOR, PROJECT_MANAGEMENT}:
        return tokenized_family
    return OTHER


def _should_emit_record(pending_line: _PendingLine, tokenized: TokenizationResult) -> bool:
    """Return True when an assembled line carries enough structure to keep.

    Header/filter metadata can slip past the line classifier when it is not a
    known boilerplate string. If such a line never started with a recognized
    transaction marker and tokenization found no structured fields, treat it as
    non-record report text instead of emitting a low-confidence junk record.
    """
    if pending_line.started_with_transaction:
        return True
    if tokenized["transaction_type"] is not None:
        return True
    return bool(tokenized["has_meaningful_fields"])


def _extract_project_header(line: str) -> Optional[tuple[str, str]]:
    """Extract the current job context from the project header line."""
    if "all phases" in line.casefold() or line.casefold().startswith("jobs:"):
        return None

    match = _PROJECT_HEADER_RE.match(line.strip())
    if not match:
        return None
    return match.group("job_number"), match.group("job_name").strip()


def _normalize_line(line: str) -> str:
    """Normalize whitespace while preserving line semantics."""
    return re.sub(r"\s+", " ", line).strip()


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    """Return warnings with duplicates removed while preserving order."""
    unique_warnings: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning not in seen:
            unique_warnings.append(warning)
            seen.add(warning)
    return unique_warnings
