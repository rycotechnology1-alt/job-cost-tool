import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ReviewSessionResponse } from "../api/contracts";
import App from "../App";

const { uploadMock } = vi.hoisted(() => ({
  uploadMock: vi.fn(),
}));

vi.mock("@vercel/blob/client", () => ({
  upload: uploadMock,
}));

const trustedProfilesPayload = [
  {
    trusted_profile_id: "trusted-profile:org-default:default",
    profile_name: "default",
    display_name: "Default Profile",
    description: "Default trusted profile",
    version_label: "1.0",
    template_filename: "recap_template.xlsx",
    source_kind: "seeded",
    current_published_version_number: 1,
    has_open_draft: false,
    is_active_profile: true,
    archived_at: null,
  },
  {
    trusted_profile_id: "trusted-profile:org-default:alternate",
    profile_name: "alternate",
    display_name: "Alternate Profile",
    description: "Alternate trusted profile",
    version_label: "1.1",
    template_filename: "alternate_template.xlsx",
    source_kind: "filesystem_bootstrap",
    current_published_version_number: 1,
    has_open_draft: false,
    is_active_profile: false,
    archived_at: null,
  },
];

const reviewOptionSets = {
  default: {
    labor: ["103 Journeyman", "103 Foreman"],
    equipment: ["Pick-up Truck"],
  },
  alternate: {
    labor: ["ALT Journeyman"],
    equipment: ["ALT Truck"],
  },
} as const;

function buildPublishedProfileDetail(versionNumber = 1, openDraftId: string | null = null) {
  return {
    trusted_profile_id: "trusted-profile:org-default:default",
    profile_name: "default",
    display_name: "Default Profile",
    description: "Default trusted profile",
    version_label: "1.0",
    current_published_version: {
      trusted_profile_version_id: `trusted-profile-version-${versionNumber}`,
      version_number: versionNumber,
      content_hash: `profile-hash-v${versionNumber}`,
      template_artifact_ref: "template-artifact:default",
      template_file_hash: "template-file-hash",
      template_filename: "recap_template.xlsx",
    },
    template_metadata: {
      template_filename: "recap_template.xlsx",
      labor_slots_total: 4,
      equipment_slots_total: 4,
      workbook_title: "Recap Template",
    },
    labor_active_slot_count: 2,
    labor_inactive_slot_count: 0,
    equipment_active_slot_count: 1,
    equipment_inactive_slot_count: 0,
    open_draft_id: openDraftId,
    deferred_domains: {
      vendor_normalization: { aliases: ["Vendor Alias"] },
      phase_mapping: { "29 .999": "labor_non_job_related" },
      input_model: { transaction_codes: ["JC", "AP"] },
      recap_template_map: { labor_section_start: "B12" },
    },
  };
}

function buildProfileDraftState() {
  return {
    trusted_profile_draft_id: "draft-1",
    trusted_profile_id: "trusted-profile:org-default:default",
    profile_name: "default",
    display_name: "Default Profile",
    description: "Default trusted profile",
    version_label: "1.0",
    current_published_version: buildPublishedProfileDetail().current_published_version,
    base_trusted_profile_version_id: "trusted-profile-version-1",
    draft_revision: 1,
    draft_content_hash: "draft-content-hash-v1",
    template_metadata: buildPublishedProfileDetail().template_metadata,
    labor_active_slot_count: 2,
    labor_inactive_slot_count: 0,
    equipment_active_slot_count: 1,
    equipment_inactive_slot_count: 0,
    default_omit_rules: [],
    default_omit_phase_options: [
      { phase_code: "20", phase_name: "Labor" },
      { phase_code: "50", phase_name: "Other Job Cost" },
    ],
    labor_mappings: [
      {
        raw_value: "NEW OBSERVED LABOR",
        target_classification: "",
        notes: "",
        is_observed: true,
        is_required_for_recent_processing: true,
      },
      {
        raw_value: "CARPENTER",
        target_classification: "103 Journeyman",
        notes: "Baseline row",
        is_observed: false,
      },
    ],
    equipment_mappings: [
      {
        raw_description: "PICK-UP TRUCK",
        target_category: "Pick-up Truck",
        is_observed: false,
      },
    ],
    labor_slots: [
      { slot_id: "labor_1", label: "103 Journeyman", active: true },
      { slot_id: "labor_2", label: "103 Foreman", active: true },
    ],
    equipment_slots: [{ slot_id: "equipment_1", label: "Pick-up Truck", active: true }],
    export_settings: {
      labor_minimum_hours: {
        enabled: false,
        threshold_hours: "",
        minimum_hours: "",
      },
    },
    labor_rates: [
      {
        classification: "103 Journeyman",
        standard_rate: "45",
        overtime_rate: "67.5",
        double_time_rate: "90",
      },
    ],
    equipment_rates: [
      {
        category: "Pick-up Truck",
        rate: "125",
      },
    ],
    deferred_domains: buildPublishedProfileDetail().deferred_domains,
    validation_errors: [],
  };
}

