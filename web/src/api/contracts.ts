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
  is_active_profile: boolean;
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
