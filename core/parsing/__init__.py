"""Parsing components for job cost source documents.

Keep package imports lazy so non-parsing flows can import parsing submodules
without requiring optional PDF-reading dependencies.
"""

from __future__ import annotations

from typing import Any

__all__ = ["extract_pdf_pages", "parse_report_pages"]


def extract_pdf_pages(*args: Any, **kwargs: Any) -> list[str]:
    """Read source-document pages without importing PDF dependencies eagerly."""
    from core.parsing.pdf_reader import extract_pdf_pages as _extract_pdf_pages

    return _extract_pdf_pages(*args, **kwargs)


def parse_report_pages(*args: Any, **kwargs: Any) -> list[Any]:
    """Parse report pages without importing parser dependencies at package import time."""
    from core.parsing.report_parser import parse_report_pages as _parse_report_pages

    return _parse_report_pages(*args, **kwargs)
