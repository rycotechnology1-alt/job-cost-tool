"""PDF text extraction utilities for job cost reports."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pdfplumber

from core.parsing.types import PDFPageData


def extract_pdf_pages(file_path: str) -> List[PDFPageData]:
    """Extract text from a text-based PDF page by page.

    Args:
        file_path: Path to the PDF file.

    Returns:
        A list of dictionaries containing page numbers and extracted text.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        ValueError: If the path is not a PDF file or cannot be read.
    """
    pdf_path = Path(file_path).expanduser()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file was not found: '{pdf_path}'")
    if not pdf_path.is_file():
        raise ValueError(f"PDF path is not a file: '{pdf_path}'")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got '{pdf_path.suffix}' for '{pdf_path}'")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            return [
                {
                    "page_number": index,
                    "text": page.extract_text() or "",
                }
                for index, page in enumerate(pdf.pages, start=1)
            ]
    except pdfplumber.pdf.PDFSyntaxError as exc:
        raise ValueError(f"Unable to read PDF file '{pdf_path}': invalid PDF structure") from exc
    except Exception as exc:
        raise ValueError(f"Unable to read PDF file '{pdf_path}': {exc}") from exc
