from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class FakeBlobObject:
    pathname: str
    content_bytes: bytes
    content_type: str
    uploaded_at: datetime


class FakeBlobObjectClient:
    """Shared in-memory blob client for multi-instance runtime storage tests."""

    def __init__(self) -> None:
        self._objects: dict[str, FakeBlobObject] = {}

    def put_bytes(
        self,
        *,
        pathname: str,
        content_bytes: bytes,
        content_type: str,
    ) -> None:
        self._objects[pathname] = FakeBlobObject(
            pathname=pathname,
            content_bytes=bytes(content_bytes),
            content_type=content_type,
            uploaded_at=datetime.now(timezone.utc),
        )

    def get_bytes(self, pathname: str) -> bytes:
        try:
            return self._objects[pathname].content_bytes
        except KeyError as exc:
            raise FileNotFoundError(pathname) from exc

    def delete_path(self, pathname: str) -> None:
        self._objects.pop(pathname, None)

    def list_paths(self, *, prefix: str) -> list[str]:
        return sorted(path for path in self._objects if path.startswith(prefix))

