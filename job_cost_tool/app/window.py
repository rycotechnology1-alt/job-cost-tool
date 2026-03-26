"""Main desktop review window for the Job Cost Tool."""

from __future__ import annotations

from pathlib import Path

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
from job_cost_tool.core.config import ConfigLoader
from job_cost_tool.services.export_service import export_records_to_recap


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
        self._export_button.setToolTip("Export the reviewed recap workbook when all blocking issues are resolved.")
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
        self._export_button.clicked.connect(self._export_records)
        self._record_table.record_selected.connect(self._view_model.set_selected_record)
        self._detail_panel.apply_requested.connect(self._view_model.apply_updates_to_selected_record)

        self._view_model.state_changed.connect(self._refresh_ui)
        self._view_model.error_occurred.connect(self._show_pipeline_error)

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

    def _export_records(self) -> None:
        """Export the reviewed record set into the configured recap template."""
        if not self._view_model.can_export:
            return

        template_path = self._resolve_template_path()
        if template_path is None:
            self._show_export_error("Template Missing", "No recap template was selected.")
            return

        suggested_output = self._build_suggested_output_path(template_path)
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Recap Workbook",
            str(suggested_output),
            "Excel Workbook (*.xlsx)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".xlsx"):
            output_path = f"{output_path}.xlsx"

        output_path_obj = Path(output_path)
        if output_path_obj.exists() and not self._confirm_overwrite(output_path_obj):
            return

        try:
            export_records_to_recap(
                records=self._view_model.records,
                template_path=str(template_path),
                output_path=str(output_path_obj),
            )
        except Exception as exc:
            title = self._export_error_title(str(exc))
            self._show_export_error(title, str(exc))
            return

        QMessageBox.information(
            self,
            "Export Complete",
            f"Export completed successfully.\n\nSaved to:\n{output_path_obj}",
        )

    def _resolve_template_path(self) -> Path | None:
        """Resolve the recap template path, preferring the configured default template when available."""
        try:
            template_map = ConfigLoader().get_recap_template_map()
        except Exception:
            template_map = {}

        configured_path = str(template_map.get("default_template_path", "")).strip()
        if configured_path:
            configured_template = Path(configured_path).expanduser()
            if configured_template.is_file():
                return configured_template

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Recap Template",
            "",
            "Excel Workbook (*.xlsx)",
        )
        return Path(file_path) if file_path else None

    def _build_suggested_output_path(self, template_path: Path) -> Path:
        """Build a default output path for the save dialog."""
        if self._view_model.current_pdf_path:
            pdf_path = Path(self._view_model.current_pdf_path)
            return pdf_path.with_name(f"{pdf_path.stem} Recap.xlsx")
        return template_path.with_name(f"{template_path.stem} Output.xlsx")

    def _confirm_overwrite(self, output_path: Path) -> bool:
        """Prompt the user before overwriting an existing export file."""
        response = QMessageBox.question(
            self,
            "Overwrite Existing File",
            f"The selected output file already exists:\n{output_path}\n\nDo you want to overwrite it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _export_error_title(self, message: str) -> str:
        """Choose a clearer dialog title for common export failures."""
        lowered = message.casefold()
        if "blocked until all blocking issues are resolved" in lowered:
            return "Export Blocked"
        if "template workbook was not found" in lowered or "template worksheet" in lowered or "valid excel file" in lowered:
            return "Template Error"
        if "currently open" in lowered:
            return "Output File In Use"
        if "exceeds template capacity" in lowered:
            return "Template Capacity Exceeded"
        return "Export Failed"

    def _show_pipeline_error(self, message: str) -> None:
        """Show a user-facing error dialog for pipeline failures."""
        QMessageBox.critical(self, "Pipeline Error", message)

    def _show_export_error(self, title: str, message: str) -> None:
        """Show a user-facing error dialog for export failures."""
        QMessageBox.critical(self, title, message)
