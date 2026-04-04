"""Detail panel for inspecting and correcting a selected validated record."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.models.record import EQUIPMENT, LABOR, MATERIAL, Record


class RecordDetailPanel(QWidget):
    """Display raw and normalized fields for the selected record and allow corrections."""

    apply_requested = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._value_labels: dict[str, QLabel] = {}
        self._raw_description = QTextEdit()
        self._source_line_text = QTextEdit()
        self._warnings_list = QListWidget()
        self._labor_options: list[str] = []
        self._equipment_options: list[str] = []
        self._current_record: Optional[Record] = None

        self._labor_edit_label = QLabel("Recap Labor Class")
        self._labor_edit_combo = QComboBox()
        self._equipment_edit_label = QLabel("Equipment Category")
        self._equipment_edit_combo = QComboBox()
        self._vendor_edit_label = QLabel("Vendor Normalized")
        self._vendor_edit_input = QLineEdit()
        self._omit_checkbox = QCheckBox("Omit this record from export")
        self._apply_button = QPushButton("Apply Changes")

        self._build_layout()
        self._connect_signals()
        self.set_record(None)

    def _build_layout(self) -> None:
        """Build the detail panel layout."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(10)

        summary_group = QGroupBox("Selected Record")
        summary_form = QFormLayout(summary_group)
        summary_fields = [
            ("source_page", "Source Page"),
            ("phase_code", "Phase Code"),
            ("phase_name_raw", "Phase Name"),
            ("transaction_type", "Transaction Type"),
            ("record_type", "Raw Type"),
            ("record_type_normalized", "Normalized Type"),
            ("is_omitted", "Export Status"),
            ("confidence", "Confidence"),
            ("employee_id", "Employee ID"),
            ("employee_name", "Employee Name"),
            ("vendor_id_raw", "Vendor ID"),
            ("vendor_name", "Vendor Name"),
            ("recap_labor_classification", "Recap Labor Class"),
            ("labor_class_raw", "Labor Class Raw"),
            ("labor_class_normalized", "Labor Class Normalized"),
            ("equipment_description", "Equipment Description"),
            ("hours", "Hours"),
            ("hour_type", "Hour Type"),
            ("cost", "Cost"),
        ]
        for key, label_text in summary_fields:
            value_label = QLabel()
            value_label.setWordWrap(True)
            self._value_labels[key] = value_label
            summary_form.addRow(label_text, value_label)

        editor_group = QGroupBox("Corrections")
        editor_form = QFormLayout(editor_group)
        editor_form.addRow(self._labor_edit_label, self._labor_edit_combo)
        editor_form.addRow(self._equipment_edit_label, self._equipment_edit_combo)
        editor_form.addRow(self._vendor_edit_label, self._vendor_edit_input)
        editor_form.addRow(QLabel("Export"), self._omit_checkbox)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._apply_button)
        editor_form.addRow(QLabel(""), button_row)

        traceability_group = QGroupBox("Traceability")
        traceability_layout = QVBoxLayout(traceability_group)
        self._raw_description.setReadOnly(True)
        self._source_line_text.setReadOnly(True)
        traceability_layout.addWidget(QLabel("Raw Description"))
        traceability_layout.addWidget(self._raw_description)
        traceability_layout.addWidget(QLabel("Source Line Text"))
        traceability_layout.addWidget(self._source_line_text)

        warnings_group = QGroupBox("Warnings")
        warnings_layout = QVBoxLayout(warnings_group)
        warnings_layout.addWidget(self._warnings_list)

        root_layout.addWidget(summary_group)
        root_layout.addWidget(editor_group)
        root_layout.addWidget(traceability_group)
        root_layout.addWidget(warnings_group, stretch=1)

    def _connect_signals(self) -> None:
        """Connect local widget signals."""
        self._apply_button.clicked.connect(self._emit_apply_requested)

    def set_edit_options(self, labor_options: list[str], equipment_options: list[str]) -> None:
        """Load config-driven edit options into the correction controls."""
        self._labor_options = list(labor_options)
        self._equipment_options = list(equipment_options)
        self._rebuild_option_lists()

    def set_record(self, record: Optional[Record]) -> None:
        """Populate the detail panel for the selected record."""
        self._current_record = record
        if record is None:
            for label in self._value_labels.values():
                label.setText("-")
            self._raw_description.setPlainText("")
            self._source_line_text.setPlainText("")
            self._warnings_list.clear()
            self._warnings_list.addItem(QListWidgetItem("Select a record to inspect its details."))
            self._set_editor_visibility(None)
            self._apply_button.setEnabled(False)
            self._reset_editor_values()
            self._omit_checkbox.setChecked(False)
            self._omit_checkbox.setEnabled(False)
            return

        values = {
            "source_page": _to_text(record.source_page),
            "phase_code": _to_text(record.phase_code),
            "phase_name_raw": _to_text(record.phase_name_raw),
            "transaction_type": _to_text(record.transaction_type),
            "record_type": _to_text(record.record_type),
            "record_type_normalized": _to_text(record.record_type_normalized),
            "is_omitted": "Omitted from export" if record.is_omitted else "Included in export",
            "confidence": f"{record.confidence:.1f}",
            "employee_id": _to_text(record.employee_id),
            "employee_name": _to_text(record.employee_name),
            "vendor_id_raw": _to_text(record.vendor_id_raw),
            "vendor_name": _to_text(record.vendor_name),
            "recap_labor_classification": _to_text(record.recap_labor_classification),
            "labor_class_raw": _to_text(record.labor_class_raw),
            "labor_class_normalized": _to_text(
                None if record.uses_fallback_labor_mapping_source() else record.labor_class_normalized
            ),
            "equipment_description": _to_text(record.equipment_description),
            "hours": _to_text(record.hours),
            "hour_type": _to_text(record.hour_type),
            "cost": _to_text(record.cost),
        }
        for key, value in values.items():
            self._value_labels[key].setText(value)

        self._raw_description.setPlainText(record.raw_description)
        self._source_line_text.setPlainText(record.source_line_text or "")
        self._warnings_list.clear()
        if record.warnings:
            for warning in record.warnings:
                self._warnings_list.addItem(QListWidgetItem(warning))
        else:
            self._warnings_list.addItem(QListWidgetItem("No warnings."))

        self._set_editor_visibility(record)
        self._populate_editor_values(record)
        self._omit_checkbox.setEnabled(True)
        self._apply_button.setEnabled(True)

    def _rebuild_option_lists(self) -> None:
        """Rebuild combo-box contents from the current option lists."""
        self._labor_edit_combo.blockSignals(True)
        self._equipment_edit_combo.blockSignals(True)
        try:
            self._labor_edit_combo.clear()
            self._labor_edit_combo.addItem("")
            self._labor_edit_combo.addItems(self._labor_options)
            self._equipment_edit_combo.clear()
            self._equipment_edit_combo.addItem("")
            self._equipment_edit_combo.addItems(self._equipment_options)
        finally:
            self._labor_edit_combo.blockSignals(False)
            self._equipment_edit_combo.blockSignals(False)

    def _populate_editor_values(self, record: Record) -> None:
        """Load the selected record values into the correction controls."""
        self._labor_edit_combo.blockSignals(True)
        self._equipment_edit_combo.blockSignals(True)
        self._vendor_edit_input.blockSignals(True)
        self._omit_checkbox.blockSignals(True)
        try:
            self._labor_edit_combo.setCurrentText(record.recap_labor_classification or "")
            self._equipment_edit_combo.setCurrentText(record.equipment_category or "")
            self._vendor_edit_input.setText(record.vendor_name_normalized or "")
            self._omit_checkbox.setChecked(record.is_omitted)
        finally:
            self._labor_edit_combo.blockSignals(False)
            self._equipment_edit_combo.blockSignals(False)
            self._vendor_edit_input.blockSignals(False)
            self._omit_checkbox.blockSignals(False)

    def _reset_editor_values(self) -> None:
        """Clear correction control values."""
        self._labor_edit_combo.setCurrentText("")
        self._equipment_edit_combo.setCurrentText("")
        self._vendor_edit_input.clear()
        self._omit_checkbox.setChecked(False)

    def _set_editor_visibility(self, record: Optional[Record]) -> None:
        """Show only the editor relevant to the selected record family."""
        normalized_family = record.record_type_normalized if record else None
        is_labor = normalized_family == LABOR
        is_equipment = normalized_family == EQUIPMENT
        is_material = normalized_family == MATERIAL

        self._labor_edit_label.setVisible(is_labor)
        self._labor_edit_combo.setVisible(is_labor)
        self._equipment_edit_label.setVisible(is_equipment)
        self._equipment_edit_combo.setVisible(is_equipment)
        self._vendor_edit_label.setVisible(is_material)
        self._vendor_edit_input.setVisible(is_material)
        self._omit_checkbox.setVisible(record is not None)

    def _emit_apply_requested(self) -> None:
        """Emit normalized field edits for the selected record."""
        if self._current_record is None:
            return

        normalized_family = self._current_record.record_type_normalized
        updates: dict[str, object] = {"is_omitted": self._omit_checkbox.isChecked()}
        if normalized_family == LABOR:
            updates["recap_labor_classification"] = self._labor_edit_combo.currentText() or None
        elif normalized_family == EQUIPMENT:
            updates["equipment_category"] = self._equipment_edit_combo.currentText() or None
        elif normalized_family == MATERIAL:
            updates["vendor_name_normalized"] = self._vendor_edit_input.text().strip() or None

        self.apply_requested.emit(updates)


def _to_text(value: object) -> str:
    """Convert an optional value to UI-friendly text."""
    return "-" if value is None or value == "" else str(value)
