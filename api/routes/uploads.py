"""Upload routes for source documents."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.schemas.uploads import BlobUploadRegistrationRequest, SourceUploadResponse
from api.serializers import to_upload_response


router = APIRouter(prefix="/api/source-documents", tags=["source-documents"])


@router.post("/uploads", response_model=SourceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_source_document(
    file: UploadFile = File(...),
    runtime: ApiRuntime = Depends(get_runtime),
) -> SourceUploadResponse:
    """Persist one uploaded source document for later processing-run creation."""
    original_filename = Path(str(file.filename or "").strip()).name
    if not original_filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must include a filename.")

    try:
        upload = runtime.file_store.save_upload(
            original_filename=original_filename,
            content_bytes=await file.read(),
            content_type=file.content_type,
        )
        return to_upload_response(upload)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc


@router.post("/blob-uploads", response_model=SourceUploadResponse, status_code=status.HTTP_201_CREATED)
def register_blob_upload(
    request: BlobUploadRegistrationRequest,
    runtime: ApiRuntime = Depends(get_runtime),
) -> SourceUploadResponse:
    """Register one PDF that the browser uploaded directly to blob storage."""
    try:
        upload = runtime.file_store.register_blob_upload(
            storage_ref=request.storage_ref,
            original_filename=request.original_filename,
            content_type=request.content_type,
            file_size_bytes=request.file_size_bytes,
        )
        return to_upload_response(upload)
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc
