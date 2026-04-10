"""Profile authoring API contracts for the Phase 2A backend slice."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.schemas.common import ApiModel


class ProfileVersionSummaryResponse(ApiModel):
    """Current published version metadata returned by profile authoring APIs."""

    trusted_profile_version_id: str
    version_number: int
    content_hash: str
    template_artifact_ref: str | None = None
    template_file_hash: str | None = None
    template_filename: str | None = None


class DeferredDomainsResponse(ApiModel):
    """Read-only deferred profile domains exposed for inspection only."""

    vendor_normalization: dict
    phase_mapping: dict
    input_model: dict
    recap_template_map: dict


class DefaultOmitRuleRow(ApiModel):
    """Editable default-omit rule row."""

    phase_code: str
    phase_name: str = ""


class PhaseOptionRow(ApiModel):
    """Known default-omit phase option row."""

    phase_code: str
    phase_name: str = ""


class LaborMappingRow(ApiModel):
    """Editable labor mapping row."""

    raw_value: str
    target_classification: str = ""
    notes: str = ""
    is_observed: bool = False
    is_required_for_recent_processing: bool = False


class EquipmentMappingRow(ApiModel):
    """Editable equipment mapping row."""

    raw_description: str
    raw_pattern: str | None = None
    target_category: str = ""
    is_observed: bool = False
    is_required_for_recent_processing: bool = False
    prediction_target: str | None = None
    prediction_confidence_label: str | None = None


class ClassificationSlotRow(ApiModel):
    """Editable classification slot row."""

    slot_id: str
    label: str = ""
    active: bool


class LaborRateRow(ApiModel):
    """Editable labor rate row."""

    classification: str
    standard_rate: str = ""
    overtime_rate: str = ""
    double_time_rate: str = ""


class EquipmentRateRow(ApiModel):
    """Editable equipment rate row."""

    category: str
    rate: str = ""


class PublishedProfileDetailResponse(ApiModel):
    """Read-only published profile detail for authoring entry."""

    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None = None
    current_published_version: ProfileVersionSummaryResponse
    open_draft_id: str | None = None
    deferred_domains: DeferredDomainsResponse


class CreateTrustedProfileRequest(ApiModel):
    """Request body for creating one new trusted profile from an existing published profile seed."""

    profile_name: str
    display_name: str
    description: str = ""
    seed_trusted_profile_id: str | None = None


class ProfileSyncExportResponse(ApiModel):
    """Published-version desktop-sync export metadata returned after archive creation."""

    trusted_profile_sync_export_id: str
    trusted_profile_version_id: str
    trusted_profile_id: str
    profile_name: str
    display_name: str
    version_number: int
    archive_filename: str
    artifact_file_hash: str | None = None
    created_at: datetime
    download_url: str


class DraftEditorStateResponse(ApiModel):
    """Full draft editor state for the approved Phase 2A settings domains."""

    trusted_profile_draft_id: str
    trusted_profile_id: str
    profile_name: str
    display_name: str
    description: str
    version_label: str | None = None
    current_published_version: ProfileVersionSummaryResponse
    base_trusted_profile_version_id: str | None = None
    draft_content_hash: str
    default_omit_rules: list[DefaultOmitRuleRow]
    default_omit_phase_options: list[PhaseOptionRow]
    labor_mappings: list[LaborMappingRow]
    equipment_mappings: list[EquipmentMappingRow]
    labor_slots: list[ClassificationSlotRow]
    equipment_slots: list[ClassificationSlotRow]
    labor_rates: list[LaborRateRow]
    equipment_rates: list[EquipmentRateRow]
    deferred_domains: DeferredDomainsResponse
    validation_errors: list[str]


class DefaultOmitPatchRequest(ApiModel):
    """Request body for replacing draft default-omit rows."""

    default_omit_rules: list[DefaultOmitRuleRow] = Field(default_factory=list)


class LaborMappingsPatchRequest(ApiModel):
    """Request body for replacing draft labor mappings."""

    labor_mappings: list[LaborMappingRow] = Field(default_factory=list)


class EquipmentMappingsPatchRequest(ApiModel):
    """Request body for replacing draft equipment mappings."""

    equipment_mappings: list[EquipmentMappingRow] = Field(default_factory=list)


class ClassificationsPatchRequest(ApiModel):
    """Request body for replacing draft labor/equipment slot rows."""

    labor_slots: list[ClassificationSlotRow] = Field(default_factory=list)
    equipment_slots: list[ClassificationSlotRow] = Field(default_factory=list)


class RatesPatchRequest(ApiModel):
    """Request body for replacing draft labor/equipment rate rows."""

    labor_rates: list[LaborRateRow] = Field(default_factory=list)
    equipment_rates: list[EquipmentRateRow] = Field(default_factory=list)
