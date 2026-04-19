import { upload } from "@vercel/blob/client";

import type {
  BlobUploadRegistrationRequest,
  ClassificationSlotRow,
  CreateTrustedProfileRequest,
  DefaultOmitRuleRow,
  DraftEditorStateResponse,
  EquipmentMappingRow,
  EquipmentRateRow,
  ExportSettingsResponse,
  ExportArtifactResponse,
  LaborMappingRow,
  LaborRateRow,
  ProcessingRunDetailResponse,
  ProcessingRunResponse,
  PublishedProfileDetailResponse,
  ReviewEditDelta,
  ReviewSessionResponse,
  SourceUploadResponse,
  TrustedProfileResponse,
} from "./contracts";
import { resolveApiBaseUrl } from "../runtimeConfig";

const apiBaseUrl = resolveApiBaseUrl(import.meta.env);

interface ApiErrorDetail {
  message?: unknown;
  error_code?: unknown;
  field_errors?: unknown;
}

export class ApiRequestError extends Error {
  status: number;
  errorCode?: string;
  fieldErrors: Record<string, string[]>;

  constructor(status: number, message: string, options?: { errorCode?: string; fieldErrors?: Record<string, string[]> }) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.errorCode = options?.errorCode;
    this.fieldErrors = options?.fieldErrors ?? {};
  }
}

function buildApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${apiBaseUrl}${path}`;
}

async function apiRequest(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(buildApiUrl(path), init);
  if (response.ok) {
    return response;
  }

  let detail = `Request failed with status ${response.status}.`;
  let errorCode: string | undefined;
  let fieldErrors: Record<string, string[]> = {};
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      detail = payload.detail;
    } else if (payload.detail && typeof payload.detail === "object") {
      const typedDetail = payload.detail as ApiErrorDetail;
      if (typeof typedDetail.message === "string" && typedDetail.message.trim()) {
        detail = typedDetail.message;
      }
      if (typeof typedDetail.error_code === "string" && typedDetail.error_code.trim()) {
        errorCode = typedDetail.error_code;
      }
      if (typedDetail.field_errors && typeof typedDetail.field_errors === "object") {
        fieldErrors = Object.fromEntries(
          Object.entries(typedDetail.field_errors as Record<string, unknown>).map(([key, value]) => [
            key,
            Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [],
          ]),
        );
      }
    }
  } catch {
    if (response.statusText.trim()) {
      detail = response.statusText;
    }
  }
  throw new ApiRequestError(response.status, detail, { errorCode, fieldErrors });
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiRequest(path, init);
  return (await response.json()) as T;
}

function buildJsonRequest(body: unknown, method = "POST"): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  };
}

function parseDownloadFilename(response: Response): string {
  const header = response.headers.get("content-disposition") ?? "";
  const match = header.match(/filename=\"?([^\"]+)\"?/i);
  return match?.[1] ?? "recap-export.xlsx";
}

export async function uploadSourceDocument(file: File): Promise<SourceUploadResponse> {
  if (import.meta.env.VITE_ENABLE_BLOB_CLIENT_UPLOADS === "true") {
    const pathname = `uploads/${crypto.randomUUID()}/${file.name}`;
    const blob = await upload(pathname, file, {
      access: "private",
      handleUploadUrl: "/api/blob-upload",
    });
    const registrationRequest: BlobUploadRegistrationRequest = {
      storage_ref: blob.pathname,
      original_filename: file.name,
      content_type: file.type || "application/pdf",
      file_size_bytes: file.size,
    };
    return apiJson<SourceUploadResponse>(
      "/api/source-documents/blob-uploads",
      buildJsonRequest(registrationRequest),
    );
  }

  const formData = new FormData();
  formData.append("file", file);
  return apiJson<SourceUploadResponse>("/api/source-documents/uploads", {
    method: "POST",
    body: formData,
  });
}

export async function fetchTrustedProfiles(includeArchived = false): Promise<TrustedProfileResponse[]> {
  const query = includeArchived ? "?include_archived=true" : "";
  return apiJson<TrustedProfileResponse[]>(`/api/trusted-profiles${query}`);
}

export async function fetchProfileDetail(
  trustedProfileId: string,
): Promise<PublishedProfileDetailResponse> {
  return apiJson<PublishedProfileDetailResponse>(`/api/profiles/${trustedProfileId}`);
}

export async function createTrustedProfile(
  request: CreateTrustedProfileRequest,
): Promise<PublishedProfileDetailResponse> {
  return apiJson<PublishedProfileDetailResponse>("/api/profiles", buildJsonRequest(request));
}

export async function archiveTrustedProfile(trustedProfileId: string): Promise<void> {
  await apiRequest(`/api/profiles/${trustedProfileId}/archive`, buildJsonRequest({}));
}

export async function unarchiveTrustedProfile(trustedProfileId: string): Promise<void> {
  await apiRequest(`/api/profiles/${trustedProfileId}/unarchive`, buildJsonRequest({}));
}

export async function createOrOpenProfileDraft(
  trustedProfileId: string,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profiles/${trustedProfileId}/draft`,
    buildJsonRequest({}),
  );
}

