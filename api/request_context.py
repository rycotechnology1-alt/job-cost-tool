"""FastAPI request-context dependency helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from api.settings import ApiSettings
from services.request_context import LOCAL_REQUEST_CONTEXT, RequestContext
from services.hosted_request_context_service import (
    AuthenticatedRequestClaims,
    HostedRequestContextService,
)


RequestContextProvider = Callable[[Request], RequestContext]


def build_request_context_provider(
    settings: ApiSettings,
    *,
    hosted_request_context_service: HostedRequestContextService,
) -> RequestContextProvider:
    """Build the configured request-context provider for the current app mode."""
    if settings.auth_mode == "bearer":
        if not settings.auth_secret:
            raise ValueError("JOB_COST_API_AUTH_SECRET is required when JOB_COST_API_AUTH_MODE=bearer.")
        return BearerRequestContextProvider(
            auth_secret=settings.auth_secret,
            hosted_request_context_service=hosted_request_context_service,
        )
    return lambda request: LOCAL_REQUEST_CONTEXT


def get_request_context(request: Request) -> RequestContext:
    """Return the current request context, defaulting to the local dev context."""
    provider = getattr(request.app.state, "request_context_provider", None)
    if callable(provider):
        return provider(request)
    return LOCAL_REQUEST_CONTEXT


class BearerRequestContextProvider:
    """Resolve authenticated hosted request context from a signed bearer token."""

    def __init__(
        self,
        *,
        auth_secret: str,
        hosted_request_context_service: HostedRequestContextService,
    ) -> None:
        self._auth_secret = auth_secret.encode("utf-8")
        self._hosted_request_context_service = hosted_request_context_service

    def __call__(self, request: Request) -> RequestContext:
        authorization_header = str(request.headers.get("Authorization") or "").strip()
        if not authorization_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication is required for hosted API requests.",
            )
        scheme, _, token = authorization_header.partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization must use a bearer token.",
            )
        claims = self._parse_token(token.strip())
        return self._hosted_request_context_service.resolve_request_context(claims)

    def _parse_token(self, token: str) -> AuthenticatedRequestClaims:
        try:
            version, encoded_payload, encoded_signature = token.split(".", 2)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token format is invalid.",
            ) from exc
        if version != "jobcostv1":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token version is not supported.",
            )
        expected_signature = hmac.new(
            self._auth_secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied_signature = _decode_base64url(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token signature is invalid.",
            )
        try:
            payload = json.loads(_decode_base64url(encoded_payload).decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token payload is invalid.",
            ) from exc
        required_claims = {
            "sub",
            "user_id",
            "email",
            "display_name",
            "organization_id",
            "organization_slug",
            "organization_name",
            "role",
        }
        missing_claims = sorted(
            claim_name for claim_name in required_claims if not str(payload.get(claim_name) or "").strip()
        )
        if missing_claims:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Bearer token is missing required claims: {', '.join(missing_claims)}.",
            )
        return AuthenticatedRequestClaims(
            auth_subject=str(payload["sub"]).strip(),
            user_id=str(payload["user_id"]).strip(),
            email=str(payload["email"]).strip(),
            display_name=str(payload["display_name"]).strip(),
            organization_id=str(payload["organization_id"]).strip(),
            organization_slug=str(payload["organization_slug"]).strip(),
            organization_name=str(payload["organization_name"]).strip(),
            role=str(payload["role"]).strip(),
        )


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
