"""Shared helpers for conservative phase-code canonicalization."""

from __future__ import annotations

import re

_PHASE_SEGMENT_RE = re.compile(r"\d+")


def canonicalize_phase_code(value: object) -> str:
    """Return a stable phase-code representation without inventing detail.

    Supported examples:
    - ``29 .   .`` -> ``29``
    - ``29 .999.`` -> ``29 .999``
    - ``13 .25 .`` -> ``13 .25``
    - ``13 .5  .`` -> ``13 .5``

    The helper is intentionally conservative. It normalizes spacing and dotted
    numeric segments, but it does not infer subphases when the input does not
    explicitly contain dotted phase detail.
    """
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""

    if "." not in text:
        return text

    segments: list[str] = []
    for part in text.split("."):
        stripped = part.strip()
        if not stripped:
            continue
        if not stripped.isdigit():
            return text
        segments.append(stripped)

    if not segments:
        return ""

    return segments[0] + "".join(f" .{segment}" for segment in segments[1:])


def phase_code_sort_key(value: object) -> tuple[tuple[int, ...], str]:
    """Return a deterministic sort key for phase-code display."""
    canonical = canonicalize_phase_code(value)
    numeric_segments = tuple(int(segment) for segment in _PHASE_SEGMENT_RE.findall(canonical))
    return numeric_segments, canonical.casefold()
