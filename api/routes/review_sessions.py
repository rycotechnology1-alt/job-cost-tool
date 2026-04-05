"""Review-session and append-only edit routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.schemas.review_sessions import AppendReviewEditsRequest, ReviewSessionResponse
from api.serializers import to_review_session_response
from core.models import PendingRecordEdit


router = APIRouter(prefix="/api/runs/{processing_run_id}/review-session", tags=["review-sessions"])


@router.get("", response_model=ReviewSessionResponse)
def get_review_session(
    processing_run_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
) -> ReviewSessionResponse:
    """Open or fetch the phase-1 review session for one immutable processing run."""
    try:
        state = runtime.review_session_service.open_review_session(processing_run_id)
        return to_review_session_response(state)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.post("/edits", response_model=ReviewSessionResponse)
def append_review_edits(
    processing_run_id: str,
    request: AppendReviewEditsRequest,
    runtime: ApiRuntime = Depends(get_runtime),
) -> ReviewSessionResponse:
    """Append one accepted review-edit batch by run-scoped record key."""
    try:
        state = runtime.review_session_service.apply_review_edits(
            processing_run_id,
            [
                PendingRecordEdit(
                    record_key=edit.record_key,
                    changed_fields=edit.changed_fields.model_dump(exclude_unset=True),
                )
                for edit in request.edits
            ],
        )
        return to_review_session_response(state)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc
