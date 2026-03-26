"""Settings/Admin dialog for managing recap profiles."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from job_cost_tool.app.viewmodels.settings_view_model import SettingsViewModel


class SettingsDialog(QDialog):
    """Manage active profile selection and profile-scoped config editing."""

    profile_changed = Signal()
    settings_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view_model = SettingsViewModel()
        self._summary_labels: dict[str, QLabel] = {}
        self._profiles_table = QTableWidget(0, 3)
        self._set_active_button = QPushButton("Set Active Profile")
        self._duplicate_button = QPushButton("Duplicate Profile")

        self._labor_mapping_table = QTableWidget(0, 3)
        self._equipment_mapping_table = QTableWidget(0, 2)
        self._labor_classifications_table = QTableWidget(0, 1)
        self._equipment_classifications_table = QTableWidget(0, 1)
        self._labor_rates_table = QTableWidget(0, 4)
        self._equipment_rates_table = QTableWidget(0, 2)

        self._configure_window()
        self._build_layout()
        self._connect_signals()
        self._refresh_ui()

    def _configure_window(self) -> None:
        """Configure dialog window properties."""
        self.setWindowTitle("Settings / Admin")
        self.resize(1080, 720)
        self.setModal(True)

    def _build_layout(self) -> None:
        """Build the settings dialog layout."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_profiles_tab(), "Profiles")
        tabs.addTab(self._build_labor_mapping_tab(), "Labor Mapping")
        tabs.addTab(self._build_equipment_mapping_tab(), "Equipment Mapping")
        tabs.addTab(self._build_classifications_tab(), "Classifications")
        tabs.addTab(self._build_rates_tab(), "Rates")

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)

        root_layout.addWidget(tabs, stretch=1)
        root_layout.addWidget(button_box)

    def _build_profiles_tab(self) -> QWidget:
        """Build the profile management tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        summary_group = QGroupBox("Active Profile")
        summary_form = QFormLayout(summary_group)
        for key, label_text in (
            ("display_name", "Display Name"),
            ("profile_name", "Internal Name"),
            ("description", "Description"),
            ("version", "Version"),
            ("template_filename", "Template File"),
            ("template_path", "Template Path"),
        ):
            label = QLabel("-")
            label.setWordWrap(True)
            self._summary_labels[key] = label
            summary_form.addRow(label_text, label)

        profiles_group = QGroupBox("Available Profiles")
        profiles_layout = QVBoxLayout(profiles_group)
        self._profiles_table.setHorizontalHeaderLabels(["Display Name", "Profile Name", "Description"])
        self._configure_table(self._profiles_table)
        self._profiles_table.setColumnWidth(0, 220)
        self._profiles_table.setColumnWidth(1, 170)
        self._profiles_table.horizontalHeader().setStretchLastSection(True)
        profiles_layout.addWidget(self._profiles_table)

        actions_layout = QHBoxLayout()
        actions_layout.addWidget(self._set_active_button)
        actions_layout.addWidget(self._duplicate_button)
        actions_layout.addStretch(1)

        layout.addWidget(summary_group)
        layout.addWidget(profiles_group, stretch=1)
        layout.addLayout(actions_layout)
        return tab

    def _build_labor_mapping_tab(self) -> QWidget:
        """Build the labor mapping editor tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._labor_mapping_table.setHorizontalHeaderLabels(["Raw Value", "Target Classification", "Notes"])
        self._configure_table(self._labor_mapping_table)
        self._labor_mapping_table.setColumnWidth(0, 240)
        self._labor_mapping_table.setColumnWidth(1, 260)
        self._labor_mapping_table.horizontalHeader().setStretchLastSection(True)

        actions = self._build_editor_actions(
            add_handler=lambda: self._add_labor_mapping_row(),
            remove_handler=lambda: self._remove_selected_rows(self._labor_mapping_table),
            save_handler=self._save_labor_mappings,
        )

        layout.addWidget(self._labor_mapping_table, stretch=1)
        layout.addLayout(actions)
        return tab

    def _build_equipment_mapping_tab(self) -> QWidget:
        """Build the equipment mapping editor tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._equipment_mapping_table.setHorizontalHeaderLabels(["Raw Description / Pattern", "Target Equipment Category"])
        self._configure_table(self._equipment_mapping_table)
        self._equipment_mapping_table.setColumnWidth(0, 360)
        self._equipment_mapping_table.horizontalHeader().setStretchLastSection(True)

        actions = self._build_editor_actions(
            add_handler=lambda: self._add_equipment_mapping_row(),
            remove_handler=lambda: self._remove_selected_rows(self._equipment_mapping_table),
            save_handler=self._save_equipment_mappings,
        )

        layout.addWidget(self._equipment_mapping_table, stretch=1)
        layout.addLayout(actions)
        return tab

    def _build_classifications_tab(self) -> QWidget:
        """Build the target classifications editor tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_classification_group(
            title="Labor Classifications",
            table=self._labor_classifications_table,
            add_handler=lambda: self._add_simple_row(self._labor_classifications_table),
            remove_handler=lambda: self._remove_selected_rows(self._labor_classifications_table),
        ))
        splitter.addWidget(self._build_classification_group(
            title="Equipment Classifications",
            table=self._equipment_classifications_table,
            add_handler=lambda: self._add_simple_row(self._equipment_classifications_table),
            remove_handler=lambda: self._remove_selected_rows(self._equipment_classifications_table),
        ))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        save_button = QPushButton("Save Classifications")
        save_button.clicked.connect(self._save_classifications)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(save_button)

        layout.addWidget(splitter, stretch=1)
        layout.addLayout(save_row)
        return tab

    def _build_rates_tab(self) -> QWidget:
        """Build the profile-scoped rates editor tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_rates_group(
            title="Labor Rates",
            table=self._labor_rates_table,
            headers=["Classification", "Standard Rate", "Overtime Rate", "Double Time Rate"],
            read_only_first_column=True,
        ))
        splitter.addWidget(self._build_rates_group(
            title="Equipment Rates",
            table=self._equipment_rates_table,
            headers=["Category", "Rate"],
            read_only_first_column=True,
        ))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        save_button = QPushButton("Save Rates")
        save_button.clicked.connect(self._save_rates)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(save_button)

        layout.addWidget(splitter, stretch=1)
        layout.addLayout(save_row)
        return tab

    def _build_classification_group(
        self,
        title: str,
        table: QTableWidget,
        add_handler,
        remove_handler,
    ) -> QWidget:
        """Build a classification editor group."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        table.setHorizontalHeaderLabels(["Label"])
        self._configure_table(table)
        table.horizontalHeader().setStretchLastSection(True)
        actions = self._build_editor_actions(add_handler, remove_handler, None)
        layout.addWidget(table)
        layout.addLayout(actions)
        return group

    def _build_rates_group(
        self,
        title: str,
        table: QTableWidget,
        headers: list[str],
        read_only_first_column: bool,
    ) -> QWidget:
        """Build a rates editor group with a simple table."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        self._configure_table(table)
        table.horizontalHeader().setStretchLastSection(True)
        if read_only_first_column:
            table.setColumnWidth(0, 260)
        layout.addWidget(table)
        return group

    def _build_editor_actions(self, add_handler, remove_handler, save_handler) -> QHBoxLayout:
        """Build add/remove/save button row for a table editor."""
        layout = QHBoxLayout()
        add_button = QPushButton("Add")
        remove_button = QPushButton("Remove")
        add_button.clicked.connect(add_handler)
        remove_button.clicked.connect(remove_handler)
        layout.addWidget(add_button)
        layout.addWidget(remove_button)
        layout.addStretch(1)
        if save_handler is not None:
            save_button = QPushButton("Save")
            save_button.clicked.connect(save_handler)
            layout.addWidget(save_button)
        return layout

    def _connect_signals(self) -> None:
        """Connect dialog and view-model signals."""
        self._view_model.state_changed.connect(self._refresh_ui)
        self._profiles_table.itemSelectionChanged.connect(self._update_action_state)
        self._set_active_button.clicked.connect(self._set_active_profile)
        self._duplicate_button.clicked.connect(self._duplicate_profile)

    def _refresh_ui(self) -> None:
        """Refresh summary, available profiles, and editor tabs from the view-model."""
        self._refresh_profile_summary()
        self._refresh_profiles_table()
        self._refresh_labor_mapping_table()
        self._refresh_equipment_mapping_table()
        self._refresh_classifications_tables()
        self._refresh_rates_tables()
        self._update_action_state()

    def _refresh_profile_summary(self) -> None:
        """Refresh the active-profile summary area."""
        active_profile = self._view_model.active_profile
        for key, label in self._summary_labels.items():
            value = active_profile.get(key)
            label.setText("-" if value in {None, ""} else str(value))

    def _refresh_profiles_table(self) -> None:
        """Refresh the available profiles table."""
        profiles = self._view_model.profiles
        selected_profile_name = self._selected_profile_name() or self._view_model.active_profile.get("profile_name")
        self._profiles_table.setRowCount(len(profiles))
        selected_row = None
        for row_index, profile in enumerate(profiles):
            display_name = str(profile.get("display_name", ""))
            profile_name = str(profile.get("profile_name", ""))
            description = str(profile.get("description", ""))
            values = [display_name, profile_name, description]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, profile_name)
                if profile.get("is_active_profile"):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self._profiles_table.setItem(row_index, column_index, item)
            if profile_name == selected_profile_name:
                selected_row = row_index

        if selected_row is not None:
            self._profiles_table.selectRow(selected_row)
        elif profiles:
            self._profiles_table.selectRow(0)

    def _refresh_labor_mapping_table(self) -> None:
        """Refresh the labor mapping editor table."""
        rows = self._view_model.labor_mapping_rows
        self._labor_mapping_table.setRowCount(len(rows))
        labor_targets = self._view_model.labor_classifications
        for row_index, row in enumerate(rows):
            self._labor_mapping_table.setItem(row_index, 0, QTableWidgetItem(row.get("raw_value", "")))
            self._set_combo_cell(
                self._labor_mapping_table,
                row_index,
                1,
                labor_targets,
                row.get("target_classification", ""),
            )
            self._labor_mapping_table.setItem(row_index, 2, QTableWidgetItem(row.get("notes", "")))

    def _refresh_equipment_mapping_table(self) -> None:
        """Refresh the equipment mapping editor table."""
        rows = self._view_model.equipment_mapping_rows
        self._equipment_mapping_table.setRowCount(len(rows))
        equipment_targets = self._view_model.equipment_classifications
        for row_index, row in enumerate(rows):
            self._equipment_mapping_table.setItem(row_index, 0, QTableWidgetItem(row.get("raw_pattern", "")))
            self._set_combo_cell(
                self._equipment_mapping_table,
                row_index,
                1,
                equipment_targets,
                row.get("target_category", ""),
            )

    def _refresh_classifications_tables(self) -> None:
        """Refresh labor and equipment classification lists."""
        self._populate_single_column_table(self._labor_classifications_table, self._view_model.labor_classifications)
        self._populate_single_column_table(self._equipment_classifications_table, self._view_model.equipment_classifications)

    def _refresh_rates_tables(self) -> None:
        """Refresh labor and equipment rate tables."""
        labor_rows = self._view_model.labor_rate_rows
        self._labor_rates_table.setRowCount(len(labor_rows))
        for row_index, row in enumerate(labor_rows):
            self._set_read_only_item(self._labor_rates_table, row_index, 0, row.get("classification", ""))
            self._labor_rates_table.setItem(row_index, 1, QTableWidgetItem(row.get("standard_rate", "")))
            self._labor_rates_table.setItem(row_index, 2, QTableWidgetItem(row.get("overtime_rate", "")))
            self._labor_rates_table.setItem(row_index, 3, QTableWidgetItem(row.get("double_time_rate", "")))

        equipment_rows = self._view_model.equipment_rate_rows
        self._equipment_rates_table.setRowCount(len(equipment_rows))
        for row_index, row in enumerate(equipment_rows):
            self._set_read_only_item(self._equipment_rates_table, row_index, 0, row.get("category", ""))
            self._equipment_rates_table.setItem(row_index, 1, QTableWidgetItem(row.get("rate", "")))

    def _set_active_profile(self) -> None:
        """Set the currently selected profile as active."""
        profile_name = self._selected_profile_name()
        if not profile_name:
            return
        try:
            message = self._view_model.set_active_profile(profile_name)
        except Exception as exc:
            QMessageBox.critical(self, "Profile Error", str(exc))
            return

        QMessageBox.information(self, "Profile Updated", message)
        self.profile_changed.emit()
        self.settings_changed.emit()

    def _duplicate_profile(self) -> None:
        """Duplicate the currently selected profile using a simple metadata dialog."""
        source_profile_name = self._selected_profile_name()
        if not source_profile_name:
            return

        source_profile = next(
            (profile for profile in self._view_model.profiles if profile.get("profile_name") == source_profile_name),
            None,
        )
        if source_profile is None:
            QMessageBox.critical(self, "Profile Error", "The selected source profile could not be found.")
            return

        duplicate_dialog = DuplicateProfileDialog(
            source_display_name=str(source_profile.get("display_name", source_profile_name)),
            parent=self,
        )
        if duplicate_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            message = self._view_model.duplicate_profile(
                source_profile_name=source_profile_name,
                new_profile_name=duplicate_dialog.profile_name,
                display_name=duplicate_dialog.display_name,
                description=duplicate_dialog.description,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Profile Error", str(exc))
            return

        QMessageBox.information(self, "Profile Created", message)
        self.settings_changed.emit()

    def _save_labor_mappings(self) -> None:
        """Validate and persist labor mapping edits."""
        rows = []
        for row_index in range(self._labor_mapping_table.rowCount()):
            raw_value = self._item_text(self._labor_mapping_table, row_index, 0)
            target_classification = self._combo_text(self._labor_mapping_table, row_index, 1)
            notes = self._item_text(self._labor_mapping_table, row_index, 2)
            if not any((raw_value, target_classification, notes)):
                continue
            rows.append(
                {
                    "raw_value": raw_value,
                    "target_classification": target_classification,
                    "notes": notes,
                }
            )

        self._run_save_action(
            self._view_model.save_labor_mappings,
            rows,
            success_title="Labor Mappings Saved",
        )

    def _save_equipment_mappings(self) -> None:
        """Validate and persist equipment mapping edits."""
        rows = []
        for row_index in range(self._equipment_mapping_table.rowCount()):
            raw_pattern = self._item_text(self._equipment_mapping_table, row_index, 0)
            target_category = self._combo_text(self._equipment_mapping_table, row_index, 1)
            if not any((raw_pattern, target_category)):
                continue
            rows.append(
                {
                    "raw_pattern": raw_pattern,
                    "target_category": target_category,
                }
            )

        self._run_save_action(
            self._view_model.save_equipment_mappings,
            rows,
            success_title="Equipment Mappings Saved",
        )

    def _save_classifications(self) -> None:
        """Validate and persist classification list edits."""
        labor_values = self._collect_single_column_values(self._labor_classifications_table)
        equipment_values = self._collect_single_column_values(self._equipment_classifications_table)
        self._run_save_action(
            self._view_model.save_classifications,
            labor_values,
            equipment_values,
            success_title="Classifications Saved",
        )

    def _save_rates(self) -> None:
        """Validate and persist rate edits."""
        labor_rows = []
        for row_index in range(self._labor_rates_table.rowCount()):
            labor_rows.append(
                {
                    "classification": self._item_text(self._labor_rates_table, row_index, 0),
                    "standard_rate": self._item_text(self._labor_rates_table, row_index, 1),
                    "overtime_rate": self._item_text(self._labor_rates_table, row_index, 2),
                    "double_time_rate": self._item_text(self._labor_rates_table, row_index, 3),
                }
            )

        equipment_rows = []
        for row_index in range(self._equipment_rates_table.rowCount()):
            equipment_rows.append(
                {
                    "category": self._item_text(self._equipment_rates_table, row_index, 0),
                    "rate": self._item_text(self._equipment_rates_table, row_index, 1),
                }
            )

        self._run_save_action(self._view_model.save_rates, labor_rows, equipment_rows, success_title="Rates Saved")

    def _run_save_action(self, handler, *args, success_title: str) -> None:
        """Run a save action with common success/error messaging."""
        try:
            message = handler(*args)
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return

        QMessageBox.information(self, success_title, message)
        self.settings_changed.emit()

    def _update_action_state(self) -> None:
        """Update action button enabled state based on selection."""
        selected_profile_name = self._selected_profile_name()
        active_profile_name = str(self._view_model.active_profile.get("profile_name", "")).strip()
        has_selection = bool(selected_profile_name)
        self._set_active_button.setEnabled(has_selection and selected_profile_name != active_profile_name)
        self._duplicate_button.setEnabled(has_selection)

    def _selected_profile_name(self) -> Optional[str]:
        """Return the currently selected profile name from the table."""
        selected_items = self._profiles_table.selectedItems()
        if not selected_items:
            return None
        row = selected_items[0].row()
        first_item = self._profiles_table.item(row, 0)
        if first_item is None:
            return None
        profile_name = first_item.data(Qt.ItemDataRole.UserRole)
        return str(profile_name) if profile_name else None

    def _add_labor_mapping_row(self) -> None:
        """Append a new editable labor mapping row."""
        row_index = self._labor_mapping_table.rowCount()
        self._labor_mapping_table.insertRow(row_index)
        self._labor_mapping_table.setItem(row_index, 0, QTableWidgetItem(""))
        self._set_combo_cell(self._labor_mapping_table, row_index, 1, self._view_model.labor_classifications, "")
        self._labor_mapping_table.setItem(row_index, 2, QTableWidgetItem(""))

    def _add_equipment_mapping_row(self) -> None:
        """Append a new editable equipment mapping row."""
        row_index = self._equipment_mapping_table.rowCount()
        self._equipment_mapping_table.insertRow(row_index)
        self._equipment_mapping_table.setItem(row_index, 0, QTableWidgetItem(""))
        self._set_combo_cell(self._equipment_mapping_table, row_index, 1, self._view_model.equipment_classifications, "")

    def _add_simple_row(self, table: QTableWidget) -> None:
        """Append a new editable single-column row."""
        row_index = table.rowCount()
        table.insertRow(row_index)
        table.setItem(row_index, 0, QTableWidgetItem(""))

    def _remove_selected_rows(self, table: QTableWidget) -> None:
        """Remove the currently selected rows from a table."""
        selected_rows = sorted({index.row() for index in table.selectionModel().selectedRows()}, reverse=True)
        for row_index in selected_rows:
            table.removeRow(row_index)

    def _configure_table(self, table: QTableWidget) -> None:
        """Apply a consistent editable-table configuration."""
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)

    def _populate_single_column_table(self, table: QTableWidget, values: list[str]) -> None:
        """Populate a one-column editable list table."""
        table.setRowCount(len(values))
        for row_index, value in enumerate(values):
            table.setItem(row_index, 0, QTableWidgetItem(value))

    def _set_combo_cell(
        self,
        table: QTableWidget,
        row_index: int,
        column_index: int,
        options: list[str],
        current_text: str,
    ) -> None:
        """Set a combo-box cell widget for a mapping target column."""
        combo_box = QComboBox()
        combo_box.addItem("")
        combo_box.addItems(options)
        combo_box.setCurrentText(current_text)
        table.setCellWidget(row_index, column_index, combo_box)

    def _set_read_only_item(self, table: QTableWidget, row_index: int, column_index: int, value: str) -> None:
        """Insert a non-editable table item."""
        item = QTableWidgetItem(value)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row_index, column_index, item)

    def _collect_single_column_values(self, table: QTableWidget) -> list[str]:
        """Collect non-empty values from a single-column editable table."""
        values: list[str] = []
        for row_index in range(table.rowCount()):
            text = self._item_text(table, row_index, 0)
            if text:
                values.append(text)
        return values

    def _item_text(self, table: QTableWidget, row_index: int, column_index: int) -> str:
        """Return table item text safely."""
        item = table.item(row_index, column_index)
        return item.text().strip() if item else ""

    def _combo_text(self, table: QTableWidget, row_index: int, column_index: int) -> str:
        """Return combo-box cell text safely."""
        combo_box = table.cellWidget(row_index, column_index)
        if isinstance(combo_box, QComboBox):
            return combo_box.currentText().strip()
        return ""


class DuplicateProfileDialog(QDialog):
    """Collect the minimal metadata needed to duplicate a profile bundle."""

    def __init__(self, source_display_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_display_name = source_display_name
        self._profile_name_input = QLineEdit()
        self._display_name_input = QLineEdit()
        self._description_input = QLineEdit()

        self._configure_window()
        self._build_layout()

    @property
    def profile_name(self) -> str:
        """Return the requested new internal profile name."""
        return self._profile_name_input.text().strip()

    @property
    def display_name(self) -> str:
        """Return the requested new display name."""
        return self._display_name_input.text().strip()

    @property
    def description(self) -> str:
        """Return the optional description for the new profile."""
        return self._description_input.text().strip()

    def accept(self) -> None:
        """Validate basic required input before closing."""
        if not self.profile_name:
            QMessageBox.warning(self, "Missing Profile Name", "Enter a new internal profile name.")
            return
        if not self.display_name:
            QMessageBox.warning(self, "Missing Display Name", "Enter a display name for the new profile.")
            return
        super().accept()

    def _configure_window(self) -> None:
        """Configure dialog window properties."""
        self.setWindowTitle("Duplicate Profile")
        self.resize(440, 220)
        self.setModal(True)

    def _build_layout(self) -> None:
        """Build the duplicate-profile input form."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        intro_label = QLabel(f"Create a new profile by copying: {self._source_display_name}")
        intro_label.setWordWrap(True)

        form_layout = QFormLayout()
        form_layout.addRow("New Internal Name", self._profile_name_input)
        form_layout.addRow("Display Name", self._display_name_input)
        form_layout.addRow("Description", self._description_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        root_layout.addWidget(intro_label)
        root_layout.addLayout(form_layout)
        root_layout.addWidget(button_box)
