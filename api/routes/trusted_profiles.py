"""Read-only trusted-profile routes for the phase-1 browser workflow."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import ApiRuntime, get_runtime
from api.errors import to_http_exception
from api.schemas.trusted_profiles import TrustedProfileResponse
from api.serializers import to_trusted_profile_response


router = APIRouter(prefix="/api/trusted-profiles", tags=["trusted-profiles"])


@router.get("", response_model=list[TrustedProfileResponse])
def list_trusted_profiles(
    runtime: ApiRuntime = Depends(get_runtime),
) -> list[TrustedProfileResponse]:
    """Return the available trusted profiles for the current phase-1 deployment."""
    try:
        return [
            to_trusted_profile_response(profile)
            for profile in runtime.trusted_profile_service.list_trusted_profiles()
        ]
    except Exception as exc:  # pragma: no cover - exercised through API tests
        raise to_http_exception(exc) from exc
