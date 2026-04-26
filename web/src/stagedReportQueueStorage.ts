import type { SourceUploadResponse } from "./api/contracts";

export const STAGED_REPORTS_STORAGE_KEY = "job-cost-tool:staged-reports:v1";

export interface PersistedStagedReport {
  stagedReportId: string;
  filename: string;
  upload: SourceUploadResponse;
}

export interface RestoredStagedReportQueue {
  activeStagedReportId: string;
  reports: PersistedStagedReport[];
  expiredCount: number;
}

interface StoredStagedReportQueue {
  version: 1;
  activeStagedReportId: string;
  reports: PersistedStagedReport[];
}

function browserStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeUpload(value: unknown): SourceUploadResponse | null {
  if (!isPlainObject(value)) {
    return null;
  }
  const uploadId = typeof value.upload_id === "string" ? value.upload_id.trim() : "";
  const originalFilename = typeof value.original_filename === "string" ? value.original_filename.trim() : "";
  const contentType = typeof value.content_type === "string" ? value.content_type.trim() : "";
  const fileSizeBytes = typeof value.file_size_bytes === "number" ? value.file_size_bytes : 0;
  const storageRef = typeof value.storage_ref === "string" ? value.storage_ref.trim() : "";
  const expiresAt = typeof value.expires_at === "string" ? value.expires_at : null;
  if (!uploadId || !originalFilename || !contentType || fileSizeBytes <= 0 || !storageRef) {
    return null;
  }
  return {
    upload_id: uploadId,
    original_filename: originalFilename,
    content_type: contentType,
    file_size_bytes: fileSizeBytes,
    storage_ref: storageRef,
    expires_at: expiresAt,
  };
}

function normalizeReport(value: unknown): PersistedStagedReport | null {
  if (!isPlainObject(value)) {
    return null;
  }
  const stagedReportId = typeof value.stagedReportId === "string" ? value.stagedReportId.trim() : "";
  const filename = typeof value.filename === "string" ? value.filename.trim() : "";
  const upload = normalizeUpload(value.upload);
  if (!stagedReportId || !filename || !upload) {
    return null;
  }
  return {
    stagedReportId,
    filename,
    upload,
  };
}

export function isUploadExpired(upload: SourceUploadResponse, nowMs = Date.now()): boolean {
  if (!upload.expires_at) {
    return false;
  }
  const expiresAtMs = Date.parse(upload.expires_at);
  return Number.isFinite(expiresAtMs) && expiresAtMs <= nowMs;
}

function writeReports(
  reports: PersistedStagedReport[],
  activeStagedReportId: string,
  storage: Storage | null,
) {
  if (!storage) {
    return;
  }
  if (reports.length === 0) {
    storage.removeItem(STAGED_REPORTS_STORAGE_KEY);
    return;
  }
  const activeReport = reports.find((report) => report.stagedReportId === activeStagedReportId) ?? reports[0];
  const payload: StoredStagedReportQueue = {
    version: 1,
    activeStagedReportId: activeReport?.stagedReportId ?? "",
    reports,
  };
  storage.setItem(STAGED_REPORTS_STORAGE_KEY, JSON.stringify(payload));
}

export function readPersistedStagedReportQueue(nowMs = Date.now()): RestoredStagedReportQueue {
  const storage = browserStorage();
  if (!storage) {
    return { activeStagedReportId: "", reports: [], expiredCount: 0 };
  }
  const rawPayload = storage.getItem(STAGED_REPORTS_STORAGE_KEY);
  if (!rawPayload) {
    return { activeStagedReportId: "", reports: [], expiredCount: 0 };
  }

  let payload: unknown;
  try {
    payload = JSON.parse(rawPayload);
  } catch {
    storage.removeItem(STAGED_REPORTS_STORAGE_KEY);
    return { activeStagedReportId: "", reports: [], expiredCount: 0 };
  }

  if (!isPlainObject(payload) || !Array.isArray(payload.reports)) {
    storage.removeItem(STAGED_REPORTS_STORAGE_KEY);
    return { activeStagedReportId: "", reports: [], expiredCount: 0 };
  }

  const normalizedReports = payload.reports
    .map((report) => normalizeReport(report))
    .filter((report): report is PersistedStagedReport => Boolean(report));
  const freshReports = normalizedReports.filter((report) => !isUploadExpired(report.upload, nowMs));
  const expiredCount = normalizedReports.length - freshReports.length;
  const requestedActiveId = typeof payload.activeStagedReportId === "string" ? payload.activeStagedReportId : "";
  const activeReport =
    freshReports.find((report) => report.stagedReportId === requestedActiveId) ?? freshReports[0] ?? null;

  if (expiredCount > 0 || freshReports.length !== normalizedReports.length || activeReport?.stagedReportId !== requestedActiveId) {
    writeReports(freshReports, activeReport?.stagedReportId ?? "", storage);
  }

  return {
    activeStagedReportId: activeReport?.stagedReportId ?? "",
    reports: freshReports,
    expiredCount,
  };
}

export function writePersistedStagedReportQueue(
  reports: PersistedStagedReport[],
  activeStagedReportId: string,
): void {
  writeReports(reports, activeStagedReportId, browserStorage());
}
