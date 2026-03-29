"""Shared helpers for deterministic equipment mapping-key derivation."""

from __future__ import annotations

import re
from typing import Optional

_ASSET_PREFIX_RE = re.compile(r"^(?P<asset_id>\d+)\s*/\s*(?P<rest>.+)$")
_LEADING_YEAR_RE = re.compile(r"^(?P<year>\d{4})\s+(?P<rest>.+)$")
_SLASH_SPACING_RE = re.compile(r"\s*/\s*")
_RAM_MODEL_RE = re.compile(r"\bRAM\s*(\d{4})\b")
_W_LIFT_GATE_RE = re.compile(r"\bW/LIFT\s*GATE\b")

_TERM_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCHEVY\b"), "CHEVROLET"),
    (re.compile(r"\bUTILTIY\b"), "UTILITY"),
    (re.compile(r"\bHANDELR\b"), "HANDLER"),
    (re.compile(r"\bSAVANNA\b"), "SAVANA"),
    (re.compile(r"\bMATERIAL HANDLER\b"), "MAT HANDLER"),
)


def derive_equipment_mapping_key(value: Optional[str]) -> Optional[str]:
    """Derive the reusable equipment mapping key from raw description text.

    The transformation is intentionally deterministic and low-risk:
    - trim and collapse repeated whitespace
    - remove a leading asset id formatted like ``<digits>/<rest>``
    - then remove a leading 4-digit year when present
    - normalize slash spacing consistently
    - standardize a small set of obvious spelling/wording variants
    - preserve the remaining make/model/type wording

    This helper does not perform broad category collapsing or fuzzy matching.
    """
    if value is None:
        return None

    normalized = " ".join(str(value).strip().split())
    if not normalized:
        return None

    asset_match = _ASSET_PREFIX_RE.match(normalized)
    if asset_match:
        normalized = asset_match.group("rest").strip()

    year_match = _LEADING_YEAR_RE.match(normalized)
    if year_match:
        normalized = year_match.group("rest").strip()

    normalized = normalized.upper()
    normalized = _SLASH_SPACING_RE.sub("/", normalized)
    normalized = _RAM_MODEL_RE.sub(r"RAM \1", normalized)
    normalized = _W_LIFT_GATE_RE.sub("W/LIFT GATE", normalized)

    for pattern, replacement in _TERM_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)

    normalized = " ".join(normalized.split())
    return normalized or None
