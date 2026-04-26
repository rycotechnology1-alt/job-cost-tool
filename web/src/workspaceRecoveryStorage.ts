export const WORKSPACE_RECOVERY_STORAGE_KEY = "job-cost-tool:workspace-recovery:v1";

export type PersistedWorkspaceName = "review" | "library" | "settings";
export type PersistedReviewOrigin = "staged_upload" | "run_library";

export interface PersistedWorkspaceRecovery {
  activeWorkspace: PersistedWorkspaceName;
  selectedTrustedProfileName: string;
  activeProcessingRunId: string;
  loadedReviewOrigin: PersistedReviewOrigin | null;
  activeStagedReportId: string;
}

interface StoredWorkspaceRecovery extends PersistedWorkspaceRecovery {
  version: 1;
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

function normalizeWorkspaceName(value: unknown): PersistedWorkspaceName {
  return value === "library" || value === "settings" || value === "review" ? value : "review";
}

function normalizeReviewOrigin(value: unknown): PersistedReviewOrigin | null {
  return value === "staged_upload" || value === "run_library" ? value : null;
}

export function readPersistedWorkspaceRecovery(): PersistedWorkspaceRecovery {
  const fallback: PersistedWorkspaceRecovery = {
    activeWorkspace: "review",
    selectedTrustedProfileName: "",
    activeProcessingRunId: "",
    loadedReviewOrigin: null,
    activeStagedReportId: "",
  };
  const storage = browserStorage();
  if (!storage) {
    return fallback;
  }
  const rawPayload = storage.getItem(WORKSPACE_RECOVERY_STORAGE_KEY);
  if (!rawPayload) {
    return fallback;
  }

  let payload: unknown;
  try {
    payload = JSON.parse(rawPayload);
  } catch {
    storage.removeItem(WORKSPACE_RECOVERY_STORAGE_KEY);
    return fallback;
  }

  if (!isPlainObject(payload) || payload.version !== 1) {
    storage.removeItem(WORKSPACE_RECOVERY_STORAGE_KEY);
    return fallback;
  }

  return {
    activeWorkspace: normalizeWorkspaceName(payload.activeWorkspace),
    selectedTrustedProfileName:
      typeof payload.selectedTrustedProfileName === "string" ? payload.selectedTrustedProfileName.trim() : "",
    activeProcessingRunId:
      typeof payload.activeProcessingRunId === "string" ? payload.activeProcessingRunId.trim() : "",
    loadedReviewOrigin: normalizeReviewOrigin(payload.loadedReviewOrigin),
    activeStagedReportId:
      typeof payload.activeStagedReportId === "string" ? payload.activeStagedReportId.trim() : "",
  };
}

export function writePersistedWorkspaceRecovery(recovery: PersistedWorkspaceRecovery): void {
  const storage = browserStorage();
  if (!storage) {
    return;
  }
  const payload: StoredWorkspaceRecovery = {
    version: 1,
    activeWorkspace: recovery.activeWorkspace,
    selectedTrustedProfileName: recovery.selectedTrustedProfileName.trim(),
    activeProcessingRunId: recovery.activeProcessingRunId.trim(),
    loadedReviewOrigin: recovery.loadedReviewOrigin,
    activeStagedReportId: recovery.activeStagedReportId.trim(),
  };
  storage.setItem(WORKSPACE_RECOVERY_STORAGE_KEY, JSON.stringify(payload));
}
