"""Shared types for PDF parsing components."""

from typing import TypedDict


class PDFPageData(TypedDict):
    """Text extracted from a single PDF page."""

    page_number: int
    text: str
