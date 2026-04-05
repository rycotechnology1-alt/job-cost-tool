"""Processing-run routes for the minimal phase-1 API slice."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.schemas.runs import (
    ProcessingRunCreateRequest,
    ProcessingRunDetailResponse,
    ProcessingRunResponse,
)
from api.serializers import to_processing_run_detail_response, to_processing_run_response


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=ProcessingRunResponse, status_code=status.HTTP_201_CREATED)
def create_processing_run(
    request: ProcessingRunCreateRequest,
    runtime: ApiRuntime = Depends(get_runtime),
) -> ProcessingRunResponse:
    """Start one immutable processing run from a previously uploaded source document."""
    try:
        upload = runtime.file_store.get_upload(request.upload_id)
        result = runtime.processing_run_service.create_processing_run(
            upload.file_path,
            profile_name=request.trusted_profile_name,
            storage_ref=upload.storage_ref,
        )
        return to_processing_run_response(result)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.get("/{processing_run_id}", response_model=ProcessingRunDetailResponse)
def get_processing_run(
    processing_run_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
) -> ProcessingRunDetailResponse:
    """Fetch one immutable processing run plus its ordered run records and blockers."""
    try:
        state = runtime.processing_run_service.get_processing_run_state(processing_run_id)
        return to_processing_run_detail_response(state)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc
