"""Bootstrap/provisioning service for trusted profiles backed by local filesystem bundles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.config import ConfigLoader, ProfileManager
from core.models.lineage import Organization, TemplateArtifact, TrustedProfile, TrustedProfileVersion
from infrastructure.persistence import LineageStore
from services.lineage_service import build_template_artifact
from services.request_context import RequestContext, is_local_request_context, resolve_request_context
from services.trusted_profile_authoring_repository import TrustedProfileAuthoringRepository


@dataclass(frozen=True, slots=True)
class ResolvedTrustedProfile:
    """One request-scoped trusted profile resolved to its current published version."""

    organization: Organization
    trusted_profile: TrustedProfile
    trusted_profile_version: TrustedProfileVersion


class TrustedProfileProvisioningService:
    """Own bootstrap/provisioning policy separate from persistence-facing repositories."""

    def __init__(
        self,
        *,
        lineage_store: LineageStore,
        repository: TrustedProfileAuthoringRepository,
        profile_manager: ProfileManager | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._repository = repository
        self._profile_manager = profile_manager or ProfileManager()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def list_trusted_profiles(
        self,
        *,
        include_archived: bool = False,
        request_context: RequestContext | None = None,
    ) -> list[TrustedProfile]:
        """List persisted trusted profiles after ensuring filesystem-backed bootstrap exists."""
        organization = self._ensure_request_organization(request_context)
        self._ensure_profiles_available(
            organization=organization,
            request_context=request_context,
        )
        return self._repository.list_trusted_profiles(
            organization.organization_id,
            include_archived=include_archived,
        )

    def get_trusted_profile(
        self,
        trusted_profile_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> TrustedProfile:
        """Fetch one trusted profile, bootstrapping filesystem-backed defaults when needed."""
        organization = self._ensure_request_organization(request_context)
        self._ensure_profiles_available(
            organization=organization,
            request_context=request_context,
        )
        try:
            trusted_profile = self._repository.get_trusted_profile(
                organization.organization_id,
                trusted_profile_id,
            )
        except KeyError:
            if self._uses_local_profile_fallback(request_context):
                self.bootstrap_filesystem_profiles(request_context=request_context)
                trusted_profile = self._repository.get_trusted_profile(
                    organization.organization_id,
                    trusted_profile_id,
                )
            else:
                raise
        return trusted_profile

    def get_current_published_version(
        self,
        trusted_profile_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> TrustedProfileVersion:
        """Fetch the current published version, repairing filesystem-backed linkage when needed."""
        trusted_profile = self.get_trusted_profile(
            trusted_profile_id,
            request_context=request_context,
        )
        try:
            return self._repository.get_current_published_version(
                trusted_profile.organization_id,
                trusted_profile.trusted_profile_id,
            )
        except ValueError:
            repaired_version = self._repair_trusted_profile_current_version(trusted_profile)
            if repaired_version is None:
                raise
            return repaired_version

    def resolve_current_published_profile(
        self,
        profile_name: str | None = None,
        *,
        request_context: RequestContext | None = None,
    ) -> ResolvedTrustedProfile:
        """Resolve one selected trusted profile to its current published version."""
        organization = self._ensure_request_organization(request_context)
        self._ensure_profiles_available(
            organization=organization,
            request_context=request_context,
        )
        trusted_profile = self._resolve_selected_trusted_profile(
            organization=organization,
            profile_name=profile_name,
            request_context=request_context,
        )
        if trusted_profile.archived_at is not None:
            raise ValueError(f"Trusted profile '{trusted_profile.display_name}' is archived.")
        trusted_profile_version = self.get_current_published_version(
            trusted_profile.trusted_profile_id,
            request_context=request_context,
        )
        return ResolvedTrustedProfile(
            organization=organization,
            trusted_profile=trusted_profile,
            trusted_profile_version=trusted_profile_version,
        )

    def create_trusted_profile_from_published_clone(
        self,
        *,
        profile_name: str,
        display_name: str,
        description: str = "",
        seed_trusted_profile_id: str,
        created_by_user_id: str | None = None,
        request_context: RequestContext | None = None,
    ) -> tuple[TrustedProfile, TrustedProfileVersion]:
        """Create one new trusted profile seeded from an existing published version."""
        organization = self._ensure_request_organization(request_context)
        seed_profile = self.get_trusted_profile(
            seed_trusted_profile_id,
            request_context=request_context,
        )
        seed_version = self.get_current_published_version(
            seed_profile.trusted_profile_id,
            request_context=request_context,
        )
        created_at = self._now_provider()
        trusted_profile = self._repository.get_or_create_trusted_profile(
            TrustedProfile(
                trusted_profile_id=self._build_trusted_profile_id(
                    organization_id=organization.organization_id,
                    profile_name=profile_name,
                ),
                organization_id=organization.organization_id,
                profile_name=profile_name,
                display_name=display_name,
                source_kind="published_clone",
                bundle_ref=None,
                description=str(description or "").strip(),
                version_label=seed_profile.version_label,
                created_by_user_id=created_by_user_id,
                created_at=created_at,
            )
        )
        bundle_payload = self._replace_traceability_profile(
            seed_version.bundle_payload,
            profile_name=profile_name,
            display_name=display_name,
            description=str(description or "").strip(),
            version_label=seed_profile.version_label,
            template_artifact_ref=seed_version.template_artifact_ref,
        )
        normalized_bundle_payload, canonical_bundle_json, content_hash = self._repository.serialize_bundle_payload(
            bundle_payload,
            template_artifact_ref=seed_version.template_artifact_ref,
            template_file_hash=seed_version.template_file_hash,
        )
        trusted_profile_version = self._repository.get_or_create_trusted_profile_version(
            TrustedProfileVersion(
                trusted_profile_version_id=self._build_trusted_profile_version_id(
                    organization_id=organization.organization_id,
                    profile_name=profile_name,
                    version_number=1,
                ),
                organization_id=organization.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                version_number=1,
                bundle_payload=normalized_bundle_payload,
                canonical_bundle_json=canonical_bundle_json,
                content_hash=content_hash,
                template_artifact_id=seed_version.template_artifact_id,
                template_artifact_ref=seed_version.template_artifact_ref,
                template_file_hash=seed_version.template_file_hash,
                source_kind="published_clone",
                base_trusted_profile_version_id=seed_version.trusted_profile_version_id,
                created_by_user_id=created_by_user_id,
                created_at=created_at,
            )
        )
        trusted_profile = self._repository.set_current_published_version(
            trusted_profile.trusted_profile_id,
            trusted_profile_version.trusted_profile_version_id,
        )
        return trusted_profile, trusted_profile_version

    def bootstrap_filesystem_profiles(
        self,
        *,
        request_context: RequestContext | None = None,
    ) -> list[TrustedProfileVersion]:
        """Provision persisted rows for local filesystem profiles without refreshing existing versions."""
        organization = self._ensure_request_organization(request_context)
        bootstrapped_versions: list[TrustedProfileVersion] = []
        for metadata in self._profile_manager.list_profiles():
            profile_name = str(metadata.get("profile_name") or "").strip()
            if not profile_name:
                continue
            existing_profile = self._get_trusted_profile_by_name_or_none(
                organization.organization_id,
                profile_name,
            )
            if existing_profile is None:
                _, trusted_profile_version = self._bootstrap_new_filesystem_profile(
                    organization=organization,
                    profile_name=profile_name,
                    metadata=metadata,
                )
                bootstrapped_versions.append(trusted_profile_version)
                continue
            try:
                current_version = self._repository.get_current_published_version(
                    existing_profile.organization_id,
                    existing_profile.trusted_profile_id,
                )
                bootstrapped_versions.append(current_version)
            except ValueError:
                repaired_version = self._repair_trusted_profile_current_version(existing_profile)
                if repaired_version is not None:
                    bootstrapped_versions.append(repaired_version)
        return bootstrapped_versions

    def get_active_profile_name(self) -> str:
        """Return the current local active profile name used for default selection."""
        active_profile_name = str(self._profile_manager.get_active_profile_name() or "").strip()
        return active_profile_name or "default"

    def get_selected_profile_name(
        self,
        *,
        request_context: RequestContext | None = None,
    ) -> str:
        """Return the current selected profile name for the active delivery mode."""
        organization = self._ensure_request_organization(request_context)
        if self._uses_local_profile_fallback(request_context):
            return self.get_active_profile_name()
        return self._get_default_trusted_profile(organization).profile_name

    def ensure_organization_default_profile(
        self,
        *,
        organization_id: str,
        created_by_user_id: str | None = None,
    ) -> TrustedProfile:
        """Ensure one hosted organization has its persisted default trusted profile seeded."""
        organization = self._lineage_store.get_organization(organization_id)
        existing_default = self._get_default_trusted_profile_or_none(organization)
        if existing_default is None:
            metadata = self._profile_manager.get_profile_metadata("default")
            existing_default, _ = self._bootstrap_new_filesystem_profile(
                organization=organization,
                profile_name="default",
                metadata=metadata,
                created_by_user_id=created_by_user_id,
            )
        else:
            try:
                self._repository.get_current_published_version(
                    existing_default.organization_id,
                    existing_default.trusted_profile_id,
                )
            except ValueError:
                self._repair_trusted_profile_current_version(existing_default)
        self._lineage_store.set_organization_default_trusted_profile(
            organization_id=organization.organization_id,
            trusted_profile_id=existing_default.trusted_profile_id,
        )
        return self._repository.get_trusted_profile(
            organization.organization_id,
            existing_default.trusted_profile_id,
        )

    def _bootstrap_new_filesystem_profile(
        self,
        *,
        organization: Organization,
        profile_name: str,
        metadata: dict[str, Any],
        created_by_user_id: str | None = None,
    ) -> tuple[TrustedProfile, TrustedProfileVersion]:
        trusted_profile = self._repository.get_or_create_trusted_profile(
            TrustedProfile(
                trusted_profile_id=self._build_trusted_profile_id(
                    organization_id=organization.organization_id,
                    profile_name=profile_name,
                ),
                organization_id=organization.organization_id,
                profile_name=profile_name,
                display_name=str(metadata.get("display_name") or profile_name).strip() or profile_name,
                source_kind="seeded" if profile_name == "default" else "filesystem_bootstrap",
                bundle_ref=str(self._require_profile_dir(profile_name)),
                description=str(metadata.get("description") or "").strip(),
                version_label=str(metadata.get("version") or "").strip() or None,
                created_by_user_id=created_by_user_id,
                created_at=self._now_provider(),
            )
        )
        trusted_profile_version = self._persist_filesystem_profile_version(
            trusted_profile=trusted_profile,
            metadata=metadata,
            created_by_user_id=created_by_user_id,
        )
        trusted_profile = self._repository.set_current_published_version(
            trusted_profile.trusted_profile_id,
            trusted_profile_version.trusted_profile_version_id,
        )
        return trusted_profile, trusted_profile_version

    def _persist_filesystem_profile_version(
        self,
        *,
        trusted_profile: TrustedProfile,
        metadata: dict[str, Any],
        created_by_user_id: str | None = None,
    ) -> TrustedProfileVersion:
        bundle_payload, template_artifact, template_artifact_ref = self._load_filesystem_bundle_payload(
            trusted_profile.organization_id,
            trusted_profile.profile_name,
            metadata=metadata,
        )
        normalized_bundle_payload, canonical_bundle_json, content_hash = self._repository.serialize_bundle_payload(
            bundle_payload,
            template_artifact_ref=template_artifact_ref,
            template_file_hash=template_artifact.content_hash,
        )
        existing_versions = self._repository.list_trusted_profile_versions(trusted_profile.trusted_profile_id)
        equivalent_version = next(
            (version for version in existing_versions if version.content_hash == content_hash),
            None,
        )
        if equivalent_version is not None:
            return equivalent_version
        version_number = self._repository.get_next_trusted_profile_version_number(trusted_profile.trusted_profile_id)
        return self._repository.get_or_create_trusted_profile_version(
            TrustedProfileVersion(
                trusted_profile_version_id=self._build_trusted_profile_version_id(
                    organization_id=trusted_profile.organization_id,
                    profile_name=trusted_profile.profile_name,
                    version_number=version_number,
                ),
                organization_id=trusted_profile.organization_id,
                trusted_profile_id=trusted_profile.trusted_profile_id,
                version_number=version_number,
                bundle_payload=normalized_bundle_payload,
                canonical_bundle_json=canonical_bundle_json,
                content_hash=content_hash,
                template_artifact_id=template_artifact.template_artifact_id,
                template_artifact_ref=template_artifact_ref,
                template_file_hash=template_artifact.content_hash,
                source_kind="filesystem_bootstrap",
                created_by_user_id=created_by_user_id,
                created_at=self._now_provider(),
            )
        )

    def _load_filesystem_bundle_payload(
        self,
        organization_id: str,
        profile_name: str,
        *,
        metadata: dict[str, Any],
    ) -> tuple[dict[str, object], TemplateArtifact, str]:
        profile_dir = self._require_profile_dir(profile_name)
        loader = ConfigLoader(
            config_dir=profile_dir,
            legacy_config_dir=self._get_legacy_config_dir(),
        )
        behavioral_bundle = {
            "review_rules": loader.get_review_rules(),
            "labor_mapping": loader.get_labor_mapping(),
            "equipment_mapping": loader.get_equipment_mapping(),
            "labor_slots": loader.get_labor_slots(),
            "equipment_slots": loader.get_equipment_slots(),
            "export_settings": loader.get_export_settings(),
            "rates": loader.get_rates(),
            "vendor_normalization": loader.get_vendor_normalization(),
            "phase_mapping": loader.get_phase_mapping(),
            "input_model": loader.get_input_model(),
            "recap_template_map": loader.get_recap_template_map(),
            "template": loader.get_template_metadata(),
        }
        template_path = loader.get_template_path()
        template_artifact_ref = template_path.name
        template_bytes = template_path.read_bytes()
        template_hash = hashlib.sha256(template_bytes).hexdigest()
        template_artifact = self._lineage_store.get_or_create_template_artifact(
            build_template_artifact(
                template_artifact_id=f"template-artifact:{organization_id}:{template_hash}",
                organization_id=organization_id,
                original_filename=template_path.name,
                content_bytes=template_bytes,
                created_at=self._now_provider(),
            )
        )
        behavioral_bundle["template"] = dict(
            behavioral_bundle["template"],
            template_artifact_ref=template_artifact_ref,
            template_file_hash=template_artifact.content_hash,
        )
        return (
            {
                "behavioral_bundle": behavioral_bundle,
                "traceability": {
                    "trusted_profile": {
                        "profile_name": profile_name,
                        "display_name": str(metadata.get("display_name") or profile_name).strip() or profile_name,
                        "description": str(metadata.get("description") or "").strip(),
                        "version": str(metadata.get("version") or "").strip() or None,
                        "template_filename": template_artifact_ref,
                        "template_artifact_ref": template_artifact_ref,
                    }
                },
            },
            template_artifact,
            template_artifact_ref,
        )

    def _repair_trusted_profile_current_version(
        self,
        trusted_profile: TrustedProfile,
    ) -> TrustedProfileVersion | None:
        if not self._can_repair_from_filesystem(trusted_profile):
            return None
        metadata = self._profile_manager.get_profile_metadata(trusted_profile.profile_name)
        trusted_profile_version = self._persist_filesystem_profile_version(
            trusted_profile=trusted_profile,
            metadata=metadata,
        )
        self._repository.set_current_published_version(
            trusted_profile.trusted_profile_id,
            trusted_profile_version.trusted_profile_version_id,
        )
        return trusted_profile_version

    def _replace_traceability_profile(
        self,
        bundle_payload: dict[str, Any],
        *,
        profile_name: str,
        display_name: str,
        description: str,
        version_label: str | None,
        template_artifact_ref: str | None,
    ) -> dict[str, Any]:
        traceability = dict(bundle_payload.get("traceability", {}))
        existing_profile = traceability.get("trusted_profile", {})
        if not isinstance(existing_profile, dict):
            existing_profile = {}
        traceability["trusted_profile"] = {
            **existing_profile,
            "profile_name": profile_name,
            "display_name": display_name,
            "description": description,
            "version": version_label,
            "template_artifact_ref": template_artifact_ref,
            "template_filename": str(
                existing_profile.get("template_filename")
                or existing_profile.get("template_artifact_ref")
                or template_artifact_ref
                or "recap_template.xlsx"
            ),
        }
        return dict(bundle_payload, traceability=traceability)

    def _get_trusted_profile_by_name_or_none(
        self,
        organization_id: str,
        profile_name: str,
    ) -> TrustedProfile | None:
        try:
            return self._repository.get_trusted_profile_by_name(organization_id, profile_name)
        except KeyError:
            return None

    def _can_repair_from_filesystem(self, trusted_profile: TrustedProfile) -> bool:
        if trusted_profile.source_kind not in {"seeded", "filesystem_bootstrap"}:
            return False
        return self._profile_manager.get_profile_dir(trusted_profile.profile_name) is not None

    def _require_profile_dir(self, profile_name: str) -> Path:
        profile_dir = self._profile_manager.get_profile_dir(profile_name)
        if profile_dir is None:
            raise FileNotFoundError(f"Profile '{profile_name}' was not found.")
        return profile_dir

    def _resolve_selected_profile_name(self, profile_name: str | None) -> str:
        selected_profile_name = str(profile_name or "").strip()
        return selected_profile_name or self.get_active_profile_name()

    def _resolve_selected_trusted_profile(
        self,
        *,
        organization: Organization,
        profile_name: str | None,
        request_context: RequestContext | None = None,
    ) -> TrustedProfile:
        selected_profile_name = str(profile_name or "").strip()
        if not selected_profile_name and not self._uses_local_profile_fallback(request_context):
            return self._get_default_trusted_profile(organization)
        resolved_profile_name = selected_profile_name or self.get_active_profile_name()
        try:
            return self._repository.get_trusted_profile_by_name(
                organization.organization_id,
                resolved_profile_name,
            )
        except KeyError as exc:
            raise ValueError(f"Trusted profile '{resolved_profile_name}' was not found.") from exc

    def _get_default_trusted_profile(self, organization: Organization) -> TrustedProfile:
        trusted_profile = self._get_default_trusted_profile_or_none(organization)
        if trusted_profile is None:
            return self.ensure_organization_default_profile(
                organization_id=organization.organization_id,
            )
        return trusted_profile

    def _get_default_trusted_profile_or_none(self, organization: Organization) -> TrustedProfile | None:
        default_trusted_profile_id = str(organization.default_trusted_profile_id or "").strip()
        if default_trusted_profile_id:
            try:
                return self._repository.get_trusted_profile(
                    organization.organization_id,
                    default_trusted_profile_id,
                )
            except KeyError:
                pass
        return self._get_trusted_profile_by_name_or_none(organization.organization_id, "default")

    def _ensure_profiles_available(
        self,
        *,
        organization: Organization,
        request_context: RequestContext | None,
    ) -> None:
        if self._uses_local_profile_fallback(request_context):
            self.bootstrap_filesystem_profiles(request_context=request_context)
            return
        self.ensure_organization_default_profile(organization_id=organization.organization_id)

    def _uses_local_profile_fallback(self, request_context: RequestContext | None) -> bool:
        return is_local_request_context(request_context)

    def _ensure_request_organization(
        self,
        request_context: RequestContext | None,
    ) -> Organization:
        resolved_request_context = resolve_request_context(request_context)
        try:
            return self._lineage_store.get_organization(resolved_request_context.organization_id)
        except KeyError:
            pass
        created_at = self._now_provider()
        return self._lineage_store.ensure_organization(
            organization_id=resolved_request_context.organization_id,
            slug=self._organization_slug(resolved_request_context.organization_id),
            display_name=self._organization_display_name(resolved_request_context.organization_id),
            created_at=created_at,
            is_seeded=resolved_request_context.organization_id == "org-default",
        )

    def _build_trusted_profile_id(self, *, organization_id: str, profile_name: str) -> str:
        return f"trusted-profile:{organization_id}:{profile_name}"

    def _build_trusted_profile_version_id(
        self,
        *,
        organization_id: str,
        profile_name: str,
        version_number: int,
    ) -> str:
        return f"trusted-profile-version:{organization_id}:{profile_name}:v{version_number}"

    def _organization_slug(self, organization_id: str) -> str:
        if organization_id == "org-default":
            return "default-org"
        normalized = str(organization_id or "").strip().lower().replace("_", "-").replace(":", "-")
        return normalized or "organization"

    def _organization_display_name(self, organization_id: str) -> str:
        if organization_id == "org-default":
            return "Default Organization"
        return str(organization_id or "").strip() or "Organization"

    def _get_legacy_config_dir(self) -> Path | None:
        legacy_config_dir = getattr(self._profile_manager, "_legacy_config_root", None)
        if isinstance(legacy_config_dir, Path):
            return legacy_config_dir
        return None
