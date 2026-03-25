"""Main desktop review window for the Job Cost Tool."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from job_cost_tool.app.viewmodels.review_view_model import ReviewViewModel
from job_cost_tool.app.widgets.issues_panel import IssuesPanel
from job_cost_tool.app.widgets.record_detail_panel import RecordDetailPanel
from job_cost_tool.app.widgets.record_table import RecordTable


class MainWindow(QMainWindow):
    """Main review workflow window for inspecting parsed, normalized, and corrected records."""

    def __init__(self) -> None:
        super().__init__()
        self._view_model = ReviewViewModel()
        self._record_table = RecordTable()
        self._detail_panel = RecordDetailPanel()
        self._issues_panel = IssuesPanel()
        self._open_button = QPushButton("Open PDF")
        self._refresh_button = QPushButton("Reprocess")
        self._filter_combo = QComboBox()
        self._export_button = QPushButton("Export")
        self._status_label = QLabel("Open a PDF to begin review.")

        self._configure_window()
        self._build_layout()
        self._connect_signals()
        self._detail_panel.set_edit_options(self._view_model.labor_options, self._view_model.equipment_options)
        self._refresh_ui()

    def _configure_window(self) -> None:
        """Configure top-level window properties."""
        self.setWindowTitle("Job Cost Tool")
        self.resize(1440, 900)

    def _build_layout(self) -> None:
        """Build the main review window layout."""
        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        filter_label = QLabel("Filter")
        self._filter_combo.addItems(ReviewViewModel.FILTER_OPTIONS)
        self._export_button.setToolTip("Export is not implemented yet.")
        self._status_label.setWordWrap(True)

        controls_layout.addWidget(self._open_button)
        controls_layout.addWidget(self._refresh_button)
        controls_layout.addSpacing(12)
        controls_layout.addWidget(filter_label)
        controls_layout.addWidget(self._filter_combo)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self._export_button)

        horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        horizontal_splitter.addWidget(self._record_table)
        horizontal_splitter.addWidget(self._detail_panel)
        horizontal_splitter.setStretchFactor(0, 3)
        horizontal_splitter.setStretchFactor(1, 2)

        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        vertical_splitter.addWidget(horizontal_splitter)
        vertical_splitter.addWidget(self._issues_panel)
        vertical_splitter.setStretchFactor(0, 4)
        vertical_splitter.setStretchFactor(1, 1)

        root_layout.addLayout(controls_layout)
        root_layout.addWidget(self._status_label)
        root_layout.addWidget(vertical_splitter, stretch=1)

        self.setCentralWidget(central_widget)

    def _connect_signals(self) -> None:
        """Connect UI events and view-model signals."""
        self._open_button.clicked.connect(self._choose_pdf)
        self._refresh_button.clicked.connect(self._view_model.reload_current_pdf)
        self._filter_combo.currentTextChanged.connect(self._view_model.set_filter_mode)
        self._export_button.clicked.connect(self._show_export_placeholder)
        self._record_table.record_selected.connect(self._view_model.set_selected_record)
        self._detail_panel.apply_requested.connect(self._view_model.apply_updates_to_selected_record)

        self._view_model.state_changed.connect(self._refresh_ui)
        self._view_model.error_occurred.connect(self._show_error)

    def _choose_pdf(self) -> None:
        """Prompt the user to select a PDF file for processing."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Job Cost Report",
            "",
            "PDF Files (*.pdf)",
        )
        if file_path:
            self._view_model.load_pdf(file_path)

    def _refresh_ui(self) -> None:
        """Refresh widgets from the current view-model state."""
        self._status_label.setText(self._view_model.status_text)
        self._record_table.set_records(self._view_model.filtered_records)
        self._record_table.select_record(self._view_model.selected_record)
        self._detail_panel.set_record(self._view_model.selected_record)
        self._issues_panel.set_issues(self._view_model.blocking_issues)

        self._refresh_button.setEnabled(self._view_model.current_pdf_path is not None and not self._view_model.is_processing)
        self._open_button.setEnabled(not self._view_model.is_processing)
        self._filter_combo.setEnabled(not self._view_model.is_processing)
        self._export_button.setEnabled(self._view_model.can_export)

    def _show_export_placeholder(self) -> None:
        """Show placeholder messaging for export until that phase is implemented."""
        QMessageBox.information(
            self,
            "Export Not Implemented",
            "Export is not implemented yet. Resolve review issues here first, then add export in a later phase.",
        )

    def _show_error(self, message: str) -> None:
        """Show a user-facing error dialog."""
        QMessageBox.critical(self, "Pipeline Error", message)
