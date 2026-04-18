"""Request-scoped context seam for web/API workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Stable request metadata used to scope web/API service calls."""

    organization_id: str
    user_id: str
    role: str


LOCAL_REQUEST_CONTEXT = RequestContext(
    organization_id="org-default",
    user_id="dev-local-user",
    role="developer",
)


def resolve_request_context(request_context: RequestContext | None) -> RequestContext:
    """Return the provided request context or the local-development default."""
    return request_context or LOCAL_REQUEST_CONTEXT


def is_local_request_context(request_context: RequestContext | None) -> bool:
    """Return whether the current request context is the local-development fallback."""
    return request_context is None or request_context is LOCAL_REQUEST_CONTEXT
