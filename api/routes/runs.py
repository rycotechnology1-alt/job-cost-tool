"""Processing-run routes for the minimal phase-1 API slice."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.request_context import get_request_context
from api.schemas.runs import (
    ProcessingRunCreateRequest,
    ProcessingRunDetailResponse,
    ProcessingRunReopenRequest,
    ProcessingRunResponse,
)
from api.schemas.review_sessions import ReviewSessionResponse
from api.serializers import (
    to_processing_run_detail_response,
    to_processing_run_response,
    to_processing_run_summary_response,
    to_review_session_response,
)
from services.request_context import RequestContext


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[ProcessingRunResponse])
def list_processing_runs(
    state: Literal["open", "archived"] = Query(default="open"),
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> list[ProcessingRunResponse]:
    """List stored processing runs for the run-library workspace."""
    try:
        summaries = runtime.processing_run_service.list_processing_runs(
            archived=state == "archived",
            request_context=request_context,
        )
        return [to_processing_run_summary_response(summary) for summary in summaries]
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.post("", response_model=ProcessingRunResponse, status_code=status.HTTP_201_CREATED)
def create_processing_run(
    request: ProcessingRunCreateRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> ProcessingRunResponse:
    """Start one immutable processing run from a previously uploaded source document."""
    try:
        upload = runtime.file_store.get_upload(request.upload_id)
        result = runtime.processing_run_service.create_processing_run(
            upload.file_path,
            profile_name=request.trusted_profile_name,
            storage_ref=upload.storage_ref,
            request_context=request_context,
        )
        return to_processing_run_response(result)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.get("/{processing_run_id}", response_model=ProcessingRunDetailResponse)
def get_processing_run(
    processing_run_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> ProcessingRunDetailResponse:
    """Fetch one immutable processing run plus its ordered run records and blockers."""
    try:
        state = runtime.processing_run_service.get_processing_run_state(
            processing_run_id,
            request_context=request_context,
        )
        return to_processing_run_detail_response(state)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.post("/{processing_run_id}/archive", response_model=ProcessingRunResponse)
def archive_processing_run(
    processing_run_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> ProcessingRunResponse:
    """Archive one stored run and detach it from live trusted-profile drift checks."""
    try:
        state = runtime.processing_run_service.archive_processing_run(
            processing_run_id,
            request_context=request_context,
        )
        return to_processing_run_detail_response(state)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.post("/{processing_run_id}/reopen", response_model=ReviewSessionResponse)
def reopen_processing_run(
    processing_run_id: str,
    request: ProcessingRunReopenRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> ReviewSessionResponse:
    """Load one stored run in latest-reviewed mode or original-processed mode."""
    try:
        state = runtime.review_session_service.reopen_review_session(
            processing_run_id,
            mode=request.mode,
            continue_from_original=request.continue_from_original,
            expected_current_revision=request.expected_current_revision,
            request_context=request_context,
        )
        return to_review_session_response(state)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc
