"""Profile discovery and metadata helpers for config bundles."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.config.path_utils import get_legacy_config_root, get_profiles_root

_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ProfileManager:
    """Discover available profiles and expose profile metadata."""

    def __init__(
        self,
        profiles_root: Path | None = None,
        legacy_config_root: Path | None = None,
    ) -> None:
        self._profiles_root = (profiles_root or get_profiles_root()).resolve()
        self._legacy_config_root = (legacy_config_root or get_legacy_config_root()).resolve()

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return discovered profile metadata for all available profiles."""
        profiles: list[dict[str, Any]] = []
        if not self._profiles_root.is_dir():
            return profiles

        for profile_dir in sorted(path for path in self._profiles_root.iterdir() if path.is_dir()):
            profile_file = profile_dir / "profile.json"
            if not profile_file.is_file():
                continue
            metadata = self._load_profile_metadata(profile_dir)
            metadata["profile_dir"] = str(profile_dir.resolve())
            profiles.append(metadata)
        return profiles

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
        return metadata

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
