"""View-model for coordinating the record review workflow."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from core.config import ProfileManager
from core.models.record import Record
from core.equipment_keys import derive_equipment_mapping_key
from core.phase_codes import canonicalize_phase_code
from services import review_workflow_service
from services.settings_workflow_service import (
    persist_observed_equipment_raw_values,
    persist_observed_labor_raw_values,
)


class ReviewViewModel(QObject):
    """Coordinate pipeline execution, filtering, selection, and corrections for the UI."""

    FILTER_ALL = "All Records"
    FILTER_BLOCKING = "Blocking Only"
    FILTER_WARNINGS = "Warnings Only"
    FILTER_OPTIONS = [FILTER_ALL, FILTER_BLOCKING, FILTER_WARNINGS]
    EDITABLE_FIELDS = review_workflow_service.EDITABLE_FIELDS

    state_changed = Signal()
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.current_pdf_path: Optional[str] = None
        self.status_text = "Open a PDF to begin review."
        self.is_processing = False
        self._review_records: list[Record] = []
        self._records: list[Record] = []
        self._record_ids: list[str] = []
        self._blocking_issues: list[str] = []
        self._filter_mode = self.FILTER_ALL
        self._selected_record_id: Optional[str] = None
        self._labor_options, self._equipment_options = review_workflow_service.load_edit_options()

    @property
    def records(self) -> list[Record]:
        """Return all validated records."""
        return list(self._records)

    @property
    def filtered_records(self) -> list[Record]:
        """Return records matching the active filter."""
        if self._filter_mode == self.FILTER_BLOCKING:
            return [record for record in self._records if record.has_blocking_warning()]
        if self._filter_mode == self.FILTER_WARNINGS:
            return [record for record in self._records if record.warnings]
        return list(self._records)

    @property
    def blocking_issues(self) -> list[str]:
        """Return aggregate export-blocking issues."""
        return list(self._blocking_issues)

    @property
    def selected_record(self) -> Optional[Record]:
        """Return the currently selected validated record."""
        if self._selected_record_id is None:
            return None
        index = self._index_for_record_id(self._selected_record_id)
        if index is None:
            return None
        record = self._records[index]
        return record if record in self.filtered_records else None

    @property
    def selected_record_id(self) -> Optional[str]:
        """Return the currently selected record identifier."""
        return self._selected_record_id

    @property
    def labor_options(self) -> list[str]:
        """Return labor classification options for correction controls."""
        return list(self._labor_options)

    @property
    def equipment_options(self) -> list[str]:
        """Return equipment category options for correction controls."""
        return list(self._equipment_options)

    @property
    def can_export(self) -> bool:
        """Return True when export would be allowed if implemented."""
        return bool(self._records) and not self._blocking_issues and not self.is_processing

    @property
    def observed_labor_raw_values(self) -> list[str]:
        """Return actual observed raw labor values from the current review dataset."""
        observed_values: list[str] = []
        seen: set[str] = set()
        for record in self._review_records:
            raw_value = self._format_observed_labor_raw_value(record)
            if raw_value is None:
                continue
            normalized = raw_value.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            observed_values.append(raw_value)
        return observed_values

    @property
    def observed_equipment_mapping_keys(self) -> list[str]:
        """Return derived reusable equipment mapping keys from the current review dataset."""
        observed_values: list[str] = []
        seen: set[str] = set()
        for record in self._review_records:
            mapping_key = str(record.equipment_mapping_key or derive_equipment_mapping_key(record.equipment_description) or "").strip()
            if not mapping_key:
                continue
            normalized = mapping_key.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            observed_values.append(mapping_key)
        return observed_values

    @property
    def observed_phase_options(self) -> list[dict[str, str]]:
        """Return canonicalized observed phase codes and their first-seen names."""
        observed_rows: list[dict[str, str]] = []
        index_by_key: dict[str, int] = {}
        for record in self._review_records:
            phase_code = canonicalize_phase_code(record.phase_code)
            if not phase_code:
                continue
            phase_name = " ".join(str(record.phase_name_raw or "").strip().split())
            normalized_key = phase_code.casefold()
            if normalized_key in index_by_key:
                existing_row = observed_rows[index_by_key[normalized_key]]
                if not existing_row["phase_name"] and phase_name:
                    existing_row["phase_name"] = phase_name
                continue
            index_by_key[normalized_key] = len(observed_rows)
            observed_rows.append({"phase_code": phase_code, "phase_name": phase_name})
        return observed_rows

    def load_pdf(self, file_path: str) -> None:
        """Run the parse-normalize-validate pipeline for a selected PDF."""
        self.current_pdf_path = file_path
        self.is_processing = True
        self.status_text = f"Processing: {file_path}"
        self._selected_record_id = None
        self.state_changed.emit()

        try:
            result = review_workflow_service.load_review_data(file_path)
        except Exception as exc:
            self.is_processing = False
            self._review_records = []
            self._records = []
            self._record_ids = []
            self._blocking_issues = []
            self.status_text = f"Failed to process file: {exc}"
            self.state_changed.emit()
            self.error_occurred.emit(str(exc))
            return

        self._review_records = list(result.review_records)
        self._persist_observed_labor_raw_values()
        self._persist_observed_equipment_raw_values()
        self._record_ids = [self._build_record_id(index) for index, _ in enumerate(self._review_records)]
        self._records = list(result.records)
        self._blocking_issues = list(result.blocking_issues)
        self._selected_record_id = self._record_ids[0] if self._record_ids else None
        self.is_processing = False
        self.status_text = result.status_text
        self.state_changed.emit()

    def reload_current_pdf(self) -> None:
        """Re-run the pipeline for the currently selected PDF."""
        if self.current_pdf_path:
            self.load_pdf(self.current_pdf_path)

    def reload_profile_options(self) -> None:
        """Reload profile-driven editor options after a profile change."""
        self._labor_options, self._equipment_options = review_workflow_service.load_edit_options()
        self.state_changed.emit()

    def set_filter_mode(self, filter_mode: str) -> None:
        """Update the active record filter."""
        if filter_mode not in self.FILTER_OPTIONS:
            return
        self._filter_mode = filter_mode
        if self.selected_record not in self.filtered_records:
            first_filtered_record = self.filtered_records[0] if self.filtered_records else None
            self._selected_record_id = self._record_id_for_record(first_filtered_record) if first_filtered_record else None
        self.state_changed.emit()

    def set_selected_record(self, record: Optional[Record]) -> None:
        """Set the currently selected record."""
        self._selected_record_id = self._record_id_for_record(record) if record else None
        self.state_changed.emit()

    def apply_updates_to_selected_record(self, updates: dict[str, object]) -> None:
        """Apply normalized-field updates to the selected record and revalidate."""
        if self._selected_record_id is None:
            return
        self.update_record(self._selected_record_id, updates)

    def update_record(self, record_id: str, updates: dict[str, object]) -> None:
        """Apply normalized-field updates to a record, then re-run validation."""
        index = self._index_for_record_id(record_id)
        if index is None:
            return

        result = review_workflow_service.update_review_record(
            self._review_records,
            index,
            updates,
            file_path=self.current_pdf_path,
        )
        if result is None:
            return

        self._review_records = list(result.review_records)
        self._records = list(result.records)
        self._blocking_issues = list(result.blocking_issues)
        if self.selected_record not in self.filtered_records:
            first_filtered_record = self.filtered_records[0] if self.filtered_records else None
            self._selected_record_id = self._record_id_for_record(first_filtered_record) if first_filtered_record else None
        else:
            self._selected_record_id = record_id
        self.status_text = result.status_text
        self.state_changed.emit()

    def _persist_observed_labor_raw_values(self) -> None:
        """Persist newly observed labor raw values for editable profiles without interrupting review load."""
        try:
            profile_manager = ProfileManager()
            if profile_manager.get_active_profile_name().strip().casefold() == "default":
                return
            persist_observed_labor_raw_values(
                profile_manager.get_active_profile_dir(),
                self.observed_labor_raw_values,
            )
        except Exception:
            return

    def _persist_observed_equipment_raw_values(self) -> None:
        """Persist newly observed equipment descriptions for editable profiles without interrupting review load."""
        try:
            profile_manager = ProfileManager()
            if profile_manager.get_active_profile_name().strip().casefold() == "default":
                return
            persist_observed_equipment_raw_values(
                profile_manager.get_active_profile_dir(),
                self.observed_equipment_mapping_keys,
            )
        except Exception:
            return

    def _record_id_for_record(self, record: Optional[Record]) -> Optional[str]:
        """Return the managed identifier for a validated record object."""
        if record is None:
            return None
        for index, existing_record in enumerate(self._records):
            if existing_record is record:
                return self._record_ids[index]
        return None

    def _index_for_record_id(self, record_id: str) -> Optional[int]:
        """Return the list index for a managed record identifier."""
        try:
            return self._record_ids.index(record_id)
        except ValueError:
            return None

    def _build_record_id(self, index: int) -> str:
        """Build a stable in-memory identifier for a review record."""
        return f"record-{index}"

    def _format_observed_labor_raw_value(self, record: Record) -> str | None:
        """Build a true observed labor raw value from parsed source fields only."""
        labor_class_raw = str(record.labor_class_raw or "").strip()
        union_code = str(record.union_code or "").strip()
        if not labor_class_raw:
            return None
        return f"{union_code}/{labor_class_raw}" if union_code else labor_class_raw
