export interface SourceUploadResponse {
  upload_id: string;
  original_filename: string;
  content_type: string;
  file_size_bytes: number;
  storage_ref: string;
}

export interface TrustedProfileResponse {
  trusted_profile_id: string;
  profile_name: string;
  display_name: string;
  description: string;
  version_label: string | null;
  template_filename: string | null;
  source_kind: string;
  current_published_version_number: number;
  has_open_draft: boolean;
  is_active_profile: boolean;
  archived_at: string | null;
}

export interface HistoricalExportStatusResponse {
  status_code: string;
  is_reproducible: boolean;
  detail: string;
}

export interface ProcessingRunResponse {
  processing_run_id: string;
  source_document_id: string;
  source_document_filename: string;
  profile_snapshot_id: string;
  trusted_profile_id: string | null;
  trusted_profile_name: string | null;
  status: string;
  aggregate_blockers: string[];
  record_count: number;
  created_at: string;
  historical_export_status: HistoricalExportStatusResponse;
}

export interface RunRecordResponse {
  run_record_id: string;
  record_key: string;
  record_index: number;
  canonical_record: Record<string, unknown>;
  source_page: number | null;
  source_line_text: string | null;
  created_at: string;
}

export interface ProcessingRunDetailResponse extends ProcessingRunResponse {
  run_records: RunRecordResponse[];
}

export interface ReviewRecordResponse {
  record_type: string;
  phase_code: string | null;
  cost: number | null;
  hours: number | null;
  hour_type: string | null;
  union_code: string | null;
  labor_class_normalized: string | null;
  vendor_name: string | null;
  equipment_description: string | null;
  equipment_category: string | null;
  confidence: number;
  raw_description: string;
  labor_class_raw: string | null;
  job_number: string | null;
  job_name: string | null;
  transaction_type: string | null;
  phase_name_raw: string | null;
  employee_id: string | null;
  employee_name: string | null;
  vendor_id_raw: string | null;
  source_page: number | null;
  source_line_text: string | null;
  warnings: string[];
  record_type_normalized: string | null;
  recap_labor_slot_id: string | null;
  recap_labor_classification: string | null;
  recap_equipment_slot_id: string | null;
  vendor_name_normalized: string | null;
  equipment_mapping_key: string | null;
  is_omitted: boolean;
}

export interface ReviewSessionResponse {
  review_session_id: string;
  processing_run_id: string;
  current_revision: number;
  session_revision: number;
  blocking_issues: string[];
  historical_export_status: HistoricalExportStatusResponse;
  records: ReviewRecordResponse[];
}

export interface ReviewEditFields {
  recap_labor_classification?: string | null;
  equipment_category?: string | null;
  vendor_name_normalized?: string | null;
  is_omitted?: boolean | null;
}

export interface ReviewEditDelta {
  record_key: string;
  changed_fields: ReviewEditFields;
}

export interface ExportArtifactResponse {
  export_artifact_id: string;
  processing_run_id: string;
  review_session_id: string;
  session_revision: number;
  artifact_kind: string;
  template_artifact_id: string | null;
  file_hash: string | null;
  created_at: string;
  download_url: string;
}

export interface ProfileVersionSummaryResponse {
  trusted_profile_version_id: string;
  version_number: number;
  content_hash: string;
  template_artifact_ref: string | null;
  template_file_hash: string | null;
  template_filename: string | null;
}

export interface DeferredDomainsResponse {
  vendor_normalization: Record<string, unknown>;
  phase_mapping: Record<string, unknown>;
  input_model: Record<string, unknown>;
  recap_template_map: Record<string, unknown>;
}

export interface DefaultOmitRuleRow {
  phase_code: string;
  phase_name: string;
}

export interface PhaseOptionRow {
  phase_code: string;
  phase_name: string;
}

export interface LaborMappingRow {
  raw_value: string;
  target_classification: string;
  notes: string;
  is_observed: boolean;
}

export interface EquipmentMappingRow {
  raw_description: string;
  raw_pattern?: string | null;
  target_category: string;
  is_observed: boolean;
}

export interface ClassificationSlotRow {
  slot_id: string;
  label: string;
  active: boolean;
}

export interface LaborRateRow {
  classification: string;
  standard_rate: string;
  overtime_rate: string;
  double_time_rate: string;
}

export interface EquipmentRateRow {
  category: string;
  rate: string;
}

export interface PublishedProfileDetailResponse {
  trusted_profile_id: string;
  profile_name: string;
  display_name: string;
  description: string;
  version_label: string | null;
  current_published_version: ProfileVersionSummaryResponse;
  open_draft_id: string | null;
  deferred_domains: DeferredDomainsResponse;
}

export interface CreateTrustedProfileRequest {
  profile_name: string;
  display_name: string;
  description: string;
  seed_trusted_profile_id?: string | null;
}

export interface ProfileSyncExportResponse {
  trusted_profile_sync_export_id: string;
  trusted_profile_version_id: string;
  trusted_profile_id: string;
  profile_name: string;
  display_name: string;
  version_number: number;
  archive_filename: string;
  artifact_file_hash: string | null;
  created_at: string;
  download_url: string;
}

export interface DraftEditorStateResponse {
  trusted_profile_draft_id: string;
  trusted_profile_id: string;
  profile_name: string;
  display_name: string;
  description: string;
  version_label: string | null;
  current_published_version: ProfileVersionSummaryResponse;
  base_trusted_profile_version_id: string | null;
  draft_content_hash: string;
  default_omit_rules: DefaultOmitRuleRow[];
  default_omit_phase_options: PhaseOptionRow[];
  labor_mappings: LaborMappingRow[];
  equipment_mappings: EquipmentMappingRow[];
  labor_slots: ClassificationSlotRow[];
  equipment_slots: ClassificationSlotRow[];
  labor_rates: LaborRateRow[];
  equipment_rates: EquipmentRateRow[];
  deferred_domains: DeferredDomainsResponse;
  validation_errors: string[];
}