export async function fetchProfileDraft(
  trustedProfileDraftId: string,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(`/api/profile-drafts/${trustedProfileDraftId}`);
}

export async function discardProfileDraft(
  trustedProfileDraftId: string,
): Promise<void> {
  await apiRequest(`/api/profile-drafts/${trustedProfileDraftId}`, { method: "DELETE" });
}

export function discardProfileDraftBestEffort(trustedProfileDraftId: string): void {
  void fetch(buildApiUrl(`/api/profile-drafts/${trustedProfileDraftId}`), {
    method: "DELETE",
    keepalive: true,
  }).catch(() => undefined);
}

export async function updateDraftDefaultOmit(
  trustedProfileDraftId: string,
  defaultOmitRules: DefaultOmitRuleRow[],
  expectedDraftRevision: number,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/default-omit`,
    buildJsonRequest(
      { expected_draft_revision: expectedDraftRevision, default_omit_rules: defaultOmitRules },
      "PATCH",
    ),
  );
}

export async function updateDraftLaborMappings(
  trustedProfileDraftId: string,
  laborMappings: LaborMappingRow[],
  expectedDraftRevision: number,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/labor-mappings`,
    buildJsonRequest(
      { expected_draft_revision: expectedDraftRevision, labor_mappings: laborMappings },
      "PATCH",
    ),
  );
}

export async function updateDraftEquipmentMappings(
  trustedProfileDraftId: string,
  equipmentMappings: EquipmentMappingRow[],
  expectedDraftRevision: number,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/equipment-mappings`,
    buildJsonRequest(
      { expected_draft_revision: expectedDraftRevision, equipment_mappings: equipmentMappings },
      "PATCH",
    ),
  );
}

export async function updateDraftClassifications(
  trustedProfileDraftId: string,
  laborSlots: ClassificationSlotRow[],
  equipmentSlots: ClassificationSlotRow[],
  expectedDraftRevision: number,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/classifications`,
    buildJsonRequest(
      {
        expected_draft_revision: expectedDraftRevision,
        labor_slots: laborSlots,
        equipment_slots: equipmentSlots,
      },
      "PATCH",
    ),
  );
}

export async function updateDraftRates(
  trustedProfileDraftId: string,
  laborRates: LaborRateRow[],
  equipmentRates: EquipmentRateRow[],
  expectedDraftRevision: number,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/rates`,
    buildJsonRequest(
      {
        expected_draft_revision: expectedDraftRevision,
        labor_rates: laborRates,
        equipment_rates: equipmentRates,
      },
      "PATCH",
    ),
  );
}

export async function updateDraftExportSettings(
  trustedProfileDraftId: string,
  exportSettings: ExportSettingsResponse,
  expectedDraftRevision: number,
): Promise<DraftEditorStateResponse> {
  return apiJson<DraftEditorStateResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/export-settings`,
    buildJsonRequest(
      { expected_draft_revision: expectedDraftRevision, export_settings: exportSettings },
      "PATCH",
    ),
  );
}

export async function publishProfileDraft(
  trustedProfileDraftId: string,
  expectedDraftRevision: number,
): Promise<PublishedProfileDetailResponse> {
  return apiJson<PublishedProfileDetailResponse>(
    `/api/profile-drafts/${trustedProfileDraftId}/publish`,
    buildJsonRequest({ expected_draft_revision: expectedDraftRevision }),
  );
}

export async function createProcessingRun(
  uploadId: string,
  trustedProfileName: string,
): Promise<ProcessingRunResponse> {
  return apiJson<ProcessingRunResponse>(
    "/api/runs",
    buildJsonRequest({
      upload_id: uploadId,
      trusted_profile_name: trustedProfileName,
    }),
  );
}

export async function fetchProcessingRun(processingRunId: string): Promise<ProcessingRunDetailResponse> {
  return apiJson<ProcessingRunDetailResponse>(`/api/runs/${processingRunId}`);
}

export async function openReviewSession(processingRunId: string): Promise<ReviewSessionResponse> {
  return apiJson<ReviewSessionResponse>(`/api/runs/${processingRunId}/review-session`);
}

export async function appendReviewEdits(
  processingRunId: string,
  edits: ReviewEditDelta[],
): Promise<ReviewSessionResponse> {
  return apiJson<ReviewSessionResponse>(
    `/api/runs/${processingRunId}/review-session/edits`,
    buildJsonRequest({ edits }),
  );
}

export async function createExportArtifact(
  processingRunId: string,
  sessionRevision: number,
): Promise<ExportArtifactResponse> {
  return apiJson<ExportArtifactResponse>(
    `/api/runs/${processingRunId}/exports`,
    buildJsonRequest({ session_revision: sessionRevision }),
  );
}

export async function downloadArtifact(downloadUrl: string): Promise<string> {
  const response = await apiRequest(downloadUrl);
  const blob = await response.blob();
  const filename = parseDownloadFilename(response);
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
  return filename;
}

export async function downloadExportArtifact(downloadUrl: string): Promise<string> {
  return downloadArtifact(downloadUrl);
}