interface MockOptions {
  expireCachedUploadOnSecondRun?: boolean;
  initialReviewRecords?: ReturnType<typeof buildBaseReviewRecords>;
  resolveMappedLaborWarningAfterPublish?: boolean;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function buildRunPayload(profileName: "default" | "alternate", sourceFilename = "report.pdf", recordCount = 3) {
  const trustedProfile =
    trustedProfilesPayload.find((profile) => profile.profile_name === profileName) ?? trustedProfilesPayload[0];
  return {
    processing_run_id: "processing-run-1",
    source_document_id: "source-1",
    source_document_filename: sourceFilename,
    profile_snapshot_id: "profile-snapshot-1",
    trusted_profile_id: trustedProfile.trusted_profile_id,
    trusted_profile_name: trustedProfile.profile_name,
    status: "completed",
    aggregate_blockers: [],
    record_count: recordCount,
    created_at: "2026-04-05T12:00:00Z",
    is_archived: false,
    archived_at: null,
    origin_profile_display_name: trustedProfile.display_name,
    origin_profile_source_kind: trustedProfile.source_kind,
    current_revision: 0,
    export_count: 0,
    last_exported_at: null,
    historical_export_status: {
      status_code: "reproducible",
      is_reproducible: true,
      detail: "Historical exports are reproducible from captured template artifact lineage.",
    },
  };
}

function buildRunDetailPayload(
  profileName: "default" | "alternate",
  sourceFilename = "report.pdf",
  records: ReturnType<typeof buildBaseReviewRecords> = buildBaseReviewRecords(profileName),
) {
  return {
    ...buildRunPayload(profileName, sourceFilename, records.length),
    run_records: records.map((record, index) => ({
      run_record_id: `run-record-${index + 1}`,
      record_key: `record-${index}`,
      record_index: index,
      canonical_record: {
        record_type: record.record_type,
        record_type_normalized: record.record_type_normalized,
        phase_code: record.phase_code,
        vendor_name_normalized: record.vendor_name_normalized,
        labor_class_raw: record.labor_class_raw,
        equipment_description: record.equipment_description,
        cost: record.cost,
      },
      source_page: record.source_page,
      source_line_text: record.source_line_text,
      created_at: "2026-04-05T12:00:00Z",
    })),
  };
}

function buildBaseReviewRecords(profileName: "default" | "alternate"): ReviewSessionResponse["records"] {
  const optionSet = reviewOptionSets[profileName];
  return [
    {
      record_type: "material",
      phase_code: "50",
      cost: 100,
      hours: null,
      hour_type: null,
      union_code: null,
      labor_class_normalized: null,
      vendor_name: "Vendor A",
      equipment_description: null,
      equipment_category: null,
      confidence: 0.9,
      raw_description: "Material line",
      labor_class_raw: null,
      job_number: "JOB-100",
      job_name: "Sample Project",
      transaction_type: "AP",
      phase_name_raw: null,
      employee_id: null,
      employee_name: null,
      vendor_id_raw: null,
      source_page: 1,
      source_line_text: "Material source",
      warnings: [],
      record_type_normalized: "material",
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      recap_equipment_slot_id: null,
      vendor_name_normalized: "Vendor A",
      equipment_mapping_key: null,
      is_omitted: false,
    },
    {
      record_type: "material",
      phase_code: "50.3",
      cost: 240,
      hours: null,
      hour_type: null,
      union_code: null,
      labor_class_normalized: null,
      vendor_name: "Concrete Vendor",
      equipment_description: null,
      equipment_category: null,
      confidence: 0.82,
      raw_description: "Concrete delivery",
      labor_class_raw: null,
      job_number: "JOB-100",
      job_name: "Sample Project",
      transaction_type: "AP",
      phase_name_raw: null,
      employee_id: null,
      employee_name: null,
      vendor_id_raw: "V-200",
      source_page: 2,
      source_line_text: "Concrete delivery invoice",
      warnings: ["Vendor name should be confirmed"],
      record_type_normalized: "material",
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      recap_equipment_slot_id: null,
      vendor_name_normalized: "Concrete Vendor",
      equipment_mapping_key: null,
      is_omitted: false,
    },
    {
      record_type: "labor",
      phase_code: "20",
      cost: 160,
      hours: 8,
      hour_type: "ST",
      union_code: "103",
      labor_class_normalized: "J",
      vendor_name: null,
      equipment_description: optionSet.equipment[0],
      equipment_category: null,
      confidence: 0.94,
      raw_description: "Labor line",
      labor_class_raw: "J",
      job_number: "JOB-100",
      job_name: "Sample Project",
      transaction_type: "PR",
      phase_name_raw: null,
      employee_id: "E-1",
      employee_name: "Labor User",
      vendor_id_raw: null,
      source_page: 3,
      source_line_text: "Labor source",
      warnings: [],
      record_type_normalized: "labor",
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      recap_equipment_slot_id: null,
      vendor_name_normalized: null,
      equipment_mapping_key: null,
      is_omitted: false,
    },
  ];
}

function buildExtraLaborReviewRecord(
  profileName: "default" | "alternate",
  rawDescription: string,
): ReviewSessionResponse["records"][number] {
  const optionSet = reviewOptionSets[profileName];
  return {
    record_type: "labor",
    phase_code: "21",
    cost: 120,
    hours: 6,
    hour_type: "ST",
    union_code: "103",
    labor_class_normalized: "J",
    vendor_name: null,
    equipment_description: optionSet.equipment[0],
    equipment_category: null,
    confidence: 0.88,
    raw_description: rawDescription,
    labor_class_raw: "J",
    job_number: "JOB-100",
    job_name: "Sample Project",
    transaction_type: "PR",
    phase_name_raw: null,
    employee_id: "E-2",
    employee_name: "Labor Helper",
    vendor_id_raw: null,
    source_page: 4,
    source_line_text: `${rawDescription} source`,
    warnings: [],
    record_type_normalized: "labor",
    recap_labor_slot_id: null,
    recap_labor_classification: null,
    recap_equipment_slot_id: null,
    vendor_name_normalized: null,
    equipment_mapping_key: null,
    is_omitted: false,
  };
}

function buildExtraEquipmentReviewRecord(rawDescription: string): ReviewSessionResponse["records"][number] {
  return {
    record_type: "equipment",
    phase_code: "30",
    cost: 210,
    hours: 5,
    hour_type: null,
    union_code: null,
    labor_class_normalized: null,
    vendor_name: null,
    equipment_description: rawDescription,
    equipment_category: null,
    confidence: 0.86,
    raw_description: rawDescription,
    labor_class_raw: null,
    job_number: "JOB-100",
    job_name: "Sample Project",
    transaction_type: "EQ",
    phase_name_raw: null,
    employee_id: null,
    employee_name: null,
    vendor_id_raw: null,
    source_page: 5,
    source_line_text: `${rawDescription} source`,
    warnings: [],
    record_type_normalized: "equipment",
    recap_labor_slot_id: null,
    recap_labor_classification: null,
    recap_equipment_slot_id: null,
    vendor_name_normalized: null,
    equipment_mapping_key: rawDescription.toUpperCase(),
    is_omitted: false,
  };
}

function buildReviewSessionPayload(
  profileName: "default" | "alternate",
  revision: number,
  records: ReturnType<typeof buildBaseReviewRecords>,
  effectiveSourceMode: "latest_reviewed" | "original_processed" = "latest_reviewed",
  sessionRevision = revision,
) {
  const optionSet = reviewOptionSets[profileName];
  return {
    review_session_id: "review-session-1",
    processing_run_id: "processing-run-1",
    current_revision: revision,
    session_revision: sessionRevision,
    blocking_issues: [],
    labor_classification_options: [...optionSet.labor],
    equipment_classification_options: [...optionSet.equipment],
    historical_export_status: {
      status_code: "reproducible",
      is_reproducible: true,
      detail: "Historical exports are reproducible from captured template artifact lineage.",
    },
    effective_source_mode: effectiveSourceMode,
    records,
  };
}

function applyReviewEdits(
  records: ReturnType<typeof buildBaseReviewRecords>,
  edits: Array<{ record_key: string; changed_fields: Record<string, unknown> }>,
) {
  return records.map((record, index) => {
    const edit = edits.find((candidate) => candidate.record_key === `record-${index}`);
    if (!edit) {
      return { ...record };
    }

    const nextRecord = { ...record };
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "vendor_name_normalized")) {
      (nextRecord as { vendor_name_normalized: string | null }).vendor_name_normalized =
        (edit.changed_fields.vendor_name_normalized as string | null) ?? null;
    }
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "recap_labor_classification")) {
      (nextRecord as { recap_labor_classification: string | null }).recap_labor_classification =
        (edit.changed_fields.recap_labor_classification as string | null) ?? null;
    }
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "equipment_category")) {
      (nextRecord as { equipment_category: string | null }).equipment_category =
        (edit.changed_fields.equipment_category as string | null) ?? null;
    }
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "is_omitted")) {
      nextRecord.is_omitted = Boolean(edit.changed_fields.is_omitted);
    }
    return nextRecord;
  });
}

function resolvePublishedLaborWarnings(records: ReturnType<typeof buildBaseReviewRecords>) {
  return records.map((record) => {
    if (
      record.record_type_normalized !== "labor" ||
      !record.warnings.includes("PR labor detail line was recognized but labor class was not parsed cleanly.")
    ) {
      return { ...record };
    }

    return {
      ...record,
      confidence: 0.9,
      recap_labor_slot_id: "labor_1",
      recap_labor_classification: "103 Journeyman",
      warnings: [],
    };
  });
}

function installFetchMock(
  options: MockOptions & { initialReviewRecords?: ReturnType<typeof buildBaseReviewRecords> } = {},
) {
  const state = {
    trustedProfiles: JSON.parse(JSON.stringify(trustedProfilesPayload)) as typeof trustedProfilesPayload,
    currentRunProfileName: "default" as "default" | "alternate",
    currentRunSourceFilename: "report.pdf",
    currentReviewRevision: 0,
    currentRunArchived: false,
    currentReviewRecords: JSON.parse(
      JSON.stringify(options.initialReviewRecords ?? buildBaseReviewRecords("default")),
    ) as ReturnType<typeof buildBaseReviewRecords>,
    originalReviewRecords: JSON.parse(
      JSON.stringify(options.initialReviewRecords ?? buildBaseReviewRecords("default")),
    ) as ReturnType<typeof buildBaseReviewRecords>,
    uploadCounter: 0,
    uploadFilenamesById: new Map<string, string>(),
    runAttemptsByUploadId: new Map<string, number>(),
    publishedProfileDetail: buildPublishedProfileDetail(),
    draftState: buildProfileDraftState(),
  };

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url === "/api/trusted-profiles" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(state.trustedProfiles);
    }

    if (url === "/api/profiles/trusted-profile:org-default:default" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(state.publishedProfileDetail);
    }

    if (url === "/api/profiles/trusted-profile:org-default:default/draft" && init?.method === "POST") {
      state.publishedProfileDetail.open_draft_id = state.draftState.trusted_profile_draft_id;
      return jsonResponse(state.draftState, 201);
    }

    if (url === "/api/profile-drafts/draft-1" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(state.draftState);
    }

    if (url === "/api/profile-drafts/draft-1" && init?.method === "PATCH") {
      const payload = JSON.parse(String(init.body ?? "{}")) as {
        expected_draft_revision?: number;
        default_omit_rules?: typeof state.draftState.default_omit_rules;
        labor_mappings?: typeof state.draftState.labor_mappings;
        equipment_mappings?: typeof state.draftState.equipment_mappings;
        labor_slots?: typeof state.draftState.labor_slots;
        equipment_slots?: typeof state.draftState.equipment_slots;
        labor_rates?: typeof state.draftState.labor_rates;
        equipment_rates?: typeof state.draftState.equipment_rates;
        export_settings?: typeof state.draftState.export_settings;
      };
      if (payload.expected_draft_revision !== state.draftState.draft_revision) {
        return jsonResponse(
          {
            detail: {
              message: "Refresh the draft and retry with the latest revision before saving.",
              error_code: "profile_authoring_persistence_conflict",
              field_errors: {
                expected_draft_revision: ["Refresh the draft and retry with the latest revision before saving."],
              },
            },
          },
          409,
        );
      }
      const laborSlots = payload.labor_slots ?? state.draftState.labor_slots;
      const equipmentSlots = payload.equipment_slots ?? state.draftState.equipment_slots;
      state.draftState = {
        ...state.draftState,
        default_omit_rules: payload.default_omit_rules ?? state.draftState.default_omit_rules,
        labor_mappings: payload.labor_mappings ?? state.draftState.labor_mappings,
        equipment_mappings: payload.equipment_mappings ?? state.draftState.equipment_mappings,
        labor_slots: laborSlots,
        equipment_slots: equipmentSlots,
        labor_rates: payload.labor_rates ?? state.draftState.labor_rates,
        equipment_rates: payload.equipment_rates ?? state.draftState.equipment_rates,
        export_settings: payload.export_settings ?? state.draftState.export_settings,
        labor_active_slot_count: laborSlots.filter((slot) => slot.active).length,
        labor_inactive_slot_count: laborSlots.filter((slot) => !slot.active).length,
        equipment_active_slot_count: equipmentSlots.filter((slot) => slot.active).length,
        equipment_inactive_slot_count: equipmentSlots.filter((slot) => !slot.active).length,
        draft_revision: state.draftState.draft_revision + 1,
        draft_content_hash: `draft-content-hash-v${state.draftState.draft_revision + 1}`,
      };
      return jsonResponse(state.draftState);
    }

    if (url === "/api/profile-drafts/draft-1/publish" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as { expected_draft_revision?: number };
      if (payload.expected_draft_revision !== state.draftState.draft_revision) {
        return jsonResponse(
          {
            detail: {
              message: "Refresh the draft and retry with the latest revision before publishing.",
              error_code: "profile_authoring_persistence_conflict",
              field_errors: {
                expected_draft_revision: ["Refresh the draft and retry with the latest revision before publishing."],
              },
            },
          },
          409,
        );
      }
      state.publishedProfileDetail = buildPublishedProfileDetail(2, null);
      state.trustedProfiles[0] = {
        ...state.trustedProfiles[0],
        current_published_version_number: 2,
        has_open_draft: false,
      };
      return jsonResponse(state.publishedProfileDetail);
    }

    if (url === "/api/source-documents/uploads" && init?.method === "POST") {
      const formData = init.body as FormData;
      const uploadedFile = formData.get("file");
      const filename = uploadedFile instanceof File ? uploadedFile.name : `report-${state.uploadCounter + 1}.pdf`;
      const uploadId = `upload-${state.uploadCounter + 1}`;
      state.uploadCounter += 1;
      state.uploadFilenamesById.set(uploadId, filename);
      return jsonResponse(
        {
          upload_id: uploadId,
          original_filename: filename,
          content_type: "application/pdf",
          file_size_bytes: 1024,
          storage_ref: `runtime/uploads/${filename}`,
        },
        201,
      );
    }

    if (url === "/api/source-documents/blob-uploads" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as {
        storage_ref?: string;
        original_filename?: string;
        content_type?: string;
        file_size_bytes?: number;
      };
      const uploadId = payload.storage_ref?.split("/")[1] ?? `upload-${state.uploadCounter + 1}`;
      state.uploadCounter += 1;
      state.uploadFilenamesById.set(uploadId, payload.original_filename ?? "report.pdf");
      return jsonResponse(
        {
          upload_id: uploadId,
          original_filename: payload.original_filename ?? "report.pdf",
          content_type: payload.content_type ?? "application/pdf",
          file_size_bytes: payload.file_size_bytes ?? 1024,
          storage_ref: payload.storage_ref ?? `uploads/${uploadId}/report.pdf`,
        },
        201,
      );
    }

    if (url === "/api/runs" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as { trusted_profile_name?: string; upload_id?: string };
      const uploadId = payload.upload_id ?? "";
      const priorAttemptCount = state.runAttemptsByUploadId.get(uploadId) ?? 0;
      const nextAttemptCount = priorAttemptCount + 1;
      state.runAttemptsByUploadId.set(uploadId, nextAttemptCount);

      if (options.expireCachedUploadOnSecondRun && nextAttemptCount === 2) {
        return jsonResponse(
          {
            detail: "The uploaded PDF expired from temporary storage. Reselect and upload the PDF again before processing.",
          },
          410,
        );
      }

      state.currentRunProfileName = payload.trusted_profile_name === "alternate" ? "alternate" : "default";
      state.currentRunSourceFilename = state.uploadFilenamesById.get(uploadId) ?? "report.pdf";
      state.currentReviewRevision = 0;
      state.currentRunArchived = false;
      const baseReviewRecords = JSON.parse(
        JSON.stringify(options.initialReviewRecords ?? buildBaseReviewRecords(state.currentRunProfileName)),
      ) as ReturnType<typeof buildBaseReviewRecords>;
      state.currentReviewRecords =
        options.resolveMappedLaborWarningAfterPublish && state.publishedProfileDetail.current_published_version.version_number > 1
          ? resolvePublishedLaborWarnings(baseReviewRecords)
          : baseReviewRecords;
      state.originalReviewRecords = JSON.parse(JSON.stringify(state.currentReviewRecords)) as ReturnType<
        typeof buildBaseReviewRecords
      >;
      return jsonResponse(
        buildRunPayload(state.currentRunProfileName, state.currentRunSourceFilename, state.currentReviewRecords.length),
        201,
      );
    }

    if (url === "/api/runs?state=open" && (!init || !init.method || init.method === "GET")) {
      if (state.currentRunArchived) {
        return jsonResponse([]);
      }
      return jsonResponse([
        {
          ...buildRunPayload(state.currentRunProfileName, state.currentRunSourceFilename, state.currentReviewRecords.length),
          current_revision: state.currentReviewRevision,
        },
      ]);
    }

    if (url === "/api/runs?state=archived" && (!init || !init.method || init.method === "GET")) {
      if (!state.currentRunArchived) {
        return jsonResponse([]);
      }
      return jsonResponse([
        {
          ...buildRunPayload(state.currentRunProfileName, state.currentRunSourceFilename, state.currentReviewRecords.length),
          is_archived: true,
          archived_at: "2026-04-06T12:00:00Z",
          current_revision: state.currentReviewRevision,
        },
      ]);
    }

    if (url === "/api/runs/processing-run-1" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(
        {
          ...buildRunDetailPayload(
            state.currentRunProfileName,
            state.currentRunSourceFilename,
            state.currentReviewRecords,
          ),
          is_archived: state.currentRunArchived,
          archived_at: state.currentRunArchived ? "2026-04-06T12:00:00Z" : null,
          current_revision: state.currentReviewRevision,
        },
      );
    }

    if (url === "/api/runs/processing-run-1/review-session" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(
        buildReviewSessionPayload(
          state.currentRunProfileName,
          state.currentReviewRevision,
          state.currentReviewRecords,
        ),
      );
    }

    if (url === "/api/runs/processing-run-1/archive" && init?.method === "POST") {
      state.currentRunArchived = true;
      return jsonResponse({
        ...buildRunPayload(state.currentRunProfileName, state.currentRunSourceFilename, state.currentReviewRecords.length),
        is_archived: true,
        archived_at: "2026-04-06T12:00:00Z",
        current_revision: state.currentReviewRevision,
      });
    }

    if (url === "/api/runs/processing-run-1/reopen" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as {
        mode?: "latest_reviewed" | "original_processed";
        continue_from_original?: boolean;
      };
      if (payload.mode === "original_processed" && payload.continue_from_original) {
        state.currentReviewRevision += 1;
        state.currentReviewRecords = JSON.parse(JSON.stringify(state.originalReviewRecords)) as ReturnType<
          typeof buildBaseReviewRecords
        >;
        return jsonResponse(
          buildReviewSessionPayload(
            state.currentRunProfileName,
            state.currentReviewRevision,
            state.currentReviewRecords,
            "latest_reviewed",
          ),
        );
      }
      if (payload.mode === "original_processed") {
        return jsonResponse(
          buildReviewSessionPayload(
            state.currentRunProfileName,
            state.currentReviewRevision,
            state.originalReviewRecords,
            "original_processed",
            0,
          ),
        );
      }
      return jsonResponse(
        buildReviewSessionPayload(
          state.currentRunProfileName,
          state.currentReviewRevision,
          state.currentReviewRecords,
          "latest_reviewed",
        ),
      );
    }

    if (url === "/api/runs/processing-run-1/review-session/edits" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as {
        edits: Array<{ record_key: string; changed_fields: Record<string, unknown> }>;
      };
      state.currentReviewRevision += 1;
      state.currentReviewRecords = applyReviewEdits(state.currentReviewRecords, payload.edits);
      return jsonResponse(
        buildReviewSessionPayload(
          state.currentRunProfileName,
          state.currentReviewRevision,
          state.currentReviewRecords,
        ),
      );
    }

    if (url === "/api/runs/processing-run-1/exports" && init?.method === "POST") {
      return jsonResponse(
        {
          export_artifact_id: "export-artifact-1",
          processing_run_id: "processing-run-1",
          review_session_id: "review-session-1",
          session_revision: state.currentReviewRevision,
          artifact_kind: "recap_workbook",
          template_artifact_id: "template-artifact-1",
          file_hash: "abc123",
          created_at: "2026-04-05T12:00:00Z",
          download_url: "/api/exports/export-artifact-1/download",
        },
        201,
      );
    }

    if (url === "/api/exports/export-artifact-1/download") {
      return new Response(new Blob(["xlsx-bytes"]), {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": 'attachment; filename="report-recap-rev-1.xlsx"',
        },
      });
    }

    throw new Error(`Unhandled fetch call for ${url}`);
  });
}

async function stageReports(user: ReturnType<typeof userEvent.setup>, filenames: string[]) {
  await user.upload(
    screen.getByLabelText(/^source report pdf$/i),
    filenames.map((filename) => new File(["sample"], filename, { type: "application/pdf" })),
  );
}

async function expandFamily(user: ReturnType<typeof userEvent.setup>, familyLabel: string) {
  const normalizedFamilyLabel = familyLabel.replace(/^(show|hide)\s+/i, "").trim();
  const toggle = screen.getByRole("button", {
    name: new RegExp(`(?:show|hide)\\s+${normalizedFamilyLabel}`, "i"),
  });
  if (toggle.getAttribute("aria-expanded") === "true") {
    return;
  }
  await user.click(toggle);
}

async function clickRowByText(user: ReturnType<typeof userEvent.setup>, text: string) {
  const row = screen.getByText(text).closest("tr");
  expect(row).not.toBeNull();
  await user.click(row!);
}

describe("App", () => {
  const originalCreateObjectUrl = URL.createObjectURL;
  const originalRevokeObjectUrl = URL.revokeObjectURL;

  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:download-url");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    uploadMock.mockReset();
    uploadMock.mockResolvedValue({
      pathname: "uploads/upload-1/report.pdf",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    URL.createObjectURL = originalCreateObjectUrl;
    URL.revokeObjectURL = originalRevokeObjectUrl;
  });

  it("stages multiple PDFs, keeps review grouped by family, and lets row selection drive the review sidebar", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Trusted profiles loaded.")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");
    await stageReports(user, ["report-a.pdf", "report-b.pdf"]);

    expect(screen.getByRole("button", { name: /report-a\.pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /report-b\.pdf/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /report-b\.pdf/i }));
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));

    expect(await screen.findByRole("heading", { name: "report-b.pdf" })).toBeInTheDocument();
    expect(screen.getByText("No current blockers.")).toBeInTheDocument();
    expect(screen.queryByText(/profile key/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export and download/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /export and download/i })).toBeEnabled();
    expect(screen.getByText(/select a row to inspect its source context and apply edits/i)).toBeInTheDocument();
    expect(screen.getAllByText("$500.00").length).toBeGreaterThan(0);
    expect(screen.queryByText("Concrete delivery")).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^type$/i })).not.toBeInTheDocument();
    expect(within(screen.getByRole("table")).getAllByRole("columnheader")).toHaveLength(7);
    const materialToggle = screen.getByRole("button", { name: /show material/i });
    expect(within(materialToggle).getByText(/^Rows$/i)).toBeInTheDocument();
    expect(within(materialToggle).getByText(/^Raw$/i)).toBeInTheDocument();
    expect(within(materialToggle).getByText(/^Included$/i)).toBeInTheDocument();
    expect(within(materialToggle).queryByText(/^Omitted$/i)).not.toBeInTheDocument();

    await expandFamily(user, "Show Material");
    await clickRowByText(user, "Concrete delivery");

    expect(screen.getAllByText("Concrete Vendor").length).toBeGreaterThan(0);
    expect(screen.queryByText(/select a row to inspect its source context and apply edits/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Page 2/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Vendor name should be confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/edit selected row/i)).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /select concrete delivery/i })).toBeChecked();

    await clickRowByText(user, "Concrete delivery");

    expect(screen.getByRole("checkbox", { name: /select concrete delivery/i })).not.toBeChecked();
    expect(screen.getByText(/select a row to inspect its source context and apply edits/i)).toBeInTheDocument();

    await clickRowByText(user, "Concrete delivery");
    expect(screen.getByRole("checkbox", { name: /select concrete delivery/i })).toBeChecked();

    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply vendor/i }));

    expect(await screen.findByText(/applied vendor name vendor edited to 1 selected row/i)).toBeInTheDocument();
    expect(screen.getAllByText("Vendor Edited").length).toBeGreaterThan(0);
    expect(screen.getByText(/advanced the session to revision 1/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    const runRequest = fetchCalls.find(([url]) => url === "/api/runs");

    expect(runRequest).toBeDefined();
    expect(editRequest).toBeDefined();
    expect(JSON.parse(String(runRequest?.[1]?.body)).trusted_profile_name).toBe("alternate");
    expect(JSON.parse(String(editRequest?.[1]?.body)).edits[0].record_key).toBe("record-1");
  });

  it("exports and downloads the current review revision in one click", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply vendor/i }));
    await user.click(screen.getByRole("button", { name: /export and download/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith("/api/exports/export-artifact-1/download", undefined);
    });

    expect(await screen.findByText(/downloaded report-recap-rev-1\.xlsx from review revision 1/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const exportRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/exports");
    expect(exportRequest).toBeDefined();
    expect(JSON.parse(String(exportRequest?.[1]?.body)).session_revision).toBe(1);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:download-url");
  });

  it("invalidates export immediately when the selected trusted profile changes until processing is rerun", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await clickRowByText(user, "Concrete delivery");

    const exportButton = screen.getByRole("button", { name: /export and download/i });
    expect(exportButton).toBeEnabled();

    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");

    expect(await screen.findByText(/review context is stale for export/i)).toBeInTheDocument();
    expect(screen.getByText(/must be reprocessed before export is allowed/i)).toBeInTheDocument();
    expect(exportButton).toBeDisabled();

    const fetchCallsBeforeRerun = vi.mocked(globalThis.fetch).mock.calls.length;
    await user.click(exportButton);
    expect(vi.mocked(globalThis.fetch).mock.calls).toHaveLength(fetchCallsBeforeRerun);

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByText("No current blockers.");
    expect(screen.queryByText(/review context is stale for export/i)).not.toBeInTheDocument();
    await expandFamily(user, "Show Material");
    await clickRowByText(user, "Concrete delivery");
    expect(screen.getByRole("button", { name: /export and download/i })).toBeEnabled();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const runRequests = fetchCalls.filter(([url]) => url === "/api/runs");
    expect(runRequests).toHaveLength(2);
    expect(JSON.parse(String(runRequests[1]?.[1]?.body)).trusted_profile_name).toBe("alternate");
  });

  it("invalidates export after profile settings are saved until processing is rerun", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    const exportButton = screen.getByRole("button", { name: /export and download/i });
    expect(exportButton).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await screen.findByText(/live version v1 remains the web-processing source/i);
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");
    await user.clear(screen.getByLabelText(/labor raw value 2/i));
    await user.type(screen.getByLabelText(/labor raw value 2/i), "SAVED-LABOR");
    await user.click(screen.getByRole("button", { name: /save profile settings/i }));
    await screen.findByText(/saved profile settings and published live version v2 for default profile/i);

    await user.click(screen.getByRole("button", { name: /review workspace/i }));

    expect(await screen.findByText(/review context is stale for export/i)).toBeInTheDocument();
    expect(screen.getByText(/profile settings were saved after this review was processed/i)).toBeInTheDocument();
    const staleExportButton = screen.getByRole("button", { name: /export and download/i });
    expect(staleExportButton).toBeDisabled();

    const fetchCallsBeforeRerun = vi
      .mocked(globalThis.fetch)
      .mock.calls.filter(([url]) => url === "/api/runs/processing-run-1/exports").length;
    await user.click(staleExportButton);
    expect(
      vi.mocked(globalThis.fetch).mock.calls.filter(([url]) => url === "/api/runs/processing-run-1/exports").length,
    ).toBe(fetchCallsBeforeRerun);

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByText("No current blockers.");
    expect(screen.queryByText(/review context is stale for export/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export and download/i })).toBeEnabled();
  });

  it("hides resolved labor parse warnings after profile publish and rerun", async () => {
    const initialRecords = buildBaseReviewRecords("default");
    initialRecords[2] = {
      ...initialRecords[2],
      confidence: 0.6,
      labor_class_raw: null,
      labor_class_normalized: null,
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      warnings: [
        "PR labor detail line was recognized but labor class was not parsed cleanly.",
        "Medium-confidence record should be reviewed before export.",
      ],
    };

    installFetchMock({
      initialReviewRecords: initialRecords,
      resolveMappedLaborWarningAfterPublish: true,
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await clickRowByText(user, "Labor line");
    expect(screen.getByText("Current row warnings")).toBeInTheDocument();
    expect(screen.getByText(/labor class was not parsed cleanly/i)).toBeInTheDocument();
    expect(screen.getByText(/medium-confidence record should be reviewed before export/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await screen.findByText(/live version v1 remains the web-processing source/i);
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");
    await user.clear(screen.getByLabelText(/labor raw value 2/i));
    await user.type(screen.getByLabelText(/labor raw value 2/i), "SAVED-LABOR");
    await user.click(screen.getByRole("button", { name: /save profile settings/i }));
    await screen.findByText(/saved profile settings and published live version v2 for default profile/i);

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    expect(await screen.findByText(/review context is stale for export/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByText("No current blockers.");
    await expandFamily(user, "Show Labor");
    await clickRowByText(user, "Labor line");

    expect(screen.getByText("No row warnings.")).toBeInTheDocument();
    expect(screen.queryByText(/labor class was not parsed cleanly/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/medium-confidence record should be reviewed before export/i)).not.toBeInTheDocument();
  });

  it("forces a reprocess before export when the selected staged source PDF changes after a run", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report-a.pdf", "report-b.pdf"]);
    await user.click(screen.getByRole("button", { name: /report-a\.pdf/i }));
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report-a.pdf" });

    const exportButton = screen.getByRole("button", { name: /export and download/i });
    expect(exportButton).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /report-b\.pdf/i }));

    expect(await screen.findByText(/staged source pdf changed to report-b\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/must be reprocessed before export is allowed/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "report-a.pdf" })).toBeInTheDocument();
    expect(exportButton).toBeDisabled();

    const fetchCallsBeforeRerun = vi.mocked(globalThis.fetch).mock.calls.length;
    await user.click(exportButton);
    expect(vi.mocked(globalThis.fetch).mock.calls).toHaveLength(fetchCallsBeforeRerun);

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report-b.pdf" });
    expect(screen.queryByText(/staged source pdf changed to report-b\.pdf/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export and download/i })).toBeEnabled();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const runRequests = fetchCalls.filter(([url]) => url === "/api/runs");
    expect(runRequests).toHaveLength(2);
    expect(JSON.parse(String(runRequests[1]?.[1]?.body)).upload_id).toBe("upload-2");
  });

  it("shows open and archived runs in the run library and archives runs on demand", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await user.click(screen.getByRole("button", { name: /run library/i }));
    expect(await screen.findByText("Run History")).toBeInTheDocument();
    expect(screen.getAllByText("report.pdf").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: /review workspace/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /profile settings/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /select run report\.pdf/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Selected Run")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /archive run/i }));
    await user.click(screen.getByRole("button", { name: /archived runs/i }));

    await waitFor(() => {
      expect(screen.getAllByText("report.pdf").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByRole("button", { name: /archived runs/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /select run report\.pdf/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("navigates from the run library to review and profile settings without reopening a stored run", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await user.click(screen.getByRole("button", { name: /run library/i }));
    await screen.findByText("Run History");
    const runCreatesBeforeNavigation = vi.mocked(globalThis.fetch).mock.calls.filter(([url]) => url === "/api/runs").length;
    const reopenCallsBeforeNavigation = vi
      .mocked(globalThis.fetch)
      .mock.calls.filter(([url]) => url === "/api/runs/processing-run-1/reopen").length;

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    expect(vi.mocked(globalThis.fetch).mock.calls.filter(([url]) => url === "/api/runs")).toHaveLength(
      runCreatesBeforeNavigation,
    );
    expect(vi.mocked(globalThis.fetch).mock.calls.filter(([url]) => url === "/api/runs/processing-run-1/reopen")).toHaveLength(
      reopenCallsBeforeNavigation,
    );

    await user.click(screen.getByRole("button", { name: /run library/i }));
    await screen.findByText("Run History");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    expect(await screen.findByRole("heading", { name: "Default Profile" })).toBeInTheDocument();
  });

  it("reopens latest reviewed state or previews original processed state from the run library", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply vendor/i }));
    expect(await screen.findByText(/applied vendor name vendor edited/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /run library/i }));
    await screen.findByText("Run History");

    await user.click(screen.getByRole("button", { name: /open latest reviewed state/i }));
    await screen.findByRole("heading", { name: "report.pdf" });
    await expandFamily(user, "Show Material");
    expect(screen.getAllByText("Vendor Edited").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /run library/i }));
    await user.click(screen.getByRole("button", { name: /open original processed state/i }));
    expect(await screen.findByText(/you are viewing the original processed state/i)).toBeInTheDocument();
    await expandFamily(user, "Show Material");
    expect(screen.queryByText("Vendor Edited")).not.toBeInTheDocument();
    expect(screen.getAllByText("Vendor A").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /continue from original processed state/i }));
    expect(await screen.findByText(/restored the original processed state as the latest working review revision/i)).toBeInTheDocument();
    expect(screen.queryByText(/you are viewing the original processed state/i)).not.toBeInTheDocument();
    await expandFamily(user, "Show Material");
    expect(screen.getAllByText("Vendor A").length).toBeGreaterThan(0);
  });

  it("uses run-bound classification dropdowns in the top action bar instead of sidebar review inputs", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await user.click(screen.getByRole("checkbox", { name: /select labor line/i }));

    const laborSelect = screen.getByRole("combobox", { name: /bulk labor classification/i });
    expect(screen.queryByText(/edit selected row/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/recap labor class/i)).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "103 Journeyman" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "103 Foreman" })).toBeInTheDocument();

    await user.selectOptions(laborSelect, "103 Foreman");
    await user.click(screen.getByRole("button", { name: /apply labor/i }));

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequest).toBeDefined();
    expect(JSON.parse(String(editRequest?.[1]?.body)).edits[0].changed_fields.recap_labor_classification).toBe(
      "103 Foreman",
    );
  });

  it("loads profile-specific classification option sets from the active review run", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await user.click(screen.getByRole("checkbox", { name: /select labor line/i }));

    expect(screen.getByRole("option", { name: "ALT Journeyman" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "103 Journeyman" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "ALT Truck" })).toBeInTheDocument();
  });

  it("bulk applies one vendor name across selected vendor rows", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Shared Vendor");
    await user.click(screen.getByRole("button", { name: /apply vendor/i }));

    expect(await screen.findByText(/applied vendor name shared vendor to 2 selected rows/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests.length).toBeGreaterThan(0);
    const edits = JSON.parse(String(editRequests[editRequests.length - 1]?.[1]?.body)).edits;
    expect(edits).toHaveLength(2);
    expect(edits[0].changed_fields.vendor_name_normalized).toBe("Shared Vendor");
    expect(edits[1].changed_fields.vendor_name_normalized).toBe("Shared Vendor");
  });

  it("bulk applies one labor classification across selected labor rows", async () => {
    installFetchMock({
      initialReviewRecords: [
        ...buildBaseReviewRecords("default"),
        buildExtraLaborReviewRecord("default", "Helper labor line"),
      ],
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await user.click(screen.getByRole("checkbox", { name: /select labor line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select helper labor line/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /bulk labor classification/i }), "103 Foreman");
    await user.click(screen.getByRole("button", { name: /apply labor/i }));

    expect(await screen.findByText(/applied labor classification 103 foreman to 2 selected rows/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests.length).toBeGreaterThan(0);
    const edits = JSON.parse(String(editRequests[editRequests.length - 1]?.[1]?.body)).edits;
    expect(edits).toHaveLength(2);
    expect(edits[0].changed_fields.recap_labor_classification).toBe("103 Foreman");
    expect(edits[1].changed_fields.recap_labor_classification).toBe("103 Foreman");
  });

  it("bulk applies one equipment category across selected equipment rows", async () => {
    installFetchMock({
      initialReviewRecords: [
        ...buildBaseReviewRecords("default"),
        buildExtraEquipmentReviewRecord("Truck 1"),
        buildExtraEquipmentReviewRecord("Truck 2"),
      ],
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Equipment");
    await user.click(screen.getByRole("checkbox", { name: /select truck 1/i }));
    await user.click(screen.getByRole("checkbox", { name: /select truck 2/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /bulk equipment category/i }), "Pick-up Truck");
    await user.click(screen.getByRole("button", { name: /apply equipment/i }));

    expect(await screen.findByText(/applied equipment category pick-up truck to 2 selected rows/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests.length).toBeGreaterThan(0);
    const edits = JSON.parse(String(editRequests[editRequests.length - 1]?.[1]?.body)).edits;
    expect(edits).toHaveLength(2);
    expect(edits[0].changed_fields.equipment_category).toBe("Pick-up Truck");
    expect(edits[1].changed_fields.equipment_category).toBe("Pick-up Truck");
  });

  it("re-uploads a queued PDF automatically when the cached upload expires before rerun", async () => {
    installFetchMock({ expireCachedUploadOnSecondRun: true });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));

    expect(
      await screen.findByText(/cached upload for report\.pdf expired from temporary storage/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const uploadRequests = fetchCalls.filter(([url]) => url === "/api/source-documents/uploads");
    const runRequests = fetchCalls.filter(([url]) => url === "/api/runs");
    expect(uploadRequests).toHaveLength(2);
    expect(runRequests).toHaveLength(3);
  });

  it("uploads staged PDFs through Vercel Blob instead of the Python upload route when hosted uploads are enabled", async () => {
    vi.stubEnv("VITE_ENABLE_BLOB_CLIENT_UPLOADS", "true");
    installFetchMock();

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.upload(
      screen.getByLabelText(/source report pdf/i),
      new File(["pdf-bytes"], "report.pdf", { type: "application/pdf" }),
    );

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));

    await screen.findByRole("heading", { name: "report.pdf" });

    expect(uploadMock).toHaveBeenCalled();
    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url]) => url === "/api/source-documents/uploads")).toBe(false);
    expect(fetchCalls.some(([url]) => url === "/api/source-documents/blob-uploads")).toBe(true);
  });

  it("bulk omits and re-includes selected rows while keeping totals in sync", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.click(screen.getByRole("button", { name: /bulk omit/i }));

    expect(await screen.findByText(/bulk omit change to 2 rows/i)).toBeInTheDocument();
    expect(screen.getAllByText("$160.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$340.00").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.click(screen.getByRole("button", { name: /bulk include/i }));

    expect(await screen.findByText(/bulk include change to 2 rows/i)).toBeInTheDocument();
    expect(screen.getAllByText("$500.00").length).toBeGreaterThan(0);

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests).toHaveLength(2);
    expect(JSON.parse(String(editRequests[0]?.[1]?.body)).edits).toHaveLength(2);
    expect(JSON.parse(String(editRequests[1]?.[1]?.body)).edits).toHaveLength(2);
  });
});
