"""Exact-revision export routes for the minimal phase-1 API slice."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.schemas.exports import ExportArtifactResponse, ExportCreateRequest
from api.serializers import to_export_artifact_response


router = APIRouter(tags=["exports"])


@router.post(
    "/api/runs/{processing_run_id}/exports",
    response_model=ExportArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_export_artifact(
    processing_run_id: str,
    request: ExportCreateRequest,
    runtime: ApiRuntime = Depends(get_runtime),
) -> ExportArtifactResponse:
    """Generate one export artifact from one exact review-session revision."""
    try:
        result = runtime.review_session_service.export_session_revision(
            processing_run_id,
            session_revision=request.session_revision,
        )
        return to_export_artifact_response(result)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.get("/api/exports/{export_artifact_id}/download")
def download_export_artifact(
    export_artifact_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
) -> FileResponse:
    """Download one persisted export artifact."""
    try:
        artifact_payload = runtime.review_session_service.resolve_export_artifact_payload(export_artifact_id)
        return FileResponse(
            path=artifact_payload.file_path,
            filename=artifact_payload.original_filename,
            media_type=artifact_payload.content_type,
        )
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc
