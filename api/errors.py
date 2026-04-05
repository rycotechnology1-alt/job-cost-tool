"""Service-to-HTTP error mapping for the narrow phase-1 API slice."""

from __future__ import annotations

from fastapi import HTTPException, status

from services.review_session_service import HistoricalExportUnavailableError


def to_http_exception(exc: Exception) -> HTTPException:
    """Map a known service/storage exception to an API-appropriate HTTP error."""
    if isinstance(exc, HistoricalExportUnavailableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_clean_message(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_clean_message(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_clean_message(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_clean_message(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected server error occurred.",
    )


def _clean_message(exc: Exception) -> str:
    """Normalize Python exception text into stable API error details."""
    return str(exc).strip().strip("'")
