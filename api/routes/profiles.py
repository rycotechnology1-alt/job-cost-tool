"""Trusted-profile authoring routes for the Phase 2A backend slice."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.request_context import get_request_context
from api.schemas.profile_authoring import (
    ClassificationsPatchRequest,
    CreateTrustedProfileRequest,
    DraftSaveRequest,
    DefaultOmitPatchRequest,
    DraftEditorStateResponse,
    EquipmentMappingsPatchRequest,
    ExportSettingsPatchRequest,
    LaborMappingsPatchRequest,
    PublishDraftRequest,
    PublishedProfileDetailResponse,
    RatesPatchRequest,
)
from api.serializers import (
    to_draft_editor_state_response,
    to_published_profile_detail_response,
)
from services.request_context import RequestContext


profiles_router = APIRouter(prefix="/api/profiles", tags=["profiles"])
profile_drafts_router = APIRouter(prefix="/api/profile-drafts", tags=["profile-drafts"])


@profiles_router.post("", response_model=PublishedProfileDetailResponse, status_code=status.HTTP_201_CREATED)
def create_trusted_profile(
    request: CreateTrustedProfileRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> PublishedProfileDetailResponse:
    """Create one new trusted profile seeded from an existing published profile."""
    try:
        detail = runtime.profile_authoring_service.create_trusted_profile(
            profile_name=request.profile_name,
            display_name=request.display_name,
            description=request.description,
            seed_trusted_profile_id=request.seed_trusted_profile_id,
            request_context=request_context,
        )
        return to_published_profile_detail_response(detail)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profiles_router.get("/{trusted_profile_id}", response_model=PublishedProfileDetailResponse)
def get_profile_detail(
    trusted_profile_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> PublishedProfileDetailResponse:
    """Return read-only published profile detail for one logical trusted profile."""
    try:
        detail = runtime.profile_authoring_service.get_profile_detail(
            trusted_profile_id,
            request_context=request_context,
        )
        return to_published_profile_detail_response(detail)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profiles_router.post("/{trusted_profile_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_trusted_profile(
    trusted_profile_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> Response:
    """Archive one user-created trusted profile without deleting published lineage."""
    try:
        runtime.profile_authoring_service.archive_trusted_profile(
            trusted_profile_id,
            request_context=request_context,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profiles_router.post("/{trusted_profile_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
def unarchive_trusted_profile(
    trusted_profile_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> Response:
    """Restore one archived user-created trusted profile to the active settings lists."""
    try:
        runtime.profile_authoring_service.unarchive_trusted_profile(
            trusted_profile_id,
            request_context=request_context,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profiles_router.post(
    "/{trusted_profile_id}/draft",
    response_model=DraftEditorStateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_or_open_profile_draft(
    trusted_profile_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Create or return the single mutable draft for one logical trusted profile."""
    try:
        state = runtime.profile_authoring_service.create_or_open_draft(
            trusted_profile_id,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.get("/{trusted_profile_draft_id}", response_model=DraftEditorStateResponse)
def get_profile_draft(
    trusted_profile_draft_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Return full editor state for one trusted-profile draft."""
    try:
        state = runtime.profile_authoring_service.get_draft_state(
            trusted_profile_draft_id,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.delete("/{trusted_profile_draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_profile_draft(
    trusted_profile_draft_id: str,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> Response:
    """Discard one trusted-profile draft without changing published lineage."""
    try:
        runtime.profile_authoring_service.discard_draft(
            trusted_profile_draft_id,
            request_context=request_context,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch("/{trusted_profile_draft_id}", response_model=DraftEditorStateResponse)
def patch_profile_draft(
    trusted_profile_draft_id: str,
    request: DraftSaveRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Atomically replace the editable draft state."""
    try:
        state = runtime.profile_authoring_service.save_draft_state(
            trusted_profile_draft_id,
            default_omit_rules=[row.model_dump() for row in request.default_omit_rules],
            labor_mapping_rows=[row.model_dump() for row in request.labor_mappings],
            equipment_mapping_rows=[row.model_dump() for row in request.equipment_mappings],
            labor_slots=[row.model_dump() for row in request.labor_slots],
            equipment_slots=[row.model_dump() for row in request.equipment_slots],
            labor_rate_rows=[row.model_dump() for row in request.labor_rates],
            equipment_rate_rows=[row.model_dump() for row in request.equipment_rates],
            export_settings=request.export_settings.model_dump(),
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch("/{trusted_profile_draft_id}/default-omit", response_model=DraftEditorStateResponse)
def patch_default_omit(
    trusted_profile_draft_id: str,
    request: DefaultOmitPatchRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Replace draft default-omit rules."""
    try:
        state = runtime.profile_authoring_service.update_default_omit_rules(
            trusted_profile_draft_id,
            [row.model_dump() for row in request.default_omit_rules],
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch("/{trusted_profile_draft_id}/labor-mappings", response_model=DraftEditorStateResponse)
def patch_labor_mappings(
    trusted_profile_draft_id: str,
    request: LaborMappingsPatchRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Replace draft labor mappings."""
    try:
        state = runtime.profile_authoring_service.update_labor_mappings(
            trusted_profile_draft_id,
            [row.model_dump() for row in request.labor_mappings],
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch(
    "/{trusted_profile_draft_id}/equipment-mappings",
    response_model=DraftEditorStateResponse,
)
def patch_equipment_mappings(
    trusted_profile_draft_id: str,
    request: EquipmentMappingsPatchRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Replace draft equipment mappings."""
    try:
        state = runtime.profile_authoring_service.update_equipment_mappings(
            trusted_profile_draft_id,
            [row.model_dump() for row in request.equipment_mappings],
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch("/{trusted_profile_draft_id}/classifications", response_model=DraftEditorStateResponse)
def patch_classifications(
    trusted_profile_draft_id: str,
    request: ClassificationsPatchRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Replace draft labor/equipment slot rows."""
    try:
        state = runtime.profile_authoring_service.update_classifications(
            trusted_profile_draft_id,
            labor_slots=[row.model_dump() for row in request.labor_slots],
            equipment_slots=[row.model_dump() for row in request.equipment_slots],
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch("/{trusted_profile_draft_id}/rates", response_model=DraftEditorStateResponse)
def patch_rates(
    trusted_profile_draft_id: str,
    request: RatesPatchRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Replace draft labor/equipment rates."""
    try:
        state = runtime.profile_authoring_service.update_rates(
            trusted_profile_draft_id,
            labor_rows=[row.model_dump() for row in request.labor_rates],
            equipment_rows=[row.model_dump() for row in request.equipment_rates],
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.patch("/{trusted_profile_draft_id}/export-settings", response_model=DraftEditorStateResponse)
def patch_export_settings(
    trusted_profile_draft_id: str,
    request: ExportSettingsPatchRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> DraftEditorStateResponse:
    """Replace draft export-only settings."""
    try:
        state = runtime.profile_authoring_service.update_export_settings(
            trusted_profile_draft_id,
            request.export_settings.model_dump(),
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_draft_editor_state_response(state)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


@profile_drafts_router.post(
    "/{trusted_profile_draft_id}/publish",
    response_model=PublishedProfileDetailResponse,
)
def publish_profile_draft(
    trusted_profile_draft_id: str,
    request: PublishDraftRequest,
    runtime: ApiRuntime = Depends(get_runtime),
    request_context: RequestContext = Depends(get_request_context),
) -> PublishedProfileDetailResponse:
    """Validate and publish one trusted-profile draft."""
    try:
        detail = runtime.profile_authoring_service.publish_draft(
            trusted_profile_draft_id,
            expected_draft_revision=request.expected_draft_revision,
            request_context=request_context,
        )
        return to_published_profile_detail_response(detail)
    except Exception as exc:  # pragma: no cover - exercised via API tests
        raise to_http_exception(exc) from exc


