"""Profile discovery and active-profile management for config bundles."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from core.config.path_utils import get_app_settings_path, get_legacy_config_root, get_profiles_root

_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DEFAULT_APP_SETTINGS = {"active_profile": "default", "default_profile_unlocked": False}


class ProfileManager:
    """Discover available profiles and manage the active profile setting."""

    def __init__(
        self,
        profiles_root: Path | None = None,
        settings_path: Path | None = None,
        legacy_config_root: Path | None = None,
    ) -> None:
        self._profiles_root = (profiles_root or get_profiles_root()).resolve()
        self._settings_path = (settings_path or get_app_settings_path()).resolve()
        self._legacy_config_root = (legacy_config_root or get_legacy_config_root()).resolve()

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return discovered profile metadata for all available profiles."""
        profiles: list[dict[str, Any]] = []
        active_profile_name = self.get_active_profile_name()
        if not self._profiles_root.is_dir():
            return profiles

        for profile_dir in sorted(path for path in self._profiles_root.iterdir() if path.is_dir()):
            profile_file = profile_dir / "profile.json"
            if not profile_file.is_file():
                continue
            metadata = self._load_profile_metadata(profile_dir)
            metadata["profile_dir"] = str(profile_dir)
            metadata["is_active_profile"] = metadata.get("profile_name") == active_profile_name
            profiles.append(metadata)
        return profiles

    def get_active_profile_name(self) -> str:
        """Return the active profile name from settings, defaulting to 'default'."""
        settings = self._load_app_settings()
        active_profile = str(settings.get("active_profile", "default")).strip()
        return active_profile or "default"

    def is_default_profile_unlocked(self) -> bool:
        """Return whether the built-in default profile is unlocked for editing."""
        settings = self._load_app_settings()
        return bool(settings.get("default_profile_unlocked", False))

    def set_default_profile_unlocked(self, unlocked: bool) -> None:
        """Persist the edit-lock state for the built-in default profile."""
        settings = self._load_app_settings()
        settings["default_profile_unlocked"] = bool(unlocked)
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def get_active_profile_dir(self) -> Path:
        """Return the directory of the active profile, falling back to legacy config when needed."""
        active_name = self.get_active_profile_name()
        profile_dir = self.get_profile_dir(active_name)
        if profile_dir is not None:
            return profile_dir

        default_dir = self.get_profile_dir("default")
        if default_dir is not None:
            return default_dir

        if self._legacy_config_root.is_dir():
            return self._legacy_config_root

        raise FileNotFoundError(
            f"Active profile '{active_name}' was not found under '{self._profiles_root}', and no legacy config directory is available."
        )

    def get_profile_dir(self, profile_name: str) -> Path | None:
        """Return the directory for a specific profile when it exists."""
        normalized_name = str(profile_name).strip()
        if not normalized_name:
            return None
        profile_dir = self._profiles_root / normalized_name
        profile_file = profile_dir / "profile.json"
        if profile_dir.is_dir() and profile_file.is_file():
            return profile_dir.resolve()
        return None

    def get_profile_metadata(self, profile_name: str) -> dict[str, Any]:
        """Return metadata for a specific profile."""
        profile_dir = self.get_profile_dir(profile_name)
        if profile_dir is None:
            raise FileNotFoundError(
                f"Profile '{profile_name}' was not found under '{self._profiles_root}'."
            )
        metadata = self._load_profile_metadata(profile_dir)
        metadata["profile_dir"] = str(profile_dir)
        metadata["is_active_profile"] = metadata.get("profile_name") == self.get_active_profile_name()
        return metadata

    def get_active_profile_metadata(self) -> dict[str, Any]:
        """Return metadata for the active profile or a legacy fallback."""
        profile_dir = self.get_active_profile_dir()
        profile_file = profile_dir / "profile.json"
        if profile_file.is_file():
            metadata = self._load_profile_metadata(profile_dir)
            metadata["profile_dir"] = str(profile_dir)
            metadata["is_active_profile"] = True
            return metadata
        return {
            "profile_name": "default",
            "display_name": "Legacy Default Profile",
            "description": "Fallback legacy configuration bundle.",
            "version": "1.0",
            "template_filename": None,
            "is_active": True,
            "profile_dir": str(profile_dir),
            "is_active_profile": True,
        }

    def set_active_profile(self, profile_name: str) -> None:
        """Persist the active profile selection to app settings."""
        profile_dir = self.get_profile_dir(profile_name)
        if profile_dir is None:
            raise FileNotFoundError(
                f"Profile '{profile_name}' was not found under '{self._profiles_root}'."
            )

        settings = self._load_app_settings()
        settings["active_profile"] = profile_name
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def duplicate_profile(
        self,
        source_profile_name: str,
        new_profile_name: str,
        display_name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Duplicate an existing profile bundle into a new profile directory."""
        source_dir = self.get_profile_dir(source_profile_name)
        if source_dir is None:
            raise FileNotFoundError(
                f"Source profile '{source_profile_name}' was not found under '{self._profiles_root}'."
            )

        normalized_profile_name = self._validate_profile_name(new_profile_name)
        normalized_display_name = str(display_name).strip()
        if not normalized_display_name:
            raise ValueError("Display name is required when duplicating a profile.")

        target_dir = self._profiles_root / normalized_profile_name
        if target_dir.exists():
            raise ValueError(f"Profile folder '{normalized_profile_name}' already exists.")

        self._profiles_root.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(source_dir, target_dir)
        except Exception as exc:
            raise ValueError(
                f"Failed to duplicate profile '{source_profile_name}' to '{normalized_profile_name}': {exc}"
            ) from exc

        metadata = self._load_profile_metadata(target_dir)
        metadata["profile_name"] = normalized_profile_name
        metadata["display_name"] = normalized_display_name
        metadata["description"] = str(description).strip() or metadata.get("description", "")
        metadata["is_active"] = False
        (target_dir / "profile.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metadata["profile_dir"] = str(target_dir.resolve())
        metadata["is_active_profile"] = False
        return metadata

    def delete_profile(self, profile_name: str) -> None:
        """Delete a non-default, non-active profile directory safely."""
        normalized_name = self._validate_profile_name(profile_name)
        if normalized_name.casefold() == "default":
            raise ValueError("Default profile cannot be deleted.")
        if normalized_name == self.get_active_profile_name():
            raise ValueError("Switch to another profile before deleting this one.")

        profile_dir = self.get_profile_dir(normalized_name)
        if profile_dir is None:
            raise FileNotFoundError(
                f"Profile '{normalized_name}' was not found under '{self._profiles_root}'."
            )

        try:
            profile_dir.relative_to(self._profiles_root)
        except ValueError as exc:
            raise ValueError("Profile deletion target is outside the profiles directory.") from exc

        try:
            shutil.rmtree(profile_dir)
        except Exception as exc:
            raise ValueError(f"Failed to delete profile '{normalized_name}': {exc}") from exc

    def validate_profile_name(self, profile_name: str) -> str:
        """Validate and normalize a filesystem-safe profile name."""
        return self._validate_profile_name(profile_name)

    def _validate_profile_name(self, profile_name: str) -> str:
        """Return a safe normalized profile directory name or raise ValueError."""
        normalized_name = str(profile_name).strip()
        if not normalized_name:
            raise ValueError("Profile name is required.")
        if not _PROFILE_NAME_RE.fullmatch(normalized_name):
            raise ValueError(
                "Profile name may only contain letters, numbers, underscores, and hyphens."
            )
        return normalized_name

    def _load_app_settings(self) -> dict[str, Any]:
        """Load the app settings file when present."""
        if not self._settings_path.is_file():
            return dict(_DEFAULT_APP_SETTINGS)

        try:
            with self._settings_path.open("r", encoding="utf-8-sig") as settings_file:
                loaded_settings = json.load(settings_file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"App settings file '{self._settings_path}' contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(loaded_settings, dict):
            raise ValueError(
                f"App settings file '{self._settings_path}' must contain a JSON object at the top level"
            )
        normalized_settings = dict(_DEFAULT_APP_SETTINGS)
        normalized_settings.update(loaded_settings)
        return normalized_settings

    def _load_profile_metadata(self, profile_dir: Path) -> dict[str, Any]:
        """Load and validate a profile metadata file."""
        profile_file = profile_dir / "profile.json"
        try:
            with profile_file.open("r", encoding="utf-8-sig") as metadata_file:
                loaded_metadata = json.load(metadata_file)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Profile metadata file '{profile_file}' contains invalid JSON: {exc.msg}"
            ) from exc

        if not isinstance(loaded_metadata, dict):
            raise ValueError(
                f"Profile metadata file '{profile_file}' must contain a JSON object at the top level"
            )

        required_keys = ("profile_name", "display_name", "description", "version", "template_filename")
        for key in required_keys:
            if key not in loaded_metadata:
                raise ValueError(
                    f"Profile metadata file '{profile_file}' is missing required top-level key '{key}'"
                )
        return loaded_metadata
