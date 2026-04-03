from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from job_cost_tool.core.export import excel_exporter, recap_mapper
from job_cost_tool.core.export.recap_mapper import build_recap_payload
from job_cost_tool.services import export_service
from job_cost_tool.services.normalization_service import normalize_records
from job_cost_tool.services.parsing_service import parse_pdf
from job_cost_tool.services.validation_service import validate_records


def main() -> int:
    os.environ["JOB_COST_TOOL_EXPORT_DEBUG"] = "1"

    sample_pdf = Path(
        r"c:\Apps\recap tool\Samples\JC Reports for Test\No way to export PM allocation 'Normalized record family is missing'\12 semi pass1.pdf"
    )
    output_path = Path(
        r"c:\Apps\recap tool\Samples\JC Reports for Test\No way to export PM allocation 'Normalized record family is missing'\12 semi pass1 TRACE Recap.xlsx"
    )

    if output_path.exists():
        output_path.unlink()

    print("module_paths")
    print(f"  export_service={export_service.__file__}")
    print(f"  recap_mapper={recap_mapper.__file__}")
    print(f"  excel_exporter={excel_exporter.__file__}")

    parsed_records = parse_pdf(str(sample_pdf))
    normalized_records = normalize_records(parsed_records)
    validated_records, blocking_issues = validate_records(normalized_records)

    print(f"parsed_record_count={len(parsed_records)}")
    print(f"normalized_record_count={len(normalized_records)}")
    print(f"validated_record_count={len(validated_records)}")
    print(f"blocking_issues={blocking_issues}")

    family_counts = Counter(
        str(record.record_type_normalized or record.record_type or "").strip().casefold() or "<blank>"
        for record in validated_records
    )
    print(f"validated_family_counts={dict(family_counts)}")

    pm_rows = [
        {
            "phase_code": record.phase_code,
            "phase_name": record.phase_name_raw,
            "raw_type": record.record_type,
            "normalized_type": record.record_type_normalized,
            "cost": record.cost,
            "is_omitted": record.is_omitted,
            "raw_description": record.raw_description,
        }
        for record in validated_records
        if str(record.record_type_normalized or record.record_type or "").strip().casefold() == "project_management"
    ]
    print(f"project_management_rows={pm_rows}")

    recap_payload = build_recap_payload(validated_records)
    print(f"project_management_total={recap_payload.get('project_management_total')!r}")

    export_service.export_records_to_recap(
        records=validated_records,
        template_path=str(Path(r"c:\Apps\recap tool\job_cost_tool\profiles\default\recap_template.xlsx")),
        output_path=str(output_path),
    )

    print(f"saved_output={output_path}")
    workbook = load_workbook(output_path)
    worksheet = workbook["RECAP"]
    print(f"saved_E59={worksheet['E59'].value!r}")
    print(f"saved_F59={worksheet['F59'].value!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

