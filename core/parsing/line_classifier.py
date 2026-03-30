"""Heuristics for classifying lines extracted from job cost report PDFs."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Optional

from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.core.models.record import EQUIPMENT, LABOR, MATERIAL, OTHER, SUBCONTRACTOR

_PHASE_HEADER_RE = re.compile(
    r"^(?P<phase_code>\d{1,3})(?:\s*\.\s*\d{1,3}\s*\.)?(?:\s*\.\s*){0,2}\s+(?P<phase_name>[A-Za-z].+?)\s*$"
)
_PAGE_FOOTER_RE = re.compile(r"\bPage\s+\d+\s+\d{2}/\d{2}/\d{2}\b", re.IGNORECASE)
_ALWAYS_SUPPORTED_TRANSACTION_TYPES = ("JC",)


@lru_cache(maxsize=1)
def _get_input_model() -> dict[str, Any]:
    """Return the cached input model configuration."""
    return ConfigLoader().get_input_model()


@lru_cache(maxsize=1)
def _get_transaction_types() -> tuple[str, ...]:
    """Return configured transaction type markers plus globally supported corrections.

    JC entries are review-relevant correction lines and must always act as a
    record boundary, even for older profiles whose input_model.json predates
    explicit JC support.
    """
    transaction_types = _get_input_model().get("transaction_types", [])
    configured = [] if not isinstance(transaction_types, list) else [str(item).upper() for item in transaction_types]

    ordered_markers: list[str] = []
    for marker in [*configured, *_ALWAYS_SUPPORTED_TRANSACTION_TYPES]:
        if marker and marker not in ordered_markers:
            ordered_markers.append(marker)
    return tuple(ordered_markers)


@lru_cache(maxsize=1)
def _get_ignore_patterns() -> tuple[str, ...]:
    """Return configured ignore patterns normalized for comparisons."""
    ignore_patterns = _get_input_model().get("ignore_patterns", [])
    if not isinstance(ignore_patterns, list):
        return tuple()
    return tuple(str(item).strip().casefold() for item in ignore_patterns if str(item).strip())


@lru_cache(maxsize=1)
def _get_section_headers() -> dict[str, tuple[str, ...]]:
    """Return configured section header names by section family."""
    raw_section_headers = _get_input_model().get("section_headers", {})
    if not isinstance(raw_section_headers, dict):
        return {}
    return {
        str(section_name).casefold(): tuple(str(value).casefold() for value in values)
        for section_name, values in raw_section_headers.items()
        if isinstance(values, list)
    }


def is_blank_line(line: str) -> bool:
    """Return True when a line is empty or only whitespace."""
    return not line.strip()


def is_header_or_footer(line: str) -> bool:
    """Return True when a line is confidently report boilerplate."""
    normalized_line = line.strip()
    if not normalized_line:
        return False

    folded = normalized_line.casefold()
    boilerplate_prefixes = (
        "dec - jc detail",
        "jobs:",
        "all months dates:",
        "project manager -",
        "trans actual",
        "type date description hours cost",
        "date format -",
    )
    if folded.startswith(boilerplate_prefixes):
        return True
    if folded.endswith("viewpoint remote .rpt"):
        return True
    if _PAGE_FOOTER_RE.search(normalized_line):
        return True
    return any(_matches_ignore_pattern(folded, pattern) for pattern in _get_ignore_patterns())


def is_total_line(line: str) -> bool:
    """Return True when a line is a subtotal or total line."""
    folded = line.strip().casefold()
    if not folded:
        return False
    total_markers = (
        "total for phase:",
        "total for job:",
        "total for company:",
        "grand total",
        "subtotal",
    )
    return folded.startswith(total_markers)


def extract_phase_header(line: str) -> Optional[tuple[str, str]]:
    """Return the phase code and phase name when a line is a phase header."""
    normalized_line = line.strip()
    if not normalized_line or is_header_or_footer(normalized_line) or is_total_line(normalized_line):
        return None

    match = _PHASE_HEADER_RE.match(normalized_line)
    if not match:
        return None
    return match.group("phase_code"), match.group("phase_name").strip()


def is_phase_header(line: str) -> bool:
    """Return True when a line appears to be a phase header."""
    return extract_phase_header(line) is not None


def is_transaction_start(line: str) -> bool:
    """Return True when a line starts with a configured transaction type marker."""
    normalized_line = line.strip()
    return any(normalized_line.startswith(f"{marker} ") for marker in _get_transaction_types())


def infer_record_type_from_phase(phase_name: Optional[str]) -> str:
    """Infer a raw record family from the current phase name using config hints."""
    if not phase_name:
        return OTHER

    folded_phase_name = phase_name.casefold()
    section_headers = _get_section_headers()
    for section_name, section_values in section_headers.items():
        if folded_phase_name in section_values:
            if section_name == "labor":
                return LABOR
            if section_name == "equipment":
                return EQUIPMENT
            if section_name == "material":
                return MATERIAL
            if section_name == "subcontractor":
                return SUBCONTRACTOR
    return OTHER


def is_detail_candidate(line: str) -> bool:
    """Return True when a line should be preserved for detail parsing or review."""
    return not (
        is_blank_line(line)
        or is_header_or_footer(line)
        or is_total_line(line)
        or is_phase_header(line)
    )


def _matches_ignore_pattern(line: str, pattern: str) -> bool:
    """Match ignore patterns conservatively to avoid dropping real detail lines."""
    if not pattern:
        return False
    if line == pattern:
        return True
    if line.startswith(pattern):
        remainder = line[len(pattern) :].strip()
        return _is_safe_boilerplate_remainder(remainder)
    if line.endswith(pattern):
        prefix = line[: -len(pattern)].strip()
        return _is_safe_boilerplate_remainder(prefix)
    return False


def _is_safe_boilerplate_remainder(text: str) -> bool:
    """Return True when a remaining fragment is only punctuation-like boilerplate."""
    if not text:
        return True
    return all(character in " .:-_/()[]" for character in text)

