"""Helpers for slot-backed profile classifications with template-bound active capacity."""

from __future__ import annotations

from typing import Any

SlotDict = dict[str, Any]


def normalize_slot_config(
    raw_config: dict[str, Any],
    *,
    slot_prefix: str,
    capacity: int,
    template_labels: list[str],
) -> dict[str, Any]:
    """Normalize old or new classification config into a slot-based structure."""
    normalized_template_labels = [str(label).strip() for label in template_labels if str(label).strip()]
    normalized_capacity = capacity if capacity > 0 else len(normalized_template_labels)

    if "slots" in raw_config:
        if not isinstance(raw_config["slots"], list):
            raise ValueError("Classification slot config must define 'slots' as an array.")
        if normalized_capacity <= 0:
            normalized_capacity = len(raw_config["slots"])
        slots = _normalize_existing_slots(raw_config["slots"], slot_prefix=slot_prefix, capacity=normalized_capacity)
    elif "classifications" in raw_config:
        if not isinstance(raw_config["classifications"], list):
            raise ValueError("Classification config must define 'classifications' as an array.")
        cleaned_labels = [str(item).strip() for item in raw_config["classifications"] if str(item).strip()]
        if normalized_capacity <= 0:
            normalized_capacity = len(cleaned_labels)
        slots = _migrate_labels_to_slots(
            cleaned_labels,
            slot_prefix=slot_prefix,
            capacity=normalized_capacity,
            template_labels=normalized_template_labels,
        )
    else:
        raise ValueError("Classification config must define either 'slots' or 'classifications'.")

    active_labels = [slot["label"] for slot in slots if slot.get("active") and str(slot.get("label", "")).strip()]
    return {
        "slots": slots,
        "classifications": active_labels,
        "capacity": normalized_capacity,
    }


def build_slot_config_from_rows(slot_rows: list[SlotDict]) -> dict[str, Any]:
    """Build a saved slot config from explicit slot rows."""
    slots: list[SlotDict] = []
    for index, row in enumerate(slot_rows):
        slot_id = str(row.get("slot_id") or f"slot_{index + 1}").strip() or f"slot_{index + 1}"
        active = bool(row.get("active"))
        label = str(row.get("label", "")).strip()
        slots.append(
            {
                "slot_id": slot_id,
                "label": label,
                "active": active,
            }
        )
    return {"slots": slots}


def get_active_slots(slot_config: dict[str, Any], *, slot_prefix: str) -> list[SlotDict]:
    """Return active slots from either slot-based or legacy list-based config."""
    if "slots" in slot_config and isinstance(slot_config.get("slots"), list):
        slots = slot_config.get("slots", [])
        active_slots: list[SlotDict] = []
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                continue
            label = str(slot.get("label", "")).strip()
            if not slot.get("active") or not label:
                continue
            slot_id = str(slot.get("slot_id") or f"{slot_prefix}_{index + 1}").strip() or f"{slot_prefix}_{index + 1}"
            active_slots.append({"slot_id": slot_id, "label": label, "active": True})
        return active_slots

    classifications = slot_config.get("classifications", []) if isinstance(slot_config.get("classifications"), list) else []
    return [
        {"slot_id": f"{slot_prefix}_{index + 1}", "label": str(label).strip(), "active": True}
        for index, label in enumerate(classifications)
        if str(label).strip()
    ]


def build_slot_lookup(active_slots: list[SlotDict]) -> dict[str, SlotDict]:
    """Build a case-insensitive label lookup for active slots."""
    lookup: dict[str, SlotDict] = {}
    for slot in active_slots:
        label = str(slot.get("label", "")).strip()
        if not label:
            continue
        lookup[label.casefold()] = dict(slot)
    return lookup


def _normalize_existing_slots(raw_slots: list[Any], *, slot_prefix: str, capacity: int) -> list[SlotDict]:
    """Normalize a slot array while preserving inactive stored classifications."""
    slots: list[SlotDict] = []
    for index in range(max(capacity, len(raw_slots), 0)):
        raw_slot = raw_slots[index] if index < len(raw_slots) and isinstance(raw_slots[index], dict) else {}
        label = str(raw_slot.get("label", "")).strip()
        active = bool(raw_slot.get("active")) and bool(label)
        slot_id = str(raw_slot.get("slot_id") or f"{slot_prefix}_{index + 1}").strip() or f"{slot_prefix}_{index + 1}"
        slots.append(
            {
                "slot_id": slot_id,
                "label": label,
                "active": active,
            }
        )
    return slots


def _migrate_labels_to_slots(
    labels: list[str],
    *,
    slot_prefix: str,
    capacity: int,
    template_labels: list[str],
) -> list[SlotDict]:
    """Migrate the old freeform list format into slot rows with inactive overflow preserved."""
    active_labels = _resolve_migrated_active_labels(labels, capacity=capacity, template_labels=template_labels)
    inactive_labels = _resolve_inactive_overflow_labels(labels, active_labels)
    slots: list[SlotDict] = []
    for index in range(max(capacity, len(labels), 0)):
        if index < len(active_labels):
            label = active_labels[index]
            active = bool(label)
        else:
            inactive_index = index - len(active_labels)
            label = inactive_labels[inactive_index] if inactive_index < len(inactive_labels) else ""
            active = False
        slots.append(
            {
                "slot_id": f"{slot_prefix}_{index + 1}",
                "label": label,
                "active": active,
            }
        )
    return slots


def _resolve_migrated_active_labels(labels: list[str], *, capacity: int, template_labels: list[str]) -> list[str]:
    """Resolve the active labels to retain during old-config migration."""
    if capacity <= 0:
        return labels
    if len(labels) <= capacity:
        return labels

    if template_labels:
        matched_labels = [label for label in template_labels if label in labels]
        if len(matched_labels) == capacity:
            return matched_labels

    return labels[:capacity]


def _resolve_inactive_overflow_labels(labels: list[str], active_labels: list[str]) -> list[str]:
    """Return legacy labels that should remain stored but inactive after migration."""
    remaining_labels = list(labels)
    for active_label in active_labels:
        if active_label in remaining_labels:
            remaining_labels.remove(active_label)
    return remaining_labels
