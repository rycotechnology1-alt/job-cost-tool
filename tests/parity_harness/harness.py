"""End-to-end parity harness for desktop and accepted web paths."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import create_app
from core.config import ConfigLoader, ProfileManager
from infrastructure.persistence import SqliteLineageStore
from services.export_service import export_records_to_recap
from services.review_workflow_service import load_review_data, update_review_record
from tests.parity_harness.corpus import ParityCase, materialize_case_runtime
from tests.parity_harness.workbook_semantics import (
    capture_non_empty_workbook_snapshot,
    capture_workbook_snapshot,
    compare_workbook_snapshots,
)


@dataclass(frozen=True, slots=True)
class ParityRunSnapshot:
    """Semantic workflow outputs for one parity-path execution."""

    base_records: list[dict[str, object]]
    base_blockers: list[str]
    edited_records: list[dict[str, object]]
    edited_blockers: list[str]
    export_snapshot: dict[str, object]


def run_desktop_reference_path(case: ParityCase, runtime_root: Path) -> ParityRunSnapshot:
    """Run one case through the desktop/core service path."""
    profile_dir, legacy_config_dir, source_path = materialize_case_runtime(case, runtime_root)
    parsed_records = case.build_parsed_records() if case.parsed_records is not None else None
    parser_context = (
        patch("services.review_workflow_service.parse_pdf", return_value=copy.deepcopy(parsed_records))
        if parsed_records is not None
        else nullcontext()
    )

    with parser_context:
        base_result = load_review_data(
            str(source_path),
            config_dir=profile_dir,
            legacy_config_dir=legacy_config_dir,
        )

    base_review_records = list(base_result.review_records)
    current_review_records = list(base_result.review_records)
    current_records = list(base_result.records)
    current_blockers = list(base_result.blocking_issues)
    target_export_revision = _resolve_target_export_revision(case)
    export_records = list(current_records)
    for revision_index, edit_batch in enumerate(case.scripted_edit_batches, start=1):
        for edit in edit_batch:
            record_index = _record_index_from_key(edit["record_key"])
            update_result = update_review_record(
                current_review_records,
                record_index,
                dict(edit["changed_fields"]),
                base_review_records=base_review_records,
                file_path=str(source_path),
                config_dir=profile_dir,
                legacy_config_dir=legacy_config_dir,
            )
            if update_result is None:
                raise AssertionError(f"Desktop reference path rejected edit for {edit['record_key']}.")
            current_review_records = list(update_result.review_records)
            current_records = list(update_result.records)
            current_blockers = list(update_result.blocking_issues)
        if revision_index == target_export_revision:
            export_records = list(current_records)

    if target_export_revision == 0:
        export_records = list(base_result.records)

    export_path = runtime_root / "desktop-export.xlsx"
    export_records_to_recap(
        export_records,
        str(profile_dir / case.template_filename),
        str(export_path),
        config_dir=profile_dir,
        legacy_config_dir=legacy_config_dir,
    )
    export_snapshot = (
        capture_workbook_snapshot(export_path, case.expected_export_snapshot)
        if case.expected_export_snapshot is not None
        else capture_non_empty_workbook_snapshot(export_path)
    )
    return ParityRunSnapshot(
        base_records=_records_to_semantic_snapshot(base_result.records),
        base_blockers=list(base_result.blocking_issues),
        edited_records=_records_to_semantic_snapshot(current_records),
        edited_blockers=current_blockers,
        export_snapshot=export_snapshot,
    )


def run_web_api_path(case: ParityCase, runtime_root: Path) -> ParityRunSnapshot:
    """Run one case through the accepted FastAPI/API workflow path."""
    _, legacy_config_dir, source_path = materialize_case_runtime(case, runtime_root)
    settings_path = runtime_root / "app_settings.json"
    settings_path.write_text(json.dumps({"active_profile": case.trusted_profile_name}, indent=2), encoding="utf-8")
    profile_manager = ProfileManager(
        profiles_root=runtime_root / "profiles",
        legacy_config_root=legacy_config_dir,
    )
    lineage_store = SqliteLineageStore()
    client = TestClient(
        create_app(
            lineage_store=lineage_store,
            profile_manager=profile_manager,
            upload_root=runtime_root / "runtime" / "uploads",
            export_root=runtime_root / "runtime" / "exports",
            engine_version="parity-harness",
        )
    )
    parsed_records = case.build_parsed_records() if case.parsed_records is not None else None
    parser_context = (
        patch("services.review_workflow_service.parse_pdf", return_value=copy.deepcopy(parsed_records))
        if parsed_records is not None
        else nullcontext()
    )

    try:
        with parser_context:
            upload_response = client.post(
                "/api/source-documents/uploads",
                files={"file": (source_path.name, source_path.read_bytes(), "application/pdf")},
            )
            upload_response.raise_for_status()
            upload_payload = upload_response.json()

            run_response = client.post(
                "/api/runs",
                json={
                    "upload_id": upload_payload["upload_id"],
                    "trusted_profile_name": case.trusted_profile_name,
                },
            )
            run_response.raise_for_status()
            run_payload = run_response.json()

            run_detail_response = client.get(f"/api/runs/{run_payload['processing_run_id']}")
            run_detail_response.raise_for_status()
            run_detail_payload = run_detail_response.json()

            current_session_response = client.get(f"/api/runs/{run_payload['processing_run_id']}/review-session")
            current_session_response.raise_for_status()
            current_session_payload = current_session_response.json()
            target_export_revision = _resolve_target_export_revision(case)

            for edit_batch in case.scripted_edit_batches:
                edits_response = client.post(
                    f"/api/runs/{run_payload['processing_run_id']}/review-session/edits",
                    json={"edits": edit_batch},
                )
                edits_response.raise_for_status()
                current_session_payload = edits_response.json()

            export_response = client.post(
                f"/api/runs/{run_payload['processing_run_id']}/exports",
                json={"session_revision": target_export_revision},
            )
            export_response.raise_for_status()
            export_payload = export_response.json()

            download_response = client.get(export_payload["download_url"])
            download_response.raise_for_status()

        export_path = runtime_root / "web-export.xlsx"
        export_path.write_bytes(download_response.content)
        export_snapshot = (
            capture_workbook_snapshot(export_path, case.expected_export_snapshot)
            if case.expected_export_snapshot is not None
            else capture_non_empty_workbook_snapshot(export_path)
        )
        return ParityRunSnapshot(
            base_records=_api_run_records_to_semantic_snapshot(run_detail_payload["run_records"]),
            base_blockers=list(run_detail_payload["aggregate_blockers"]),
            edited_records=_api_review_records_to_semantic_snapshot(current_session_payload["records"]),
            edited_blockers=list(current_session_payload["blocking_issues"]),
            export_snapshot=export_snapshot,
        )
    finally:
        client.close()
        lineage_store.close()
        ConfigLoader.clear_runtime_caches()


def build_expected_snapshot(case: ParityCase) -> ParityRunSnapshot:
    """Return the corpus-defined expected semantic outputs for one case."""
    if (
        case.expected_base_records is None
        or case.expected_base_blockers is None
        or case.expected_edited_records is None
        or case.expected_edited_blockers is None
        or case.expected_export_snapshot is None
    ):
        raise ValueError(f"Parity case '{case.case_name}' does not define a full expected semantic snapshot.")
    return ParityRunSnapshot(
        base_records=case.expected_base_records,
        base_blockers=case.expected_base_blockers,
        edited_records=case.expected_edited_records,
        edited_blockers=case.expected_edited_blockers,
        export_snapshot=case.expected_export_snapshot,
    )


def build_reference_export_snapshot(case: ParityCase) -> dict[str, object]:
    """Return the semantic workbook snapshot captured from a corpus reference workbook."""
    if case.reference_export_path is None:
        raise ValueError(f"Parity case '{case.case_name}' does not define a reference export workbook.")
    return capture_non_empty_workbook_snapshot(case.reference_export_path)


def compare_parity_snapshot(
    expected: ParityRunSnapshot,
    actual: ParityRunSnapshot,
    *,
    label: str,
) -> list[str]:
    """Return semantic parity mismatch messages for one path."""
    diffs: list[str] = []
    diffs.extend(_compare_jsonish(expected.base_records, actual.base_records, f"{label}: base records"))
    diffs.extend(_compare_jsonish(expected.base_blockers, actual.base_blockers, f"{label}: base blockers"))
    diffs.extend(_compare_jsonish(expected.edited_records, actual.edited_records, f"{label}: edited records"))
    diffs.extend(_compare_jsonish(expected.edited_blockers, actual.edited_blockers, f"{label}: edited blockers"))
    diffs.extend(compare_workbook_snapshots(expected.export_snapshot, actual.export_snapshot, label=f"{label}: export"))
    return diffs


def _record_index_from_key(record_key: str) -> int:
    """Resolve one run-scoped record key into its emitted-order index."""
    prefix = "record-"
    if not str(record_key).startswith(prefix):
        raise ValueError(f"Unsupported record_key format: {record_key}")
    return int(str(record_key)[len(prefix) :])


def _resolve_target_export_revision(case: ParityCase) -> int:
    """Return the explicit export revision or default to the latest scripted revision."""
    target_export_revision = len(case.scripted_edit_batches) if case.target_export_revision is None else case.target_export_revision
    if target_export_revision < 0 or target_export_revision > len(case.scripted_edit_batches):
        raise ValueError(
            f"Parity case '{case.case_name}' target_export_revision must be between 0 and "
            f"{len(case.scripted_edit_batches)}."
        )
    return target_export_revision


def _records_to_semantic_snapshot(records) -> list[dict[str, object]]:
    """Shape Record objects into parity-comparison dictionaries."""
    return [
        _record_to_semantic_snapshot(record, record_key=f"record-{index}")
        for index, record in enumerate(records)
    ]


def _api_run_records_to_semantic_snapshot(run_records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Shape immutable API run records into parity-comparison dictionaries."""
    snapshots: list[dict[str, object]] = []
    for run_record in run_records:
        canonical_record = dict(run_record["canonical_record"])
        snapshots.append(
            {
                "record_key": run_record["record_key"],
                "record_type": canonical_record.get("record_type"),
                "record_type_normalized": canonical_record.get("record_type_normalized"),
                "phase_code": canonical_record.get("phase_code"),
                "raw_description": canonical_record.get("raw_description"),
                "cost": canonical_record.get("cost"),
                "hours": canonical_record.get("hours"),
                "hour_type": canonical_record.get("hour_type"),
                "job_number": canonical_record.get("job_number"),
                "job_name": canonical_record.get("job_name"),
                "transaction_type": canonical_record.get("transaction_type"),
                "source_page": run_record.get("source_page"),
                "source_line_text": run_record.get("source_line_text"),
                "vendor_name": canonical_record.get("vendor_name"),
                "vendor_name_normalized": canonical_record.get("vendor_name_normalized"),
                "recap_labor_classification": canonical_record.get("recap_labor_classification"),
                "equipment_category": canonical_record.get("equipment_category"),
                "warnings": list(canonical_record.get("warnings") or []),
                "is_omitted": bool(canonical_record.get("is_omitted", False)),
            }
        )
    return snapshots


