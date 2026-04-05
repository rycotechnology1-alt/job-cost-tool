"""Qt adapter for profile settings and lightweight admin actions."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from core.config import ProfileManager
from services.settings_workflow_service import (
    SettingsWorkflowService,
    _active_labels_from_slots,
    _build_equipment_mapping_rows,
    _build_labor_mapping_rows,
    _build_slot_label_rename_map,
    _dedupe_casefold_preserving_order,
    _rename_equipment_mapping_config_targets,
    _rename_labor_mapping_config_targets,
    _rename_rates_config_targets,
    _rename_recap_template_map_targets,
    _validate_equipment_classification_references,
    _validate_labor_classification_references,
    _validate_slot_rows,
    persist_observed_equipment_raw_values,
    persist_observed_labor_raw_values,
)


class SettingsViewModel(QObject):
    """Keep Qt signals/state separate while delegating settings workflow logic to services."""

    state_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._workflow = SettingsWorkflowService(profile_manager=ProfileManager())

    @property
    def profiles(self) -> list[dict[str, Any]]:
        return self._workflow.profiles

    @property
    def active_profile(self) -> dict[str, Any]:
        return self._workflow.active_profile

    @property
    def labor_mapping_rows(self) -> list[dict[str, str]]:
        return self._workflow.labor_mapping_rows

    @property
    def equipment_mapping_rows(self) -> list[dict[str, str]]:
        return self._workflow.equipment_mapping_rows

    @property
    def labor_slots(self) -> list[dict[str, Any]]:
        return self._workflow.labor_slots

    @property
    def equipment_slots(self) -> list[dict[str, Any]]:
        return self._workflow.equipment_slots

    @property
    def labor_classifications(self) -> list[str]:
        return self._workflow.labor_classifications

    @property
    def equipment_classifications(self) -> list[str]:
        return self._workflow.equipment_classifications

    @property
    def is_default_profile(self) -> bool:
        return self._workflow.is_default_profile

    @property
    def is_default_profile_locked(self) -> bool:
        return self._workflow.is_default_profile_locked

    @property
    def is_active_profile_editable(self) -> bool:
        return self._workflow.is_active_profile_editable

    @property
    def is_default_profile_unlocked(self) -> bool:
        return self._workflow.is_default_profile_unlocked

    @property
    def read_only_message(self) -> str:
        return self._workflow.read_only_message

    @property
    def labor_rate_rows(self) -> list[dict[str, str]]:
        return self._workflow.labor_rate_rows

    @property
    def equipment_rate_rows(self) -> list[dict[str, str]]:
        return self._workflow.equipment_rate_rows

    @property
    def default_omit_rule_rows(self) -> list[dict[str, str]]:
        return self._workflow.default_omit_rule_rows

    @property
    def available_default_omit_phase_options(self) -> list[dict[str, str]]:
        return self._workflow.available_default_omit_phase_options

    def reload(self) -> None:
        self._workflow.reload()
        self.state_changed.emit()

    def set_active_profile(self, profile_name: str) -> str:
        message = self._workflow.set_active_profile(profile_name)
        self.state_changed.emit()
        return message

    def duplicate_profile(
        self,
        source_profile_name: str,
        new_profile_name: str,
        display_name: str,
        description: str = "",
    ) -> str:
        message = self._workflow.duplicate_profile(
            source_profile_name=source_profile_name,
            new_profile_name=new_profile_name,
            display_name=display_name,
            description=description,
        )
        self.state_changed.emit()
        return message

    def delete_profile(self, profile_name: str) -> str:
        message = self._workflow.delete_profile(profile_name)
        self.state_changed.emit()
        return message

    def unlock_default_profile(self) -> str:
        message = self._workflow.unlock_default_profile()
        self.state_changed.emit()
        return message

    def lock_default_profile(self) -> str:
        message = self._workflow.lock_default_profile()
        self.state_changed.emit()
        return message

    def set_observed_phase_options(self, values: list[dict[str, str]]) -> None:
        if self._workflow.set_observed_phase_options(values):
            self.state_changed.emit()

    def set_observed_labor_raw_values(self, values: list[str]) -> None:
        if self._workflow.set_observed_labor_raw_values(values):
            self.state_changed.emit()

    def set_observed_equipment_raw_values(self, values: list[str]) -> None:
        if self._workflow.set_observed_equipment_raw_values(values):
            self.state_changed.emit()

    def save_default_omit_rules(self, rows: list[dict[str, str]]) -> str:
        message = self._workflow.save_default_omit_rules(rows)
        self.state_changed.emit()
        return message

    def save_labor_mappings(self, rows: list[dict[str, str]]) -> str:
        message = self._workflow.save_labor_mappings(rows)
        self.state_changed.emit()
        return message

    def save_equipment_mappings(self, rows: list[dict[str, str]]) -> str:
        message = self._workflow.save_equipment_mappings(rows)
        self.state_changed.emit()
        return message

    def save_classification_slots(
        self,
        labor_slots: list[dict[str, Any]],
        equipment_slots: list[dict[str, Any]],
    ) -> str:
        message = self._workflow.save_classification_slots(labor_slots, equipment_slots)
        self.state_changed.emit()
        return message

    def save_rates(
        self,
        labor_rows: list[dict[str, str]],
        equipment_rows: list[dict[str, str]],
    ) -> str:
        message = self._workflow.save_rates(labor_rows, equipment_rows)
        self.state_changed.emit()
        return message
