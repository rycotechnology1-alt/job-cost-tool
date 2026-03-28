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
        self._delete_button = QPushButton("Delete Profile")

        self._labor_mapping_table = QTableWidget(0, 3)
        self._equipment_mapping_table = QTableWidget(0, 2)
        self._labor_classifications_table = QTableWidget(0, 3)
        self._equipment_classifications_table = QTableWidget(0, 3)
        self._labor_rates_table = QTableWidget(0, 4)
        self._equipment_rates_table = QTableWidget(0, 2)
        self._labor_mapping_status_label = QLabel()
        self._equipment_mapping_status_label = QLabel()
        self._classification_status_label = QLabel()
        self._rates_status_label = QLabel()
        self._labor_mapping_add_button = QPushButton("Add")
        self._labor_mapping_remove_button = QPushButton("Remove")
        self._labor_mapping_save_button = QPushButton("Save")
        self._equipment_mapping_add_button = QPushButton("Add")
        self._equipment_mapping_remove_button = QPushButton("Remove")
        self._equipment_mapping_save_button = QPushButton("Save")
        self._save_classifications_button = QPushButton("Save Classifications")
        self._save_rates_button = QPushButton("Save Rates")

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
        actions_layout.addWidget(self._delete_button)
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

        self._labor_mapping_status_label.setWordWrap(True)
        self._labor_mapping_add_button.clicked.connect(self._add_labor_mapping_row)
        self._labor_mapping_remove_button.clicked.connect(lambda: self._remove_selected_rows(self._labor_mapping_table))
        self._labor_mapping_save_button.clicked.connect(self._save_labor_mappings)

        actions = QHBoxLayout()
        actions.addWidget(self._labor_mapping_add_button)
        actions.addWidget(self._labor_mapping_remove_button)
        actions.addStretch(1)
        actions.addWidget(self._labor_mapping_save_button)

        layout.addWidget(self._labor_mapping_status_label)
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

        self._equipment_mapping_status_label.setWordWrap(True)
        self._equipment_mapping_add_button.clicked.connect(self._add_equipment_mapping_row)
        self._equipment_mapping_remove_button.clicked.connect(lambda: self._remove_selected_rows(self._equipment_mapping_table))
        self._equipment_mapping_save_button.clicked.connect(self._save_equipment_mappings)

        actions = QHBoxLayout()
        actions.addWidget(self._equipment_mapping_add_button)
        actions.addWidget(self._equipment_mapping_remove_button)
        actions.addStretch(1)
        actions.addWidget(self._equipment_mapping_save_button)

        layout.addWidget(self._equipment_mapping_status_label)
        layout.addWidget(self._equipment_mapping_table, stretch=1)
        layout.addLayout(actions)
        return tab

    def _build_classifications_tab(self) -> QWidget:
        """Build the fixed-slot classifications editor tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._classification_status_label.setWordWrap(True)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_classification_group(
            title="Labor Slots",
            table=self._labor_classifications_table,
        ))
        splitter.addWidget(self._build_classification_group(
            title="Equipment Slots",
            table=self._equipment_classifications_table,
        ))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        self._save_classifications_button.clicked.connect(self._save_classifications)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(self._save_classifications_button)

        layout.addWidget(self._classification_status_label)
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

        self._rates_status_label.setWordWrap(True)
        self._save_rates_button.clicked.connect(self._save_rates)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(self._save_rates_button)

        layout.addWidget(self._rates_status_label)
        layout.addWidget(splitter, stretch=1)
        layout.addLayout(save_row)
        return tab

    def _build_classification_group(
        self,
        title: str,
        table: QTableWidget,
    ) -> QWidget:
        """Build a fixed-slot classification editor group."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Slot", "Label", "Active"])
        self._configure_table(table)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setColumnWidth(0, 80)
        table.setColumnWidth(1, 240)
        table.horizontalHeader().setStretchLastSection(False)
        layout.addWidget(table)
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
        self._delete_button.clicked.connect(self._delete_profile)

    def set_observed_labor_raw_values(self, values: list[str]) -> None:
        """Update temporary observed labor raw values used by the mapping editor."""
        self._view_model.set_observed_labor_raw_values(values)

    def _refresh_ui(self) -> None:
        """Refresh summary, available profiles, and editor tabs from the view-model."""
        self._refresh_profile_summary()
        self._refresh_profiles_table()
        self._refresh_labor_mapping_table()
        self._refresh_equipment_mapping_table()
        self._refresh_classifications_tables()
        self._refresh_rates_tables()
        self._update_editor_states()
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
        """Refresh labor and equipment fixed slot tables."""
        self._populate_slot_table(self._labor_classifications_table, self._view_model.labor_slots)
        self._populate_slot_table(self._equipment_classifications_table, self._view_model.equipment_slots)
        self._update_classification_editor_state()

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

    def _delete_profile(self) -> None:
        """Delete the currently selected non-default, non-active profile after confirmation."""
        profile_name = self._selected_profile_name()
        if not profile_name:
            return

        selected_profile = next(
            (profile for profile in self._view_model.profiles if profile.get("profile_name") == profile_name),
            None,
        )
        if selected_profile is None:
            QMessageBox.critical(self, "Profile Error", "The selected profile could not be found.")
            return

        if str(selected_profile.get("profile_name", "")).strip().casefold() == "default":
            QMessageBox.information(self, "Delete Not Allowed", "Default profile cannot be deleted.")
            return

        if bool(selected_profile.get("is_active_profile")):
            QMessageBox.information(
                self,
                "Delete Not Allowed",
                "Switch to another profile before deleting this one.",
            )
            return

        display_name = str(selected_profile.get("display_name", profile_name)).strip() or profile_name
        confirmation = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile '{display_name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            message = self._view_model.delete_profile(profile_name)
        except Exception as exc:
            QMessageBox.critical(self, "Profile Error", str(exc))
            return

        QMessageBox.information(self, "Profile Deleted", message)
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
        """Validate and persist fixed slot edits."""
        labor_slots = self._collect_slot_rows(self._labor_classifications_table)
        equipment_slots = self._collect_slot_rows(self._equipment_classifications_table)
        self._run_save_action(
            self._view_model.save_classification_slots,
            labor_slots,
            equipment_slots,
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
        self._delete_button.setEnabled(has_selection)

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

    def _populate_slot_table(self, table: QTableWidget, slots: list[dict[str, object]]) -> None:
        """Populate a fixed-slot classification table."""
        table.setRowCount(len(slots))
        for row_index, slot in enumerate(slots):
            slot_id = str(slot.get("slot_id", "")).strip()
            order_item = QTableWidgetItem(str(row_index + 1))
            order_item.setData(Qt.ItemDataRole.UserRole, slot_id)
            order_item.setToolTip(slot_id)
            order_item.setFlags(order_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_index, 0, order_item)

            label_item = QTableWidgetItem(str(slot.get("label", "")))
            table.setItem(row_index, 1, label_item)

            active_item = QTableWidgetItem("")
            active_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            active_item.setCheckState(
                Qt.CheckState.Checked if bool(slot.get("active")) else Qt.CheckState.Unchecked
            )
            table.setItem(row_index, 2, active_item)

    def _update_editor_states(self) -> None:
        """Apply default-profile read-only state across all editable admin tabs."""
        self._update_mapping_editor_state(
            table=self._labor_mapping_table,
            status_label=self._labor_mapping_status_label,
            add_button=self._labor_mapping_add_button,
            remove_button=self._labor_mapping_remove_button,
            save_button=self._labor_mapping_save_button,
            editable_columns={0, 2},
        )
        self._update_mapping_editor_state(
            table=self._equipment_mapping_table,
            status_label=self._equipment_mapping_status_label,
            add_button=self._equipment_mapping_add_button,
            remove_button=self._equipment_mapping_remove_button,
            save_button=self._equipment_mapping_save_button,
            editable_columns={0},
        )
        self._update_classification_editor_state()
        self._update_rates_editor_state()

    def _update_mapping_editor_state(
        self,
        *,
        table: QTableWidget,
        status_label: QLabel,
        add_button: QPushButton,
        remove_button: QPushButton,
        save_button: QPushButton,
        editable_columns: set[int],
    ) -> None:
        """Apply read-only state for a mapping editor table."""
        is_read_only = self._view_model.is_default_profile
        status_label.setText(
            self._view_model.read_only_message if is_read_only else "Edit mappings for the active profile."
        )
        add_button.setEnabled(not is_read_only)
        remove_button.setEnabled(not is_read_only)
        save_button.setEnabled(not is_read_only)
        if is_read_only:
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        else:
            table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
                | QAbstractItemView.EditTrigger.SelectedClicked
            )
        self._set_table_item_editability(table, editable_columns, not is_read_only)
        self._set_table_combo_widgets_enabled(table, not is_read_only)

    def _update_rates_editor_state(self) -> None:
        """Apply read-only state for the rates editors."""
        is_read_only = self._view_model.is_default_profile
        self._rates_status_label.setText(
            self._view_model.read_only_message if is_read_only else "Edit rates for the active profile."
        )
        self._save_rates_button.setEnabled(not is_read_only)
        for table, editable_columns in (
            (self._labor_rates_table, {1, 2, 3}),
            (self._equipment_rates_table, {1}),
        ):
            if is_read_only:
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            else:
                table.setEditTriggers(
                    QAbstractItemView.EditTrigger.DoubleClicked
                    | QAbstractItemView.EditTrigger.EditKeyPressed
                    | QAbstractItemView.EditTrigger.SelectedClicked
                )
            self._set_table_item_editability(table, editable_columns, not is_read_only)

    def _set_table_item_editability(self, table: QTableWidget, editable_columns: set[int], editable: bool) -> None:
        """Toggle edit flags for existing table items by column."""
        for row_index in range(table.rowCount()):
            for column_index in range(table.columnCount()):
                item = table.item(row_index, column_index)
                if item is None:
                    continue
                flags = item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                if column_index in editable_columns and editable:
                    flags |= Qt.ItemFlag.ItemIsEditable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags)

    def _set_table_combo_widgets_enabled(self, table: QTableWidget, enabled: bool) -> None:
        """Toggle enabled state for combo-box cell widgets in a table."""
        for row_index in range(table.rowCount()):
            for column_index in range(table.columnCount()):
                widget = table.cellWidget(row_index, column_index)
                if widget is not None:
                    widget.setEnabled(enabled)

    def _update_classification_editor_state(self) -> None:
        """Apply read-only messaging and enabled state for classification slots."""
        is_read_only = self._view_model.is_default_profile
        if is_read_only:
            self._classification_status_label.setText(self._view_model.read_only_message)
        else:
            self._classification_status_label.setText(
                "Edit fixed recap slot labels and active states for this profile."
            )

        self._save_classifications_button.setEnabled(not is_read_only)
        self._set_slot_table_read_only(self._labor_classifications_table, is_read_only)
        self._set_slot_table_read_only(self._equipment_classifications_table, is_read_only)

    def _set_slot_table_read_only(self, table: QTableWidget, is_read_only: bool) -> None:
        """Toggle slot table editability without changing its visible fixed rows."""
        if is_read_only:
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        else:
            table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked
                | QAbstractItemView.EditTrigger.EditKeyPressed
                | QAbstractItemView.EditTrigger.SelectedClicked
            )

        for row_index in range(table.rowCount()):
            label_item = table.item(row_index, 1)
            if label_item is not None:
                flags = label_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                if is_read_only:
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                else:
                    flags |= Qt.ItemFlag.ItemIsEditable
                label_item.setFlags(flags)

            active_item = table.item(row_index, 2)
            if active_item is not None:
                if is_read_only:
                    active_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                else:
                    active_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )

    def _collect_slot_rows(self, table: QTableWidget) -> list[dict[str, object]]:
        """Collect edited slot rows from a fixed-slot classification table."""
        rows: list[dict[str, object]] = []
        for row_index in range(table.rowCount()):
            slot_item = table.item(row_index, 0)
            label_item = table.item(row_index, 1)
            active_item = table.item(row_index, 2)
            rows.append(
                {
                    "slot_id": str(slot_item.data(Qt.ItemDataRole.UserRole)) if slot_item else "",
                    "label": label_item.text().strip() if label_item else "",
                    "active": bool(active_item and active_item.checkState() == Qt.CheckState.Checked),
                }
            )
        return rows

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
