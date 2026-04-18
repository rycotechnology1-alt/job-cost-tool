"""Compatibility adapter that materializes persisted bundles for filesystem-shaped execution flows."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from core.config import ProfileManager
from core.models.lineage import ProfileSnapshot, TemplateArtifact, TrustedProfileVersion
from infrastructure.persistence import LineageStore


@dataclass(frozen=True, slots=True)
class MaterializedProfileExecutionBundle:
    """Temporary explicit filesystem bundle used by legacy parser/review/export paths."""

    config_dir: Path
    legacy_config_dir: Path
    template_path: Path | None


class ProfileExecutionCompatibilityAdapter:
    """Materialize persisted published versions and snapshots for existing execution pipelines."""

    def __init__(
        self,
        *,
        lineage_store: LineageStore,
        profile_manager: ProfileManager | None = None,
    ) -> None:
        self._lineage_store = lineage_store
        self._profile_manager = profile_manager or ProfileManager()

    @contextmanager
    def materialize_published_version_bundle(
        self,
        trusted_profile_version: TrustedProfileVersion,
        *,
        require_template_artifact: bool = True,
    ) -> Iterator[MaterializedProfileExecutionBundle]:
        """Materialize one persisted published version into an execution-ready config bundle."""
        with TemporaryDirectory(prefix="job-cost-profile-config-") as config_tmp:
            config_dir = Path(config_tmp).resolve()
            template_path = self._write_bundle_payload(
                config_dir=config_dir,
                bundle_payload=trusted_profile_version.bundle_payload,
                template_artifact_id=trusted_profile_version.template_artifact_id,
                template_artifact_ref=trusted_profile_version.template_artifact_ref,
                template_file_hash=trusted_profile_version.template_file_hash,
                require_template_artifact=require_template_artifact,
            )
            shared_legacy_dir = self._get_shared_legacy_config_dir()
            if shared_legacy_dir is not None:
                yield MaterializedProfileExecutionBundle(
                    config_dir=config_dir,
                    legacy_config_dir=shared_legacy_dir,
                    template_path=template_path,
                )
                return
            with self._temporary_legacy_config_dir() as legacy_config_dir:
                yield MaterializedProfileExecutionBundle(
                    config_dir=config_dir,
                    legacy_config_dir=legacy_config_dir,
                    template_path=template_path,
                )

    @contextmanager
    def materialize_snapshot_bundle(
        self,
        profile_snapshot: ProfileSnapshot,
        *,
        require_template_artifact: bool = True,
    ) -> Iterator[MaterializedProfileExecutionBundle]:
        """Materialize one persisted immutable snapshot into the legacy execution shape."""
        with TemporaryDirectory(prefix="job-cost-snapshot-config-") as config_tmp:
            config_dir = Path(config_tmp).resolve()
            template_path = self._write_bundle_payload(
                config_dir=config_dir,
                bundle_payload=profile_snapshot.bundle_payload,
                template_artifact_id=profile_snapshot.template_artifact_id,
                template_artifact_ref=profile_snapshot.template_artifact_ref,
                template_file_hash=profile_snapshot.template_file_hash,
                require_template_artifact=require_template_artifact,
            )
            with self._temporary_legacy_config_dir() as legacy_config_dir:
                yield MaterializedProfileExecutionBundle(
                    config_dir=config_dir,
                    legacy_config_dir=legacy_config_dir,
                    template_path=template_path,
                )

    def _write_bundle_payload(
        self,
        *,
        config_dir: Path,
        bundle_payload: dict[str, object],
        template_artifact_id: str | None,
        template_artifact_ref: str | None,
        template_file_hash: str | None,
        require_template_artifact: bool,
    ) -> Path | None:
        behavioral_bundle = self._behavioral_bundle(bundle_payload)
        traceability = self._traceability_bundle(bundle_payload)
        file_payloads = {
            "labor_mapping.json": behavioral_bundle.get("labor_mapping", {}),
            "equipment_mapping.json": behavioral_bundle.get("equipment_mapping", {}),
            "phase_mapping.json": behavioral_bundle.get("phase_mapping", {}),
            "vendor_normalization.json": behavioral_bundle.get("vendor_normalization", {}),
            "input_model.json": behavioral_bundle.get("input_model", {}),
            "recap_template_map.json": behavioral_bundle.get("recap_template_map", {}),
            "target_labor_classifications.json": behavioral_bundle.get("labor_slots", {}),
            "target_equipment_classifications.json": behavioral_bundle.get("equipment_slots", {}),
            "rates.json": behavioral_bundle.get("rates", {}),
            "review_rules.json": behavioral_bundle.get("review_rules", {}),
            "export_settings.json": behavioral_bundle.get("export_settings", {}),
            "template_metadata.json": behavioral_bundle.get("template", {}),
            "profile.json": {
                "profile_name": str(self._nested_lookup(traceability, "trusted_profile", "profile_name") or "snapshot"),
                "display_name": str(self._nested_lookup(traceability, "trusted_profile", "display_name") or "Snapshot"),
                "description": str(self._nested_lookup(traceability, "trusted_profile", "description") or ""),
                "version": str(self._nested_lookup(traceability, "trusted_profile", "version") or ""),
                "template_filename": str(
                    self._nested_lookup(traceability, "trusted_profile", "template_filename")
                    or self._nested_lookup(traceability, "trusted_profile", "template_artifact_ref")
                    or "recap_template.xlsx"
                ),
            },
        }
        for file_name, payload in file_payloads.items():
            (config_dir / file_name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if not require_template_artifact:
            return None
        template_artifact = self._load_template_artifact(template_artifact_id, template_file_hash)
        template_filename = str(
            template_artifact_ref
            or self._nested_lookup(traceability, "trusted_profile", "template_filename")
            or self._nested_lookup(traceability, "trusted_profile", "template_artifact_ref")
            or template_artifact.original_filename
        ).strip() or template_artifact.original_filename
        template_path = (config_dir / template_filename).resolve()
        template_path.write_bytes(template_artifact.content_bytes)
        return template_path

    def _load_template_artifact(
        self,
        template_artifact_id: str | None,
        template_file_hash: str | None,
    ) -> TemplateArtifact:
        template_artifact_id_text = str(template_artifact_id or "").strip()
        if not template_artifact_id_text:
            raise ValueError("Persisted bundle is missing a template artifact id.")
        template_artifact = self._lineage_store.get_template_artifact(template_artifact_id_text)
        if template_file_hash and template_artifact.content_hash != template_file_hash:
            raise ValueError("Persisted template artifact does not match the recorded template hash.")
        return template_artifact

    @contextmanager
    def _temporary_legacy_config_dir(self) -> Iterator[Path]:
        with TemporaryDirectory(prefix="job-cost-materialized-legacy-") as legacy_tmp:
            legacy_config_dir = Path(legacy_tmp).resolve()
            (legacy_config_dir / "phase_catalog.json").write_text('{"phases":[]}', encoding="utf-8")
            yield legacy_config_dir

    def _behavioral_bundle(self, bundle_payload: dict[str, object]) -> dict[str, object]:
        raw_bundle = bundle_payload.get("behavioral_bundle")
        if isinstance(raw_bundle, dict):
            return dict(raw_bundle)
        return dict(bundle_payload)

    def _traceability_bundle(self, bundle_payload: dict[str, object]) -> dict[str, object]:
        raw_traceability = bundle_payload.get("traceability")
        if isinstance(raw_traceability, dict):
            return dict(raw_traceability)
        return {}

    def _nested_lookup(self, payload: dict[str, object], *keys: str) -> object | None:
        current: object = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _get_shared_legacy_config_dir(self) -> Path | None:
        legacy_config_dir = getattr(self._profile_manager, "_legacy_config_root", None)
        if isinstance(legacy_config_dir, Path) and legacy_config_dir.exists():
            return legacy_config_dir
        return None
