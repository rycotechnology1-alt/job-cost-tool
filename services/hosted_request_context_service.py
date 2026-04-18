"""Hosted request-context provisioning for authenticated web/API requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from core.models.lineage import User
from infrastructure.persistence import LineageStore
from services.request_context import RequestContext
from services.trusted_profile_provisioning_service import TrustedProfileProvisioningService


@dataclass(frozen=True, slots=True)
class AuthenticatedRequestClaims:
    """Minimal authenticated identity claims required for hosted API access."""

    auth_subject: str
    user_id: str
    email: str
    display_name: str
    organization_id: str
    organization_slug: str
    organization_name: str
    role: str


class HostedRequestContextService:
    """Ensure authenticated org/user state exists before hosted services run."""

    def __init__(
        self,
        *,
        lineage_store: LineageStore,
        trusted_profile_provisioning_service: TrustedProfileProvisioningService,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._trusted_profile_provisioning_service = trusted_profile_provisioning_service
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def resolve_request_context(self, claims: AuthenticatedRequestClaims) -> RequestContext:
        """Provision the authenticated organization/user and return the hosted request context."""
        created_at = self._now_provider()
        organization = self._lineage_store.ensure_organization(
            organization_id=claims.organization_id,
            slug=claims.organization_slug,
            display_name=claims.organization_name,
            created_at=created_at,
            is_seeded=False,
        )
        user = self._lineage_store.ensure_user(
            User(
                user_id=claims.user_id,
                organization_id=organization.organization_id,
                email=claims.email,
                display_name=claims.display_name,
                auth_subject=claims.auth_subject,
                created_at=created_at,
            )
        )
        self._trusted_profile_provisioning_service.ensure_organization_default_profile(
            organization_id=organization.organization_id,
            created_by_user_id=user.user_id,
        )
        return RequestContext(
            organization_id=organization.organization_id,
            user_id=user.user_id,
            role=claims.role,
        )
