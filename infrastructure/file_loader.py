"""Filesystem helpers for application inputs."""

from pathlib import Path


def load_file(file_path: str) -> Path:
    """Return a resolved path for a user-selected input file.

    Args:
        file_path: Raw file path provided by the caller.

    Returns:
        A resolved Path instance for downstream processing.
    """
    return Path(file_path).expanduser().resolve()
