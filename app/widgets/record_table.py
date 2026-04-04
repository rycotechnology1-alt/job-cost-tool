"""Record table widget for browsing validated records."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from core.models.record import Record

_OMITTED_ROW_COLOR = QColor("#FDECEC")


class RecordTable(QTableWidget):
    """Table widget that displays validated records and supports row selection."""

    COLUMN_HEADERS = [
        "Page",
        "Phase",
        "Type",
        "Raw Description",
        "Labor Class",
        "Equipment Category",
        "Vendor",
        "Confidence",
        "Warnings",
    ]

    record_selected = Signal(object)

    def __init__(self) -> None:
        super().__init__(0, len(self.COLUMN_HEADERS))
        self._records: list[Record] = []
        self._suppress_selection_signal = False
        self.setHorizontalHeaderLabels(self.COLUMN_HEADERS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setColumnWidth(0, 60)
        self.setColumnWidth(1, 70)
        self.setColumnWidth(2, 110)
        self.setColumnWidth(3, 460)
        self.setColumnWidth(4, 170)
        self.setColumnWidth(5, 170)
        self.setColumnWidth(6, 170)
        self.setColumnWidth(7, 90)
        self.itemSelectionChanged.connect(self._emit_selected_record)

    def set_records(self, records: list[Record]) -> None:
        """Replace the table contents with a new record set."""
        self._suppress_selection_signal = True
        try:
            self._records = list(records)
            self.clearContents()
            self.setRowCount(len(self._records))

            for row_index, record in enumerate(self._records):
                values = [
                    str(record.source_page or ""),
                    record.phase_code or "",
                    record.record_type_normalized or record.record_type,
                    record.raw_description,
                    record.effective_labor_classification() or "",
                    record.equipment_category or "",
                    record.vendor_name_normalized or record.vendor_name or "",
                    f"{record.confidence:.1f}",
                    _summarize_warnings(record),
                ]
                for column_index, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column_index == 0:
                        item.setData(Qt.ItemDataRole.UserRole, record)
                    if record.is_omitted:
                        item.setBackground(_OMITTED_ROW_COLOR)
                        item.setToolTip("This record is omitted from export.")
                    self.setItem(row_index, column_index, item)

            if not self._records:
                self.clearSelection()
        finally:
            self._suppress_selection_signal = False

    def select_record(self, record: Optional[Record]) -> None:
        """Select the table row corresponding to the provided record."""
        self._suppress_selection_signal = True
        try:
            if record is None:
                self.clearSelection()
                return

            for row_index, existing_record in enumerate(self._records):
                if existing_record is record:
                    self.selectRow(row_index)
                    return

            self.clearSelection()
        finally:
            self._suppress_selection_signal = False

    def _emit_selected_record(self) -> None:
        """Emit the currently selected record object."""
        if self._suppress_selection_signal:
            return

        selected_indexes = self.selectionModel().selectedRows()
        if not selected_indexes:
            self.record_selected.emit(None)
            return

        row_index = selected_indexes[0].row()
        if 0 <= row_index < len(self._records):
            self.record_selected.emit(self._records[row_index])
            return

        self.record_selected.emit(None)


def _summarize_warnings(record: Record) -> str:
    """Build a short warning summary for table display."""
    if record.is_omitted:
        return "Omitted"
    if not record.warnings:
        return ""
    if record.has_blocking_warning():
        return f"Blocking ({len(record.warnings)})"
    return f"Warnings ({len(record.warnings)})"
