import type {
  ExportArtifactResponse,
  ProcessingRunDetailResponse,
  ProcessingRunResponse,
  ReviewEditDelta,
  ReviewSessionResponse,
  SourceUploadResponse,
  TrustedProfileResponse,
} from "./contracts";
import { resolveApiBaseUrl } from "../runtimeConfig";

const apiBaseUrl = resolveApiBaseUrl(import.meta.env);

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
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      detail = payload.detail;
    }
  } catch {
    if (response.statusText.trim()) {
      detail = response.statusText;
    }
  }
  throw new Error(detail);
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiRequest(path, init);
  return (await response.json()) as T;
}

function buildJsonRequest(body: unknown): RequestInit {
  return {
    method: "POST",
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
  const formData = new FormData();
  formData.append("file", file);
  return apiJson<SourceUploadResponse>("/api/source-documents/uploads", {
    method: "POST",
    body: formData,
  });
}

export async function fetchTrustedProfiles(): Promise<TrustedProfileResponse[]> {
  return apiJson<TrustedProfileResponse[]>("/api/trusted-profiles");
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

export async function downloadExportArtifact(downloadUrl: string): Promise<string> {
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
