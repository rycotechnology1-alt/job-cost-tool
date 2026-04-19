"""Small helpers for resolving config-related project paths."""

from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """Return the root directory of the package."""
    return Path(__file__).resolve().parents[2]


def get_profiles_root() -> Path:
    """Return the directory containing profile bundles."""
    return get_project_root() / "profiles"


def get_legacy_config_root() -> Path:
    """Return the legacy shared config directory used before profiles."""
    return get_project_root() / "config"
