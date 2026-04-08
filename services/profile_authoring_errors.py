"""Narrow profile-authoring exceptions for stable API error mapping."""

from __future__ import annotations


class ProfileAuthoringConflictError(ValueError):
    """Raised when a trusted-profile authoring request conflicts with existing persisted state."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "profile_authoring_conflict",
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.field_errors = {
            key: list(messages)
            for key, messages in (field_errors or {}).items()
            if list(messages)
        }

    def to_api_detail(self) -> dict[str, object]:
        """Return the stable API-safe error detail payload."""
        return {
            "message": str(self),
            "error_code": self.error_code,
            "field_errors": self.field_errors,
        }
