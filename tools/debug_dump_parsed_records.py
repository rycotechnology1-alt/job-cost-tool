"""Diagnostic utility for dumping emitted parsed records from a PDF."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.models.record import Record
from services.parsing_service import parse_pdf

CSV_COLUMNS = (
    "record_index",
    "source_page",
    "raw_description",
    "source_line_text",
    "raw_type",
    "normalized_type",
    "phase_code",
    "phase_name",
    "transaction_type",
    "confidence",
    "job_number",
    "job_name",
    "employee_id",
    "employee_name",
    "vendor_id_raw",
    "vendor_name",
    "vendor_name_normalized",
    "union_code",
    "labor_class_raw",
    "labor_class_normalized",
    "equipment_description",
    "equipment_mapping_key",
    "equipment_category",
    "hours",
    "hour_type",
    "cost",
    "recap_labor_slot_id",
    "recap_labor_classification",
    "recap_equipment_slot_id",
    "is_omitted",
    "has_blocking_warning",
    "warning_count",
    "warnings",
)


def dump_parsed_records(pdf_path: str, output_path: str | None = None) -> Path:
    """Parse a PDF with the real pipeline and dump emitted records to CSV."""
    pdf = Path(pdf_path).expanduser().resolve()
    output = _default_output_path(pdf) if output_path is None else Path(output_path).expanduser().resolve()
    records = parse_pdf(str(pdf))
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for index, record in enumerate(records, start=1):
            writer.writerow(_record_to_row(record, index))

    return output


def _default_output_path(pdf_path: Path) -> Path:
    """Return the default CSV path next to the input PDF."""
    return pdf_path.with_name(f"{pdf_path.stem}_parsed_records.csv")


def _record_to_row(record: Record, record_index: int) -> dict[str, str | int | float | bool]:
    """Serialize one parsed record into a diff-friendly CSV row."""
    return {
        "record_index": record_index,
        "source_page": _stringify(record.source_page),
        "raw_description": _stringify(record.raw_description),
        "source_line_text": _stringify(record.source_line_text),
        "raw_type": _stringify(record.record_type),
        "normalized_type": _stringify(record.record_type_normalized),
        "phase_code": _stringify(record.phase_code),
        "phase_name": _stringify(record.phase_name_raw),
        "transaction_type": _stringify(record.transaction_type),
        "confidence": record.confidence,
        "job_number": _stringify(record.job_number),
        "job_name": _stringify(record.job_name),
        "employee_id": _stringify(record.employee_id),
        "employee_name": _stringify(record.employee_name),
        "vendor_id_raw": _stringify(record.vendor_id_raw),
        "vendor_name": _stringify(record.vendor_name),
        "vendor_name_normalized": _stringify(record.vendor_name_normalized),
        "union_code": _stringify(record.union_code),
        "labor_class_raw": _stringify(record.labor_class_raw),
        "labor_class_normalized": _stringify(record.labor_class_normalized),
        "equipment_description": _stringify(record.equipment_description),
        "equipment_mapping_key": _stringify(record.equipment_mapping_key),
        "equipment_category": _stringify(record.equipment_category),
        "hours": _stringify(record.hours),
        "hour_type": _stringify(record.hour_type),
        "cost": _stringify(record.cost),
        "recap_labor_slot_id": _stringify(record.recap_labor_slot_id),
        "recap_labor_classification": _stringify(record.recap_labor_classification),
        "recap_equipment_slot_id": _stringify(record.recap_equipment_slot_id),
        "is_omitted": record.is_omitted,
        "has_blocking_warning": record.has_blocking_warning(),
        "warning_count": len(record.warnings),
        "warnings": " | ".join(record.warnings),
    }


def _stringify(value: object) -> str | int | float:
    """Return CSV-safe scalar values without forcing numbers to strings."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dump emitted parsed records from a PDF into a CSV for debugging diffs.",
    )
    parser.add_argument("pdf_path", help="Path to the source PDF to parse.")
    parser.add_argument(
        "-o",
        "--output",
        help="Optional output CSV path. Defaults to <pdf_stem>_parsed_records.csv next to the PDF.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    output_path = dump_parsed_records(args.pdf_path, args.output)
    print(f"Wrote parsed record dump to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
