import { useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  archiveProcessingRun,
  archiveTrustedProfile,
  appendReviewEdits,
  createTrustedProfile,
  createOrOpenProfileDraft,
  discardProfileDraft,
  discardProfileDraftBestEffort,
  createExportArtifact,
  createProcessingRun,
  downloadExportArtifact,
  fetchProfileDetail,
  fetchProfileDraft,
  listProcessingRuns,
  fetchTrustedProfiles,
  fetchProcessingRun,
  openReviewSession,
  publishProfileDraft,
  reopenProcessingRun,
  unarchiveTrustedProfile,
  updateDraftState,
  uploadSourceDocument,
} from "./api/client";
import type {
  CreateTrustedProfileRequest,
  DraftSaveRequest,
  DraftEditorStateResponse,
  ExportArtifactResponse,
  ProcessingRunResponse,
  ProcessingRunDetailResponse,
  PublishedProfileDetailResponse,
  ReviewEditFields,
  ReviewSessionResponse,
  SourceUploadResponse,
  TrustedProfileResponse,
} from "./api/contracts";
import {
  ProfileSettingsWorkspace,
  type ProfileSettingsLeaveGuard,
} from "./components/ProfileSettingsWorkspace";
import { RunLibraryWorkspace } from "./components/RunLibraryWorkspace";
import { ReviewWorkspace, type WorkspaceRow } from "./components/ReviewWorkspace";
import { UploadRunPanel } from "./components/UploadRunPanel";
import {
  readPersistedStagedReportQueue,
  writePersistedStagedReportQueue,
} from "./stagedReportQueueStorage";
import {
  readPersistedWorkspaceRecovery,
  writePersistedWorkspaceRecovery,
} from "./workspaceRecoveryStorage";

type DraftSyncReason =
  | "reset"
  | "profileSwitch"
  | "open"
  | "save"
  | "defaultOmit"
  | "laborMappings"
  | "equipmentMappings"
  | "classifications"
  | "exportSettings"
  | "rates";

interface DraftSyncToken {
  reason: DraftSyncReason;
  sequence: number;
}

interface LeaveSettingsPromptState {
  destination: "review" | "profile" | "library";
  nextProfileName?: string;
  nextProfileDisplayName?: string;
  dirtySections: string[];
  profileDisplayName: string;
}

interface StagedReportItem {
  stagedReportId: string;
  file: File | null;
  filename: string;
  upload: SourceUploadResponse | null;
  uploadStatus: "uploading" | "ready" | "failed" | "expired";
  uploadError: string;
}

const maxStagedReports = 10;