def _api_review_records_to_semantic_snapshot(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Shape API review-session records into parity-comparison dictionaries."""
    snapshots: list[dict[str, object]] = []
    for index, record in enumerate(records):
        snapshots.append(
            {
                "record_key": f"record-{index}",
                "record_type": record.get("record_type"),
                "record_type_normalized": record.get("record_type_normalized"),
                "phase_code": record.get("phase_code"),
                "raw_description": record.get("raw_description"),
                "cost": record.get("cost"),
                "hours": record.get("hours"),
                "hour_type": record.get("hour_type"),
                "job_number": record.get("job_number"),
                "job_name": record.get("job_name"),
                "transaction_type": record.get("transaction_type"),
                "source_page": record.get("source_page"),
                "source_line_text": record.get("source_line_text"),
                "vendor_name": record.get("vendor_name"),
                "vendor_name_normalized": record.get("vendor_name_normalized"),
                "recap_labor_classification": record.get("recap_labor_classification"),
                "equipment_category": record.get("equipment_category"),
                "warnings": list(record.get("warnings") or []),
                "is_omitted": bool(record.get("is_omitted", False)),
            }
        )
    return snapshots


def _record_to_semantic_snapshot(record, *, record_key: str) -> dict[str, object]:
    """Shape one Record object into the stable parity-comparison contract."""
    return {
        "record_key": record_key,
        "record_type": record.record_type,
        "record_type_normalized": record.record_type_normalized,
        "phase_code": record.phase_code,
        "raw_description": record.raw_description,
        "cost": record.cost,
        "hours": record.hours,
        "hour_type": record.hour_type,
        "job_number": record.job_number,
        "job_name": record.job_name,
        "transaction_type": record.transaction_type,
        "source_page": record.source_page,
        "source_line_text": record.source_line_text,
        "vendor_name": record.vendor_name,
        "vendor_name_normalized": record.vendor_name_normalized,
        "recap_labor_classification": record.recap_labor_classification,
        "equipment_category": record.equipment_category,
        "warnings": list(record.warnings),
        "is_omitted": bool(record.is_omitted),
    }


def _compare_jsonish(expected, actual, label: str) -> list[str]:
    """Return a compact mismatch message for JSON-like payloads."""
    if expected == actual:
        return []
    return [
        f"{label} mismatch.\nEXPECTED: {json.dumps(expected, indent=2, sort_keys=True)}\n"
        f"ACTUAL: {json.dumps(actual, indent=2, sort_keys=True)}"
    ]