function buildStagedReportId(): string {
  return `staged-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeErrorMessage(error: unknown, fallbackMessage: string): string {
  return error instanceof Error ? error.message : fallbackMessage;
}

function buildWorkspaceRows(
  runDetail: ProcessingRunDetailResponse | null,
  reviewSession: ReviewSessionResponse | null,
): WorkspaceRow[] {
  if (!runDetail || !reviewSession) {
    return [];
  }
  return reviewSession.records.map((record, index) => {
    const runRecord = runDetail.run_records[index];
    return {
      recordKey: runRecord?.record_key ?? `row-${index}`,
      recordIndex: runRecord?.record_index ?? index,
      sourcePage: runRecord?.source_page ?? record.source_page,
      sourceLineText: runRecord?.source_line_text ?? record.source_line_text,
      canonicalRecord: runRecord?.canonical_record ?? {},
      record,
    };
  });
}

function isLaborBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType === "labor";
}

function isEquipmentBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType === "equipment";
}

function isVendorBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType !== "labor" && normalizedType !== "equipment";
}

export default function App() {
  const [initialWorkspaceRecovery] = useState(() => readPersistedWorkspaceRecovery());
  const [initialStagedReportQueue] = useState(() => readPersistedStagedReportQueue());
  const [activeWorkspace, setActiveWorkspace] = useState<"review" | "library" | "settings">(
    initialWorkspaceRecovery.activeWorkspace,
  );
  const [trustedProfiles, setTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [archivedTrustedProfiles, setArchivedTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [selectedTrustedProfileName, setSelectedTrustedProfileName] = useState(
    initialWorkspaceRecovery.selectedTrustedProfileName,
  );
  const [stagedReports, setStagedReports] = useState<StagedReportItem[]>(() =>
    initialStagedReportQueue.reports.map((report) => ({
      stagedReportId: report.stagedReportId,
      file: null,
      filename: report.filename,
      upload: report.upload,
      uploadStatus: "ready",
      uploadError: "",
    })),
  );
  const [activeStagedReportId, setActiveStagedReportId] = useState(
    initialStagedReportQueue.activeStagedReportId || initialWorkspaceRecovery.activeStagedReportId,
  );
  const [openRuns, setOpenRuns] = useState<ProcessingRunResponse[]>([]);
  const [archivedRuns, setArchivedRuns] = useState<ProcessingRunResponse[]>([]);
  const [runDetail, setRunDetail] = useState<ProcessingRunDetailResponse | null>(null);
  const [reviewSession, setReviewSession] = useState<ReviewSessionResponse | null>(null);
  const [profileDetail, setProfileDetail] = useState<PublishedProfileDetailResponse | null>(null);
  const [draftState, setDraftState] = useState<DraftEditorStateResponse | null>(null);
  const [draftSyncToken, setDraftSyncToken] = useState<DraftSyncToken>({ reason: "reset", sequence: 0 });
  const [selectedRecordKey, setSelectedRecordKey] = useState("");
  const [selectedReviewRecordKeys, setSelectedReviewRecordKeys] = useState<string[]>([]);
  const [exportArtifact, setExportArtifact] = useState<ExportArtifactResponse | null>(null);
  const [lastDownloadedFilename, setLastDownloadedFilename] = useState("");
  const [reviewContextInvalidationMessage, setReviewContextInvalidationMessage] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState(() => {
    if (initialStagedReportQueue.reports.length > 0) {
      const restoredCount = initialStagedReportQueue.reports.length;
      return `Restored ${restoredCount} staged report${restoredCount === 1 ? "" : "s"} from temporary browser recovery.`;
    }
    if (initialStagedReportQueue.expiredCount > 0) {
      const expiredCount = initialStagedReportQueue.expiredCount;
      return `Removed ${expiredCount} expired staged report${expiredCount === 1 ? "" : "s"} from temporary browser recovery.`;
    }
    return "Choose a trusted profile and stage one or more PDFs to start reviewing.";
  });
  const [runLibraryStatusMessage, setRunLibraryStatusMessage] = useState(
    "Browse open and archived runs, then reopen one in the review workspace when you want to keep working.",
  );
  const [settingsStatusMessage, setSettingsStatusMessage] = useState(
    "Inspect the live trusted profile and select Edit current profile when you are ready to make changes.",
  );
  const [settingsProfileDetailLoading, setSettingsProfileDetailLoading] = useState(false);
  const [settingsWorkspaceSession, setSettingsWorkspaceSession] = useState(0);
  const [leaveSettingsPrompt, setLeaveSettingsPrompt] = useState<LeaveSettingsPromptState | null>(null);
  const settingsLeaveGuardRef = useRef<ProfileSettingsLeaveGuard | null>(null);
  const pageExitCleanupDraftIdRef = useRef<string | null>(null);
  const draftStateRef = useRef<DraftEditorStateResponse | null>(null);
  const workspaceRestoreAttemptedRef = useRef(false);
  const recoveredProcessingRunIdRef = useRef(initialWorkspaceRecovery.activeProcessingRunId);
  const [loadedReviewOrigin, setLoadedReviewOrigin] = useState<"staged_upload" | "run_library" | null>(null);

  const selectedTrustedProfile =
    trustedProfiles.find((profile) => profile.profile_name === selectedTrustedProfileName) ?? null;
  const selectedTrustedProfileId = selectedTrustedProfile?.trusted_profile_id ?? "";
  const activeSettingsProfileDetail =
    profileDetail && profileDetail.trusted_profile_id === selectedTrustedProfileId ? profileDetail : null;
  const activeSettingsDraftState =
    draftState && draftState.trusted_profile_id === selectedTrustedProfileId ? draftState : null;
  const activeProfileDraftId =
    activeSettingsDraftState?.trusted_profile_draft_id ?? activeSettingsProfileDetail?.open_draft_id ?? null;
  const activeStagedReport =
    stagedReports.find((report) => report.stagedReportId === activeStagedReportId) ?? stagedReports[0] ?? null;
  const rows = buildWorkspaceRows(runDetail, reviewSession);
  const selectedRow = rows.find((row) => row.recordKey === selectedRecordKey) ?? null;
  const originalProcessedPreview = reviewSession?.effective_source_mode === "original_processed";
  const activeReviewProfileMismatch = Boolean(
    runDetail &&
      reviewSession &&
      !runDetail.is_archived &&
      selectedTrustedProfile &&
      (
        (runDetail.trusted_profile_id &&
          selectedTrustedProfile.trusted_profile_id &&
          runDetail.trusted_profile_id !== selectedTrustedProfile.trusted_profile_id) ||
        ((!runDetail.trusted_profile_id || !selectedTrustedProfile.trusted_profile_id) &&
          runDetail.trusted_profile_name &&
          runDetail.trusted_profile_name !== selectedTrustedProfile.profile_name)
      ),
  );
  const reviewExportInvalidated =
    originalProcessedPreview || Boolean(reviewContextInvalidationMessage) || activeReviewProfileMismatch;
  const activeReviewProfileLabel =
    runDetail?.trusted_profile_name ?? selectedTrustedProfile?.display_name ?? "the prior trusted profile";
  const reviewContextMessage =
    runDetail && reviewSession && reviewExportInvalidated
      ? activeReviewProfileMismatch
        ? `This loaded review was processed under ${activeReviewProfileLabel}, but the current trusted profile selection is ${selectedTrustedProfile?.display_name ?? "different"}. Reprocess under the selected profile before export is allowed.`
        : reviewContextInvalidationMessage
      : "";

  function advanceDraftSync(reason: DraftSyncReason) {
    setDraftSyncToken((current) => ({
      reason,
      sequence: current.sequence + 1,
    }));
  }

  useEffect(() => {
    draftStateRef.current = draftState;
  }, [draftState]);

  useEffect(() => {
    writePersistedStagedReportQueue(
      stagedReports
        .filter((report) => report.uploadStatus === "ready" && report.upload)
        .map((report) => ({
          stagedReportId: report.stagedReportId,
          filename: report.filename,
          upload: report.upload as SourceUploadResponse,
        })),
      activeStagedReportId,
    );
  }, [activeStagedReportId, stagedReports]);

  useEffect(() => {
    const activeProcessingRunId = runDetail?.processing_run_id ?? recoveredProcessingRunIdRef.current;
    writePersistedWorkspaceRecovery({
      activeWorkspace,
      selectedTrustedProfileName,
      activeProcessingRunId,
      loadedReviewOrigin,
      activeStagedReportId,
    });
  }, [activeStagedReportId, activeWorkspace, loadedReviewOrigin, runDetail, selectedTrustedProfileName]);

  function registerSettingsLeaveGuard(guard: ProfileSettingsLeaveGuard | null) {
    settingsLeaveGuardRef.current = guard;
  }

  function clearSettingsDraftView() {
    setDraftState(null);
  }

  function resetSettingsWorkspaceState(options?: { resetStatusMessage?: boolean }) {
    setProfileDetail(null);
    setDraftState(null);
    draftStateRef.current = null;
    setSettingsProfileDetailLoading(false);
    if (options?.resetStatusMessage) {
      setSettingsStatusMessage(
        "Inspect the live trusted profile and select Edit current profile when you are ready to make changes.",
      );
    }
  }

  function enterSettingsWorkspace() {
    resetSettingsWorkspaceState();
    setSettingsWorkspaceSession((current) => current + 1);
    advanceDraftSync("profileSwitch");
    setActiveWorkspace("settings");
    setErrorMessage("");
  }

  function completeSettingsProfileSwitch(nextProfileName: string) {
    if (!nextProfileName || nextProfileName === selectedTrustedProfileName) {
      return;
    }
    const nextProfile =
      trustedProfiles.find((profile) => profile.profile_name === nextProfileName) ?? null;
    setSelectedTrustedProfileName(nextProfileName);
    resetSettingsWorkspaceState();
    advanceDraftSync("profileSwitch");
    setSettingsStatusMessage(
      nextProfile
        ? `Loading published settings for ${nextProfile.display_name}.`
        : "Loading trusted profile settings.",
    );
  }

  function completeLeaveSettingsToWorkspace(nextWorkspace: "review" | "library") {
    resetSettingsWorkspaceState({ resetStatusMessage: true });
    setLeaveSettingsPrompt(null);
    setActiveWorkspace(nextWorkspace);
    setErrorMessage("");
  }

  function promptToLeaveSettings(
    destination: "review" | "profile" | "library",
    options?: { nextProfileName?: string; nextProfileDisplayName?: string },
  ) {
    const guard = settingsLeaveGuardRef.current;
    if (!guard || !guard.hasUnpublishedChanges) {
      setLeaveSettingsPrompt(null);
      if (destination === "review" || destination === "library") {
        completeLeaveSettingsToWorkspace(destination);
      } else if (options?.nextProfileName) {
        completeSettingsProfileSwitch(options.nextProfileName);
      }
      return;
    }
    setLeaveSettingsPrompt({
      destination,
      nextProfileName: options?.nextProfileName,
      nextProfileDisplayName: options?.nextProfileDisplayName,
      dirtySections: [...guard.dirtySections],
      profileDisplayName: guard.profileDisplayName,
    });
  }

  useEffect(() => {
    if (!activeProfileDraftId) {
      pageExitCleanupDraftIdRef.current = null;
    }
  }, [activeProfileDraftId]);

  useEffect(() => {
    if (!activeProfileDraftId) {
      return;
    }
    const draftId = activeProfileDraftId;

    function discardDraftOnPageExit() {
      if (pageExitCleanupDraftIdRef.current === draftId) {
        return;
      }
      pageExitCleanupDraftIdRef.current = draftId;
      discardProfileDraftBestEffort(draftId);
    }

    window.addEventListener("pagehide", discardDraftOnPageExit);
    window.addEventListener("beforeunload", discardDraftOnPageExit);
    return () => {
      window.removeEventListener("pagehide", discardDraftOnPageExit);
      window.removeEventListener("beforeunload", discardDraftOnPageExit);
    };
  }, [activeProfileDraftId]);

  async function loadSettingsProfileDetail(trustedProfileId: string): Promise<PublishedProfileDetailResponse> {
    return fetchProfileDetail(trustedProfileId);
  }

  async function loadSettingsProfileDetailWithRetry(trustedProfileId: string): Promise<PublishedProfileDetailResponse> {
    try {
      return await loadSettingsProfileDetail(trustedProfileId);
    } catch (error) {
      if (!(error instanceof ApiRequestError) || error.status < 500) {
        throw error;
      }
      return loadSettingsProfileDetail(trustedProfileId);
    }
  }

  function patchStagedReport(
    stagedReportId: string,
    patch: Partial<Pick<StagedReportItem, "upload" | "uploadStatus" | "uploadError">>,
  ) {
    setStagedReports((current) =>
      current.map((report) =>
        report.stagedReportId === stagedReportId
          ? {
              ...report,
              ...patch,
            }
          : report,
      ),
    );
  }

  async function uploadStagedReportFile(stagedReportId: string, file: File): Promise<SourceUploadResponse> {
    patchStagedReport(stagedReportId, {
      upload: null,
      uploadStatus: "uploading",
      uploadError: "",
    });
    try {
      const upload = await uploadSourceDocument(file);
      patchStagedReport(stagedReportId, {
        upload,
        uploadStatus: "ready",
        uploadError: "",
      });
      return upload;
    } catch (error) {
      const message = normalizeErrorMessage(error, `Failed to upload ${file.name}.`);
      patchStagedReport(stagedReportId, {
        upload: null,
        uploadStatus: "failed",
        uploadError: message,
      });
      throw new Error(message);
    }
  }

  function handleStageFiles(files: File[]) {
    const pdfFiles = files.filter(
      (file) => file.type === "application/pdf" || file.name.toLocaleLowerCase().endsWith(".pdf"),
    );

    if (pdfFiles.length === 0) {
      return;
    }

    const remainingSlots = Math.max(0, maxStagedReports - stagedReports.length);
    const acceptedFiles = pdfFiles.slice(0, remainingSlots);
    const nextReports = acceptedFiles.map((file) => ({
      stagedReportId: buildStagedReportId(),
      file,
      filename: file.name,
      upload: null,
      uploadStatus: "uploading" as const,
      uploadError: "",
    }));
    const acceptedCount = nextReports.length;
    const ignoredCount = pdfFiles.length - acceptedCount;

    setStagedReports((current) => [...current, ...nextReports]);
    if (!activeStagedReportId && nextReports.length > 0) {
      setActiveStagedReportId(nextReports[0].stagedReportId);
    }
    setErrorMessage("");

    if (acceptedCount === 0) {
      setStatusMessage("The staged review queue already holds 10 PDFs. Remove one before adding more.");
      return;
    }

    setStatusMessage(
      ignoredCount > 0
        ? `Staged ${acceptedCount} report${acceptedCount === 1 ? "" : "s"}. The queue holds up to 10 PDFs, so ${ignoredCount} additional file${ignoredCount === 1 ? " was" : "s were"} ignored.`
        : `Staged ${acceptedCount} report${acceptedCount === 1 ? "" : "s"} for review and started temporary upload for browser recovery.`,
    );

    nextReports.forEach((report) => {
      if (!report.file) {
        return;
      }
      void uploadStagedReportFile(report.stagedReportId, report.file).catch((error) => {
        setErrorMessage(
          `Upload failed for ${report.filename}: ${normalizeErrorMessage(error, "Unexpected upload error.")}`,
        );
      });
    });
  }

  function handleSelectStagedReport(stagedReportId: string) {
    if (!stagedReportId || stagedReportId === activeStagedReportId) {
      return;
    }
    const nextReport = stagedReports.find((report) => report.stagedReportId === stagedReportId) ?? null;
    setActiveStagedReportId(stagedReportId);
    setErrorMessage("");
    if (loadedReviewOrigin !== "staged_upload" || !runDetail || !reviewSession || !nextReport) {
      return;
    }
    setReviewContextInvalidationMessage(
      `Staged source PDF changed to ${nextReport.filename}. The loaded review is still showing ${runDetail.source_document_filename} and must be reprocessed before export is allowed.`,
    );
    setExportArtifact(null);
    setLastDownloadedFilename("");
    setStatusMessage(
      `Selected staged report ${nextReport.filename}. Reprocess before export because the loaded review still reflects ${runDetail.source_document_filename}.`,
    );
  }

  function handleRemoveStagedReport(stagedReportId: string) {
    const remaining = stagedReports.filter((report) => report.stagedReportId !== stagedReportId);
    const nextActiveReport =
      activeStagedReportId === stagedReportId
        ? remaining[0] ?? null
        : remaining.find((report) => report.stagedReportId === activeStagedReportId) ?? null;
    setStagedReports(remaining);
    if (activeStagedReportId === stagedReportId) {
      setActiveStagedReportId(nextActiveReport?.stagedReportId ?? "");
    }
    setErrorMessage("");
    if (
      loadedReviewOrigin !== "staged_upload" ||
      !runDetail ||
      !reviewSession ||
      activeStagedReportId !== stagedReportId ||
      !nextActiveReport
    ) {
      return;
    }
    setReviewContextInvalidationMessage(
      `Staged source PDF changed to ${nextActiveReport.filename}. The loaded review is still showing ${runDetail.source_document_filename} and must be reprocessed before export is allowed.`,
    );
    setExportArtifact(null);
    setLastDownloadedFilename("");
    setStatusMessage(
      `Selected staged report ${nextActiveReport.filename}. Reprocess before export because the loaded review still reflects ${runDetail.source_document_filename}.`,
    );
  }

  function applyTrustedProfiles(profiles: TrustedProfileResponse[], preferredProfileName?: string) {
    setTrustedProfiles(profiles);
    setSelectedTrustedProfileName((current) => {
      if (preferredProfileName && profiles.some((profile) => profile.profile_name === preferredProfileName)) {
        return preferredProfileName;
      }
      const existingMatch = profiles.some((profile) => profile.profile_name === current);
      if (existingMatch) {
        return current;
      }
      const activeProfile = profiles.find((profile) => profile.is_active_profile);
      return activeProfile?.profile_name ?? profiles[0]?.profile_name ?? "";
    });
  }

  function patchTrustedProfileSummary(
    profileName: string,
    patch: Partial<TrustedProfileResponse>,
  ) {
    setTrustedProfiles((current) =>
      current.map((profile) =>
        profile.profile_name === profileName
          ? {
              ...profile,
              ...patch,
            }
          : profile,
      ),
    );
  }

  function applyArchivedTrustedProfiles(profiles: TrustedProfileResponse[]) {
    setArchivedTrustedProfiles(profiles.filter((profile) => Boolean(profile.archived_at)));
  }

  async function reloadTrustedProfiles(preferredProfileName?: string): Promise<TrustedProfileResponse[]> {
    const profiles = await fetchTrustedProfiles();
    applyTrustedProfiles(profiles, preferredProfileName);
    return profiles;
  }

  async function reloadArchivedTrustedProfiles(): Promise<TrustedProfileResponse[]> {
    const profiles = await fetchTrustedProfiles(true);
    applyArchivedTrustedProfiles(profiles);
    return profiles;
  }

  async function reloadSettingsTrustedProfiles(preferredProfileName?: string): Promise<TrustedProfileResponse[]> {
    const profiles = await reloadTrustedProfiles(preferredProfileName);
    await reloadArchivedTrustedProfiles();
    return profiles;
  }

  async function refreshRunLibrary() {
    const [nextOpenRuns, nextArchivedRuns] = await Promise.all([
      listProcessingRuns("open"),
      listProcessingRuns("archived"),
    ]);
    setOpenRuns(nextOpenRuns);
    setArchivedRuns(nextArchivedRuns);
  }

  useEffect(() => {
    let cancelled = false;

    async function loadTrustedProfiles() {
      try {
        const profiles = await fetchTrustedProfiles();
        if (cancelled) {
          return;
        }
        applyTrustedProfiles(profiles);
        if (profiles.length > 0) {
          setStatusMessage((current) =>
            initialStagedReportQueue.reports.length > 0 || initialStagedReportQueue.expiredCount > 0
              ? current
              : "Trusted profiles loaded.",
          );
        } else {
          setErrorMessage("No trusted profiles are available for phase-1 web processing.");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to load trusted profiles.");
      }
    }

    void loadTrustedProfiles();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (activeWorkspace !== "settings") {
      return;
    }

    let cancelled = false;

    async function loadArchivedProfiles() {
      try {
        const profiles = await fetchTrustedProfiles(true);
        if (cancelled) {
          return;
        }
        applyArchivedTrustedProfiles(profiles);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to load archived trusted profiles.");
      }
    }

    void loadArchivedProfiles();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace]);

  useEffect(() => {
    if (activeWorkspace !== "library") {
      return;
    }

    let cancelled = false;

    async function loadRunLibrary() {
      try {
        const [nextOpenRuns, nextArchivedRuns] = await Promise.all([
          listProcessingRuns("open"),
          listProcessingRuns("archived"),
        ]);
        if (cancelled) {
          return;
        }
        setOpenRuns(nextOpenRuns);
        setArchivedRuns(nextArchivedRuns);
        setRunLibraryStatusMessage(
          nextOpenRuns.length + nextArchivedRuns.length > 0
            ? "Run library loaded. Reopen a stored run in either latest reviewed or original processed mode."
            : "Run library loaded. Process a PDF to seed your first stored run.",
        );
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to load the run library.");
      }
    }

    void loadRunLibrary();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace]);

  useEffect(() => {
    if (activeWorkspace !== "settings") {
      setSettingsProfileDetailLoading(false);
      return;
    }

    setDraftState(null);
    if (!selectedTrustedProfile || !selectedTrustedProfileId) {
      setProfileDetail(null);
      setSettingsProfileDetailLoading(false);
      return;
    }

    let cancelled = false;
    setProfileDetail(null);
    setSettingsProfileDetailLoading(true);
    setErrorMessage("");
    const trustedProfileId = selectedTrustedProfileId;
    const selectedProfileName = selectedTrustedProfile.profile_name;

    async function loadProfileDetail() {
      try {
        if (cancelled) {
          return;
        }
        const detail = await loadSettingsProfileDetailWithRetry(trustedProfileId);
        if (cancelled) {
          return;
        }
        setProfileDetail(detail);
        setSettingsProfileDetailLoading(false);
        patchTrustedProfileSummary(selectedProfileName, {
          current_published_version_number: detail.current_published_version.version_number,
          has_open_draft: Boolean(detail.open_draft_id),
        });
        setSettingsStatusMessage(
          `Inspecting live version v${detail.current_published_version.version_number} for ${detail.display_name}.`,
        );
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSettingsProfileDetailLoading(false);
        setErrorMessage(error instanceof Error ? error.message : "Failed to load profile settings.");
      }
    }

    void loadProfileDetail();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, selectedTrustedProfileId]);

  useEffect(() => {
    if (workspaceRestoreAttemptedRef.current || trustedProfiles.length === 0) {
      return;
    }
    const processingRunId = initialWorkspaceRecovery.activeProcessingRunId;
    if (!processingRunId) {
      return;
    }

    workspaceRestoreAttemptedRef.current = true;
    let cancelled = false;

    async function restoreReviewWorkspace() {
      const recoveredProfileName = initialWorkspaceRecovery.selectedTrustedProfileName;
      if (recoveredProfileName && trustedProfiles.some((profile) => profile.profile_name === recoveredProfileName)) {
        setSelectedTrustedProfileName(recoveredProfileName);
      }

      try {
        const [nextRunDetail, nextReviewSession] = await Promise.all([
          fetchProcessingRun(processingRunId),
          openReviewSession(processingRunId),
        ]);
        if (cancelled) {
          return;
        }
        recoveredProcessingRunIdRef.current = processingRunId;
        setActiveWorkspace(initialWorkspaceRecovery.activeWorkspace);
        applyLoadedReviewWorkspace(
          nextRunDetail,
          nextReviewSession,
          `Restored ${nextRunDetail.source_document_filename} from the saved review workspace.`,
          { reviewOrigin: initialWorkspaceRecovery.loadedReviewOrigin ?? "run_library" },
        );
      } catch (error) {
        if (cancelled) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to restore the saved review workspace.");
      }
    }

    void restoreReviewWorkspace();
    return () => {
      cancelled = true;
    };
  }, [initialWorkspaceRecovery, trustedProfiles]);

  async function runAction(
    actionLabel: string,
    action: () => Promise<void>,
    options?: { rethrow?: boolean },
  ): Promise<boolean> {
    setBusyAction(actionLabel);
    setErrorMessage("");
    try {
      await action();
      return true;
    } catch (error) {
      const normalizedError = error instanceof Error ? error : new Error("Unexpected browser workflow error.");
      setErrorMessage(normalizedError.message);
      if (options?.rethrow) {
        throw normalizedError;
      }
      return false;
    } finally {
      setBusyAction(null);
    }
  }

  async function handleReloadSettingsProfileDetail() {
    await runAction("Reloading published profile detail...", async () => {
      if (!selectedTrustedProfile) {
        throw new Error("Choose a trusted profile before reloading profile settings.");
      }
      setSettingsProfileDetailLoading(true);
      try {
        const detail = await loadSettingsProfileDetailWithRetry(selectedTrustedProfile.trusted_profile_id);
        setProfileDetail(detail);
        patchTrustedProfileSummary(selectedTrustedProfile.profile_name, {
          current_published_version_number: detail.current_published_version.version_number,
          has_open_draft: Boolean(detail.open_draft_id),
        });
        setSettingsStatusMessage(
          `Inspecting live version v${detail.current_published_version.version_number} for ${detail.display_name}.`,
        );
      } finally {
        setSettingsProfileDetailLoading(false);
      }
    });
  }

  function handleSettingsTrustedProfileNameChange(nextProfileName: string) {
    if (!nextProfileName || nextProfileName === selectedTrustedProfileName) {
      return;
    }
    const nextProfile = trustedProfiles.find((profile) => profile.profile_name === nextProfileName) ?? null;
    promptToLeaveSettings("profile", {
      nextProfileName,
      nextProfileDisplayName: nextProfile?.display_name ?? nextProfileName,
    });
  }

  function selectRow(nextRows: WorkspaceRow[], recordKey: string | null, options?: { fallbackToFirst?: boolean }) {
    const preferred = recordKey ? nextRows.find((row) => row.recordKey === recordKey) ?? null : null;
    const row = preferred ?? (options?.fallbackToFirst ? nextRows[0] ?? null : null);
    setSelectedRecordKey(row?.recordKey ?? "");
  }

  async function loadReviewWorkspaceFromUpload(uploadToUse: SourceUploadResponse) {
    const createdRun = await createProcessingRun(uploadToUse.upload_id, selectedTrustedProfileName.trim());
    const nextRunDetail = await fetchProcessingRun(createdRun.processing_run_id);
    const nextReviewSession = await openReviewSession(createdRun.processing_run_id);
    return {
      nextRunDetail,
      nextReviewSession,
    };
  }

  function applyLoadedReviewWorkspace(
    nextRunDetail: ProcessingRunDetailResponse,
    nextReviewSession: ReviewSessionResponse,
    nextStatusMessage: string,
    options?: { reviewOrigin?: "staged_upload" | "run_library" },
  ) {
    const nextRows = buildWorkspaceRows(nextRunDetail, nextReviewSession);
    recoveredProcessingRunIdRef.current = nextRunDetail.processing_run_id;
    setRunDetail(nextRunDetail);
    setReviewSession(nextReviewSession);
    setLoadedReviewOrigin(options?.reviewOrigin ?? "staged_upload");
    setExportArtifact(null);
    setLastDownloadedFilename("");
    setReviewContextInvalidationMessage("");
    setSelectedReviewRecordKeys([]);
    selectRow(nextRows, null);
    setStatusMessage(nextStatusMessage);
  }

  async function handleLaunchReviewWorkspace() {
    await runAction("Opening review workspace...", async () => {
      if (!selectedTrustedProfileName.trim()) {
        throw new Error("Choose a trusted profile before opening the review workspace.");
      }

      const stagedReport = activeStagedReport;
      if (!stagedReport) {
        throw new Error("Stage at least one report PDF before opening the review workspace.");
      }

      let uploadToUse = stagedReport.upload;
      if (stagedReport.uploadStatus === "uploading") {
        throw new Error(`Wait for ${stagedReport.filename} to finish uploading before processing it.`);
      }
      if (!uploadToUse) {
        if (!stagedReport.file) {
          throw new Error(`Reselect ${stagedReport.filename} to stage it again before processing.`);
        }
        uploadToUse = await uploadStagedReportFile(stagedReport.stagedReportId, stagedReport.file);
      }

      try {
        const { nextRunDetail, nextReviewSession } = await loadReviewWorkspaceFromUpload(uploadToUse);
        applyLoadedReviewWorkspace(
          nextRunDetail,
          nextReviewSession,
          `Loaded ${nextReviewSession.records.length} review records from ${nextRunDetail.source_document_filename}.`,
          { reviewOrigin: "staged_upload" },
        );
      } catch (error) {
        const temporaryUploadUnavailable =
          error instanceof ApiRequestError && (error.status === 410 || (!stagedReport.file && error.status === 404));
        if (!temporaryUploadUnavailable) {
          throw error;
        }

        if (!stagedReport.file) {
          const message = `The temporary upload for ${stagedReport.filename} expired. Reselect ${stagedReport.filename} to stage it again before processing.`;
          patchStagedReport(stagedReport.stagedReportId, {
            upload: null,
            uploadStatus: "expired",
            uploadError: message,
          });
          throw new Error(message);
        }

        const refreshedUpload = await uploadStagedReportFile(stagedReport.stagedReportId, stagedReport.file);

        const { nextRunDetail, nextReviewSession } = await loadReviewWorkspaceFromUpload(refreshedUpload);
        applyLoadedReviewWorkspace(
          nextRunDetail,
          nextReviewSession,
          `The cached upload for ${stagedReport.filename} expired from temporary storage, so the queued PDF was uploaded again and reopened in review.`,
          { reviewOrigin: "staged_upload" },
        );
      }
    });
  }

  async function handleRefreshRunLibrary() {
    await runAction("Refreshing run library...", async () => {
      await refreshRunLibrary();
      setRunLibraryStatusMessage("Run library refreshed.");
    });
  }

  async function handleOpenLatestReviewedRun(run: ProcessingRunResponse) {
    await runAction("Reopening latest reviewed state...", async () => {
      const [nextRunDetail, nextReviewSession] = await Promise.all([
        fetchProcessingRun(run.processing_run_id),
        reopenProcessingRun(run.processing_run_id, {
          mode: "latest_reviewed",
        }),
      ]);
      setActiveWorkspace("review");
      applyLoadedReviewWorkspace(
        nextRunDetail,
        nextReviewSession,
        `Reopened the latest reviewed state for ${run.source_document_filename}.`,
        { reviewOrigin: "run_library" },
      );
    });
  }

  async function handleOpenOriginalProcessedRun(run: ProcessingRunResponse) {
    await runAction("Opening original processed state...", async () => {
      const [nextRunDetail, nextReviewSession] = await Promise.all([
        fetchProcessingRun(run.processing_run_id),
        reopenProcessingRun(run.processing_run_id, {
          mode: "original_processed",
        }),
      ]);
      setActiveWorkspace("review");
      applyLoadedReviewWorkspace(
        nextRunDetail,
        nextReviewSession,
        `Previewing the original processed state for ${run.source_document_filename}. Continue from it to make it the latest working review state.`,
        { reviewOrigin: "run_library" },
      );
    });
  }

  async function handleContinueFromOriginalProcessedState() {
    await runAction("Restoring original processed state...", async () => {
      if (!runDetail || !reviewSession) {
        throw new Error("Open a stored run before restoring its original processed state.");
      }
      const nextReviewSession = await reopenProcessingRun(runDetail.processing_run_id, {
        mode: "original_processed",
        continue_from_original: true,
        expected_current_revision: reviewSession.current_revision,
      });
      const nextRunDetail = await fetchProcessingRun(runDetail.processing_run_id);
      applyLoadedReviewWorkspace(
        nextRunDetail,
        nextReviewSession,
        "Restored the original processed state as the latest working review revision.",
        { reviewOrigin: "run_library" },
      );
    });
  }

  async function handleArchiveRun(run: ProcessingRunResponse) {
    await runAction("Archiving run...", async () => {
      await archiveProcessingRun(run.processing_run_id);
      await refreshRunLibrary();
      setRunLibraryStatusMessage(
        `Archived ${run.source_document_filename}. Archived runs stay reopenable but stop participating in live profile drift warnings.`,
      );
    });
  }

  function handleReviewTrustedProfileNameChange(nextProfileName: string) {
    if (!nextProfileName || nextProfileName === selectedTrustedProfileName) {
      return;
    }

    const nextProfile =
      trustedProfiles.find((profile) => profile.profile_name === nextProfileName) ?? null;
    const hasActiveReview = Boolean(runDetail && reviewSession);

    setSelectedTrustedProfileName(nextProfileName);
    setProfileDetail(null);
    setDraftState(null);
    draftStateRef.current = null;
    setSettingsProfileDetailLoading(false);
    advanceDraftSync("profileSwitch");

    if (!hasActiveReview || runDetail?.is_archived) {
      return;
    }

    setReviewContextInvalidationMessage(
      `This loaded review was processed under ${activeReviewProfileLabel}, and the trusted profile selection changed afterward. This review is now stale for export and must be reprocessed before export is allowed.`,
    );
    setExportArtifact(null);
    setLastDownloadedFilename("");
    setStatusMessage(
      `Profile selection changed to ${nextProfile?.display_name ?? nextProfileName}. The loaded review was processed under ${activeReviewProfileLabel} and must be reprocessed before export is allowed.`,
    );
  }

  function handleReviewRowSelectionChange(recordKey: string, isSelected: boolean) {
    setSelectedReviewRecordKeys((current) => {
      if (isSelected) {
        if (current.includes(recordKey)) {
          return current;
        }
        return [...current, recordKey];
      }
      return current.filter((key) => key !== recordKey);
    });
  }

  function handleActivateReviewRow(recordKey: string) {
    const isCurrentlySelected = selectedReviewRecordKeys.includes(recordKey);
    handleReviewRowSelectionChange(recordKey, !isCurrentlySelected);
    setSelectedRecordKey(isCurrentlySelected ? "" : recordKey);
  }

  async function handleApplyBulkOmission(nextOmissionState: boolean) {
    await runAction(
      nextOmissionState ? "Bulk omitting review rows..." : "Bulk including review rows...",
      async () => {
        if (!runDetail || !reviewSession) {
          throw new Error("Open the review workspace before applying a bulk omission change.");
        }

        const selectedRows = rows.filter((row) => selectedReviewRecordKeys.includes(row.recordKey));
        if (selectedRows.length === 0) {
          throw new Error("Select at least one review row before applying a bulk omission change.");
        }

        const applicableRows = selectedRows.filter((row) => row.record.is_omitted !== nextOmissionState);
        if (applicableRows.length === 0) {
          throw new Error(
            nextOmissionState
              ? "Select at least one currently included row before bulk omitting."
              : "Select at least one currently omitted row before bulk including.",
          );
        }

        const nextReviewSession = await appendReviewEdits(
          runDetail.processing_run_id,
          applicableRows.map((row) => ({
            record_key: row.recordKey,
            changed_fields: {
              is_omitted: nextOmissionState,
            },
          })),
        );
        const nextRows = buildWorkspaceRows(runDetail, nextReviewSession);
        const preferredSelectedRecordKey =
          selectedRow && nextRows.some((row) => row.recordKey === selectedRow.recordKey)
            ? selectedRow.recordKey
            : applicableRows[0]?.recordKey ?? null;

        setReviewSession(nextReviewSession);
        setExportArtifact(null);
        setLastDownloadedFilename("");
        setSelectedReviewRecordKeys([]);
        selectRow(nextRows, preferredSelectedRecordKey);
        setStatusMessage(
          `Applied a bulk ${nextOmissionState ? "omit" : "include"} change to ${applicableRows.length} row${applicableRows.length === 1 ? "" : "s"} and advanced the session to revision ${nextReviewSession.current_revision}.`,
        );
      },
    );
  }

  async function handleApplyBulkVendorName(vendorName: string) {
    const nextVendorName = vendorName.trim();
    await runAction("Applying vendor name...", async () => {
      if (!runDetail || !reviewSession) {
        throw new Error("Open the review workspace before applying a vendor name.");
      }
      if (!nextVendorName) {
        throw new Error("Enter a vendor name before applying a review change.");
      }

      const selectedRows = rows.filter((row) => selectedReviewRecordKeys.includes(row.recordKey));
      if (selectedRows.length === 0) {
        throw new Error("Select at least one review row before applying a vendor name.");
      }
      if (!selectedRows.every(isVendorBulkCompatibleRow)) {
        throw new Error("Vendor name editing only works when every selected row is a vendor row.");
      }

      const applicableRows = selectedRows.filter(
        (row) => (row.record.vendor_name_normalized ?? row.record.vendor_name ?? "").trim() !== nextVendorName,
      );
      if (applicableRows.length === 0) {
        throw new Error("The selected vendor rows already use that vendor name.");
      }

      const nextReviewSession = await appendReviewEdits(
        runDetail.processing_run_id,
        applicableRows.map((row) => ({
          record_key: row.recordKey,
          changed_fields: {
            vendor_name_normalized: nextVendorName,
          } satisfies ReviewEditFields,
        })),
      );
      const nextRows = buildWorkspaceRows(runDetail, nextReviewSession);
      const preferredSelectedRecordKey =
        selectedRow && nextRows.some((row) => row.recordKey === selectedRow.recordKey)
          ? selectedRow.recordKey
          : applicableRows[0]?.recordKey ?? null;

      setReviewSession(nextReviewSession);
      setExportArtifact(null);
      setLastDownloadedFilename("");
      setSelectedReviewRecordKeys([]);
      selectRow(nextRows, preferredSelectedRecordKey);
      setStatusMessage(
        `Applied vendor name ${nextVendorName} to ${applicableRows.length} selected row${applicableRows.length === 1 ? "" : "s"} and advanced the session to revision ${nextReviewSession.current_revision}.`,
      );
    });
  }

  async function handleApplyBulkLaborClassification(targetClassification: string) {
    const nextTarget = targetClassification.trim();
    await runAction("Applying bulk labor classification...", async () => {
      if (!runDetail || !reviewSession) {
        throw new Error("Open the review workspace before applying a bulk labor classification.");
      }
      if (!nextTarget) {
        throw new Error("Choose a labor classification before applying a bulk review change.");
      }

      const selectedRows = rows.filter((row) => selectedReviewRecordKeys.includes(row.recordKey));
      if (selectedRows.length === 0) {
        throw new Error("Select at least one review row before applying a bulk labor classification.");
      }
      if (!selectedRows.every(isLaborBulkCompatibleRow)) {
        throw new Error("Bulk labor classification only works when every selected row is a labor row.");
      }

      const applicableRows = selectedRows.filter(
        (row) => (row.record.recap_labor_classification ?? "").trim() !== nextTarget,
      );
      if (applicableRows.length === 0) {
        throw new Error("The selected labor rows already use that classification.");
      }

      const nextReviewSession = await appendReviewEdits(
        runDetail.processing_run_id,
        applicableRows.map((row) => ({
          record_key: row.recordKey,
          changed_fields: {
            recap_labor_classification: nextTarget,
          },
        })),
      );
      const nextRows = buildWorkspaceRows(runDetail, nextReviewSession);
      const preferredSelectedRecordKey =
        selectedRow && nextRows.some((row) => row.recordKey === selectedRow.recordKey)
          ? selectedRow.recordKey
          : applicableRows[0]?.recordKey ?? null;

      setReviewSession(nextReviewSession);
      setExportArtifact(null);
      setLastDownloadedFilename("");
      setSelectedReviewRecordKeys([]);
      selectRow(nextRows, preferredSelectedRecordKey);
      setStatusMessage(
        `Applied labor classification ${nextTarget} to ${applicableRows.length} selected row${applicableRows.length === 1 ? "" : "s"} and advanced the session to revision ${nextReviewSession.current_revision}.`,
      );
    });
  }

  async function handleApplyBulkEquipmentCategory(targetCategory: string) {
    const nextTarget = targetCategory.trim();
    await runAction("Applying bulk equipment category...", async () => {
      if (!runDetail || !reviewSession) {
        throw new Error("Open the review workspace before applying a bulk equipment category.");
      }
      if (!nextTarget) {
        throw new Error("Choose an equipment category before applying a bulk review change.");
      }

      const selectedRows = rows.filter((row) => selectedReviewRecordKeys.includes(row.recordKey));
      if (selectedRows.length === 0) {
        throw new Error("Select at least one review row before applying a bulk equipment category.");
      }
      if (!selectedRows.every(isEquipmentBulkCompatibleRow)) {
        throw new Error("Bulk equipment category only works when every selected row is an equipment row.");
      }

      const applicableRows = selectedRows.filter((row) => (row.record.equipment_category ?? "").trim() !== nextTarget);
      if (applicableRows.length === 0) {
        throw new Error("The selected equipment rows already use that category.");
      }

      const nextReviewSession = await appendReviewEdits(
        runDetail.processing_run_id,
        applicableRows.map((row) => ({
          record_key: row.recordKey,
          changed_fields: {
            equipment_category: nextTarget,
          },
        })),
      );
      const nextRows = buildWorkspaceRows(runDetail, nextReviewSession);
      const preferredSelectedRecordKey =
        selectedRow && nextRows.some((row) => row.recordKey === selectedRow.recordKey)
          ? selectedRow.recordKey
          : applicableRows[0]?.recordKey ?? null;

      setReviewSession(nextReviewSession);
      setExportArtifact(null);
      setLastDownloadedFilename("");
      setSelectedReviewRecordKeys([]);
      selectRow(nextRows, preferredSelectedRecordKey);
      setStatusMessage(
        `Applied equipment category ${nextTarget} to ${applicableRows.length} selected row${applicableRows.length === 1 ? "" : "s"} and advanced the session to revision ${nextReviewSession.current_revision}.`,
      );
    });
  }

  async function handleExportAndDownload() {
    await runAction("Exporting workbook...", async () => {
      if (!runDetail || !reviewSession) {
        throw new Error("Open the review workspace before exporting a workbook.");
      }
      if (reviewExportInvalidated) {
        throw new Error(reviewContextMessage || "This loaded review is stale for export. Reprocess it first.");
      }

      const artifact = await createExportArtifact(runDetail.processing_run_id, reviewSession.current_revision);
      const filename = await downloadExportArtifact(artifact.download_url);
      setExportArtifact(artifact);
      setLastDownloadedFilename(filename);
      setStatusMessage(`Downloaded ${filename} from review revision ${artifact.session_revision}.`);
    });
  }

  async function handleOpenSettingsDraft() {
    await runAction("Opening current profile editor...", async () => {
      if (!selectedTrustedProfile) {
        throw new Error("Choose a trusted profile before editing the current profile.");
      }
      if (settingsProfileDetailLoading || !activeSettingsProfileDetail) {
        throw new Error("Wait for the selected live profile to finish loading before editing the current profile.");
      }

      let usedFallbackCreate = false;
      let draft: DraftEditorStateResponse;
      if (activeSettingsProfileDetail.open_draft_id) {
        try {
          draft = await fetchProfileDraft(activeSettingsProfileDetail.open_draft_id);
        } catch (error) {
          if (!(error instanceof ApiRequestError) || error.status !== 404) {
            throw error;
          }
          draft = await createOrOpenProfileDraft(selectedTrustedProfile.trusted_profile_id);
          usedFallbackCreate = true;
        }
      } else {
        draft = await createOrOpenProfileDraft(selectedTrustedProfile.trusted_profile_id);
      }
      setDraftState(draft);
      advanceDraftSync("open");
      setProfileDetail((current) =>
        current && current.trusted_profile_id === draft.trusted_profile_id
          ? {
              ...current,
              open_draft_id: draft.trusted_profile_draft_id,
            }
          : current,
      );
      patchTrustedProfileSummary(selectedTrustedProfile.profile_name, {
        has_open_draft: true,
      });
      setSettingsStatusMessage(
        usedFallbackCreate
          ? `Recovered a missing unpublished-change link and continued editing ${draft.display_name}.`
          : `Editing current profile settings for ${draft.display_name}.`,
      );
    });
  }

  async function handleSaveDraftState(request: Omit<DraftSaveRequest, "expected_draft_revision">): Promise<boolean> {
    return runAction("Saving profile settings...", async () => {
      const currentDraft = draftStateRef.current;
      if (!currentDraft) {
        throw new Error("Edit the current profile before saving profile settings.");
      }
      const nextDraft = await updateDraftState(currentDraft.trusted_profile_draft_id, {
        ...request,
        expected_draft_revision: currentDraft.draft_revision,
      });
      draftStateRef.current = nextDraft;
      setDraftState(nextDraft);
      advanceDraftSync("save");
      setSettingsStatusMessage("Saved profile settings into the current unpublished profile changes.");
    });
  }

  async function handleDiscardProfileDraft(trustedProfileDraftId: string): Promise<boolean> {
    return runAction("Discarding profile changes...", async () => {
      await discardProfileDraft(trustedProfileDraftId);
      clearSettingsDraftView();
      advanceDraftSync("reset");
      setProfileDetail((current) =>
        current
          ? {
              ...current,
              open_draft_id: null,
            }
          : current,
      );
      if (selectedTrustedProfile) {
        patchTrustedProfileSummary(selectedTrustedProfile.profile_name, {
          has_open_draft: false,
        });
      }
      setSettingsStatusMessage("Discarded unpublished profile changes. Live profile settings remain unchanged.");
    });
  }

  async function handlePublishDraft(trustedProfileDraftId?: string): Promise<boolean> {
    return runAction("Saving and publishing profile settings...", async () => {
      const currentDraft = draftStateRef.current;
      const draftIdToPublish = trustedProfileDraftId ?? currentDraft?.trusted_profile_draft_id;
      if (!draftIdToPublish || !currentDraft || currentDraft.trusted_profile_draft_id !== draftIdToPublish) {
        throw new Error("Edit the current profile before saving profile settings.");
      }

      const publishedDetail = await publishProfileDraft(draftIdToPublish, currentDraft.draft_revision);
      draftStateRef.current = null;
      setDraftState(null);
      advanceDraftSync("reset");

      let refreshedDetail = publishedDetail;
      let refreshConfirmed = false;
      if (selectedTrustedProfile) {
        try {
          refreshedDetail = await fetchProfileDetail(selectedTrustedProfile.trusted_profile_id);
          refreshConfirmed = true;
        } catch {
          refreshConfirmed = false;
        }
      }
      setProfileDetail(refreshedDetail);
      if (selectedTrustedProfile) {
        patchTrustedProfileSummary(selectedTrustedProfile.profile_name, {
          current_published_version_number: refreshedDetail.current_published_version.version_number,
          has_open_draft: false,
        });
      }
      if (runDetail && reviewSession && !runDetail.is_archived) {
        setReviewContextInvalidationMessage(
          "Profile settings were saved after this review was processed. Reprocess before export is allowed.",
        );
        setExportArtifact(null);
        setLastDownloadedFilename("");
        setStatusMessage(
          `Profile settings were saved for ${refreshedDetail.display_name}. The loaded review must be reprocessed before export is allowed.`,
        );
      }
      setSettingsStatusMessage(
        refreshConfirmed
          ? `Saved profile settings and published live version v${refreshedDetail.current_published_version.version_number} for ${refreshedDetail.display_name}.`
          : `Saved profile settings and published live version v${publishedDetail.current_published_version.version_number} for ${publishedDetail.display_name}. The summary is showing the publish response until the next reload.`,
      );
    });
  }

  async function handleCreateTrustedProfile(request: CreateTrustedProfileRequest) {
    await runAction("Creating trusted profile...", async () => {
      const seedProfile = selectedTrustedProfile;
      if (!seedProfile) {
        throw new Error("Choose a seed trusted profile before creating another profile.");
      }
      const seedVersionNumber =
        profileDetail?.current_published_version.version_number ??
        seedProfile.current_published_version_number ??
        1;

      const createdDetail = await createTrustedProfile({
        ...request,
        seed_trusted_profile_id: seedProfile.trusted_profile_id,
      });
      await reloadSettingsTrustedProfiles(createdDetail.profile_name);
      setSelectedTrustedProfileName(createdDetail.profile_name);
      setDraftState(null);
      setProfileDetail(createdDetail);
      advanceDraftSync("reset");
      setSettingsStatusMessage(
        `Created ${createdDetail.display_name} from live version v${seedVersionNumber} of ${seedProfile.display_name}. Select Edit current profile when you are ready to change it.`,
      );
    }, { rethrow: true });
  }

  async function handleArchiveTrustedProfile() {
    await runAction("Archiving trusted profile...", async () => {
      if (!selectedTrustedProfile || !profileDetail) {
        throw new Error("Load a trusted profile before archiving it.");
      }
      await archiveTrustedProfile(selectedTrustedProfile.trusted_profile_id);
      const archivedDisplayName = profileDetail.display_name;
      const profiles = await reloadSettingsTrustedProfiles();
      const fallbackProfileName =
        profiles.find((profile) => profile.is_active_profile)?.profile_name ?? profiles[0]?.profile_name ?? "";
      setSelectedTrustedProfileName(fallbackProfileName);
      setDraftState(null);
      setProfileDetail(null);
      advanceDraftSync("reset");
      setSettingsStatusMessage(
        `Archived ${archivedDisplayName}. Archived profiles stay in lineage history but are removed from active web selectors.`,
      );
    });
  }

  async function handleUnarchiveTrustedProfile(trustedProfileId: string, displayName: string) {
    await runAction("Restoring trusted profile...", async () => {
      await unarchiveTrustedProfile(trustedProfileId);
      await reloadSettingsTrustedProfiles();
      setSettingsStatusMessage(
        `Restored ${displayName} to the active trusted profile lists. It remains non-processable until you explicitly select it for future review work.`,
      );
    });
  }

  function handleStayOnSettings() {
    setLeaveSettingsPrompt(null);
  }

  async function handleSaveAndLeaveSettings() {
    const prompt = leaveSettingsPrompt;
    const guard = settingsLeaveGuardRef.current;
    if (!prompt || !guard) {
      setLeaveSettingsPrompt(null);
      return;
    }
    const saved = await guard.saveAllDirtySections();
    if (!saved) {
      setLeaveSettingsPrompt(null);
      setErrorMessage((current) => current || "Could not save the profile changes. Review the highlighted sections and try again.");
      return;
    }
    const published = await handlePublishDraft(guard.draftId ?? undefined);
    if (!published) {
      setLeaveSettingsPrompt(null);
      setErrorMessage((current) => current || "Could not save profile settings. The live profile was not updated.");
      return;
    }
    if (prompt.destination === "review" || prompt.destination === "library") {
      completeLeaveSettingsToWorkspace(prompt.destination);
      return;
    }
    setLeaveSettingsPrompt(null);
    if (prompt.nextProfileName) {
      completeSettingsProfileSwitch(prompt.nextProfileName);
    }
  }

  async function handleDiscardAndLeaveSettings() {
    const prompt = leaveSettingsPrompt;
    const guard = settingsLeaveGuardRef.current;
    if (!prompt || !guard) {
      setLeaveSettingsPrompt(null);
      return;
    }
    const discarded = await guard.discardCurrentDraft();
    if (!discarded) {
      setLeaveSettingsPrompt(null);
      setErrorMessage((current) => current || "Could not discard the unpublished profile changes. Try again from profile settings.");
      return;
    }
    if (prompt.destination === "review" || prompt.destination === "library") {
      completeLeaveSettingsToWorkspace(prompt.destination);
      return;
    }
    setLeaveSettingsPrompt(null);
    if (prompt.nextProfileName) {
      completeSettingsProfileSwitch(prompt.nextProfileName);
    }
  }

  const busy = busyAction !== null;
  const currentWorkspaceStatusMessage =
    activeWorkspace === "settings"
      ? settingsStatusMessage
      : activeWorkspace === "library"
        ? runLibraryStatusMessage
        : statusMessage;
  const currentWorkspaceTitle =
    activeWorkspace === "settings"
      ? "Profile Settings Workspace"
      : activeWorkspace === "library"
        ? "Run Library"
        : "Job Cost Review Workspace";
  const currentWorkspaceEyebrow =
    activeWorkspace === "settings"
      ? "Phase 2A Settings"
      : activeWorkspace === "library"
        ? "Stored Run History"
        : "Phase 1 Pilot Review";
  const currentWorkspaceCopy =
    activeWorkspace === "settings"
      ? "The browser remains a thin client. Live profile versions and save rules still come from the backend authoring services."
      : activeWorkspace === "library"
        ? "Stored processing runs, review revisions, and export history stay durable so operators can reopen prior work without the original PDF."
        : "The browser stays thin. Processing, review lineage, and exact-revision export still come from the accepted backend services.";
  const workspaceStatusCard = (
    <div className="status-card" aria-live="polite">
      <strong>{busyAction ?? "Workflow status"}</strong>
      <p>{busy ? busyAction : currentWorkspaceStatusMessage}</p>
      {activeWorkspace === "review" && runDetail ? (
        <p className="muted">Reviewing {runDetail.source_document_filename}</p>
      ) : null}
      {activeWorkspace === "library" ? (
        <p className="muted">
          Browsing {openRuns.length} open run{openRuns.length === 1 ? "" : "s"} and {archivedRuns.length} archived
          run{archivedRuns.length === 1 ? "" : "s"}.
        </p>
      ) : null}
      {activeWorkspace === "settings" && selectedTrustedProfile ? (
        <p className="muted">Editing profile {selectedTrustedProfile.display_name}</p>
      ) : null}
    </div>
  );
  const workspaceModeToggle = (
    <div
      className={
        activeWorkspace === "review"
          ? "workspace-toggle workspace-mode-toggle review-workspace-toggle"
          : activeWorkspace === "settings"
            ? "workspace-toggle workspace-mode-toggle settings-header-toggle"
            : "workspace-toggle workspace-mode-toggle"
      }
      aria-label="Workspace mode"
    >
      <button
        type="button"
        className={activeWorkspace === "review" ? "toggle-button active" : "toggle-button"}
        onClick={() => {
          if (activeWorkspace === "settings") {
            promptToLeaveSettings("review");
            return;
          }
          setActiveWorkspace("review");
          setErrorMessage("");
        }}
        aria-pressed={activeWorkspace === "review"}
      >
        Review workspace
      </button>
      <button
        type="button"
        className={activeWorkspace === "library" ? "toggle-button active" : "toggle-button"}
        onClick={() => {
          if (activeWorkspace === "settings") {
            promptToLeaveSettings("library");
            return;
          }
          setActiveWorkspace("library");
          setErrorMessage("");
        }}
        aria-pressed={activeWorkspace === "library"}
      >
        Run library
      </button>
      <button
        type="button"
        className={activeWorkspace === "settings" ? "toggle-button active" : "toggle-button"}
        onClick={() => {
          enterSettingsWorkspace();
        }}
        aria-pressed={activeWorkspace === "settings"}
      >
        Profile settings
      </button>
    </div>
  );

  return (
    <main
      className={
        activeWorkspace === "review"
          ? "app-shell app-shell-review"
          : activeWorkspace === "library"
            ? "app-shell app-shell-library"
          : activeWorkspace === "settings"
            ? "app-shell app-shell-settings"
            : "app-shell"
      }
    >
      <header
        className={
          activeWorkspace === "review"
            ? "hero compact-hero review-hero"
            : activeWorkspace === "library"
              ? "hero compact-hero library-hero"
            : activeWorkspace === "settings"
              ? "hero compact-hero settings-hero"
              : "hero compact-hero"
        }
      >
        <div>
          <p className="eyebrow">{currentWorkspaceEyebrow}</p>
          <h1>{currentWorkspaceTitle}</h1>
          <p className="hero-copy">{currentWorkspaceCopy}</p>
        </div>
        <div className="settings-hero-side">
          {workspaceModeToggle}
          {workspaceStatusCard}
        </div>
      </header>

      {errorMessage ? (
        <div className="banner error" role="alert">
          {errorMessage}
        </div>
      ) : null}

      {leaveSettingsPrompt ? (
        <div className="dialog-backdrop" role="presentation">
          <section
            className="dialog-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="leave-settings-title"
          >
            <p className="eyebrow">Unpublished Profile Changes</p>
            <h2 id="leave-settings-title">Leave profile settings with unpublished changes?</h2>
            <p>
              {leaveSettingsPrompt.dirtySections.length > 0
                ? `${leaveSettingsPrompt.profileDisplayName} still has ${leaveSettingsPrompt.dirtySections.join(", ")} waiting to be saved.`
                : `${leaveSettingsPrompt.profileDisplayName} still has unpublished profile changes open.`}
            </p>
            <p className="muted">
              {leaveSettingsPrompt.destination === "review"
                ? "Save and leave publishes these profile settings, then moves you back to the review workspace. Don't save discards the unpublished profile changes and leaves the live profile unchanged."
                : `Save and leave publishes these profile settings, then switches to ${leaveSettingsPrompt.nextProfileDisplayName ?? "the selected trusted profile"}. Don't save discards the unpublished profile changes before switching profiles.`}
            </p>
            <div className="actions">
              <button type="button" onClick={() => void handleSaveAndLeaveSettings()} disabled={busy}>
                Save and leave
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void handleDiscardAndLeaveSettings()}
                disabled={busy}
              >
                Don&apos;t save
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={handleStayOnSettings}
                disabled={busy}
              >
                Stay here
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {activeWorkspace === "review" ? (
        <section className="review-console">
          <div className="review-console-rail">
            <UploadRunPanel
              trustedProfiles={trustedProfiles}
              selectedTrustedProfileName={selectedTrustedProfileName}
              stagedReports={stagedReports}
              activeStagedReportId={activeStagedReport?.stagedReportId ?? ""}
              busy={busy}
              exportDisabled={!reviewSession || reviewExportInvalidated}
              onTrustedProfileNameChange={handleReviewTrustedProfileNameChange}
              onStageFiles={handleStageFiles}
              onSelectStagedReport={handleSelectStagedReport}
              onRemoveStagedReport={handleRemoveStagedReport}
              onLaunchReviewWorkspace={() => void handleLaunchReviewWorkspace()}
              onExportAndDownload={() => void handleExportAndDownload()}
            />
          </div>

          <div className="review-console-main">
            <ReviewWorkspace
              runDetail={runDetail}
              reviewSession={reviewSession}
              rows={rows}
              selectedRow={selectedRow}
              selectedReviewRecordKeys={selectedReviewRecordKeys}
              exportArtifact={exportArtifact}
              exportDisabledMessage={reviewContextMessage}
              originalProcessedPreview={originalProcessedPreview}
              onContinueFromOriginalProcessedState={handleContinueFromOriginalProcessedState}
              busy={busy}
              onToggleReviewRowSelection={handleReviewRowSelectionChange}
              onSelectRow={handleActivateReviewRow}
              onApplyBulkVendorName={handleApplyBulkVendorName}
              onApplyBulkOmission={handleApplyBulkOmission}
              onApplyBulkLaborClassification={handleApplyBulkLaborClassification}
              onApplyBulkEquipmentCategory={handleApplyBulkEquipmentCategory}
            />
          </div>
        </section>
      ) : activeWorkspace === "library" ? (
        <RunLibraryWorkspace
          openRuns={openRuns}
          archivedRuns={archivedRuns}
          busy={busy}
          onRefresh={handleRefreshRunLibrary}
          onOpenLatestReviewed={handleOpenLatestReviewedRun}
          onOpenOriginalProcessed={handleOpenOriginalProcessedRun}
          onArchiveRun={handleArchiveRun}
        />
      ) : (
        <ProfileSettingsWorkspace
          key={`settings-session-${settingsWorkspaceSession}`}
          trustedProfiles={trustedProfiles}
          archivedTrustedProfiles={archivedTrustedProfiles}
          selectedTrustedProfileName={selectedTrustedProfileName}
          selectedTrustedProfile={selectedTrustedProfile}
          profileDetail={activeSettingsProfileDetail}
          draftState={activeSettingsDraftState}
          profileDetailLoading={settingsProfileDetailLoading}
          draftSyncToken={draftSyncToken}
          busy={busy}
          settingsErrorMessage={errorMessage}
          onTrustedProfileNameChange={handleSettingsTrustedProfileNameChange}
          onReloadProfileDetail={handleReloadSettingsProfileDetail}
          onOpenDraft={handleOpenSettingsDraft}
          onSaveDraft={handleSaveDraftState}
          onPublishDraft={handlePublishDraft}
          onDiscardDraft={handleDiscardProfileDraft}
          onCreateTrustedProfile={handleCreateTrustedProfile}
          onArchiveTrustedProfile={handleArchiveTrustedProfile}
          onUnarchiveTrustedProfile={handleUnarchiveTrustedProfile}
          onLeaveGuardChange={registerSettingsLeaveGuard}
        />
      )}
    </main>
  );
}
