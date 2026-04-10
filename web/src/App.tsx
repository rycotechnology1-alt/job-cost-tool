import { useEffect, useRef, useState } from "react";

import {
  ApiRequestError,
  archiveTrustedProfile,
  appendReviewEdits,
  createTrustedProfile,
  createOrOpenProfileDraft,
  discardProfileDraft,
  createExportArtifact,
  createProfileSyncExport,
  createProcessingRun,
  downloadArtifact,
  downloadExportArtifact,
  fetchProfileDetail,
  fetchProfileDraft,
  fetchTrustedProfiles,
  fetchProcessingRun,
  openReviewSession,
  publishProfileDraft,
  unarchiveTrustedProfile,
  updateDraftClassifications,
  updateDraftDefaultOmit,
  updateDraftEquipmentMappings,
  updateDraftLaborMappings,
  updateDraftRates,
  uploadSourceDocument,
} from "./api/client";
import type {
  ClassificationSlotRow,
  CreateTrustedProfileRequest,
  DefaultOmitRuleRow,
  DraftEditorStateResponse,
  EquipmentMappingRow,
  EquipmentRateRow,
  ExportArtifactResponse,
  LaborMappingRow,
  LaborRateRow,
  ProcessingRunDetailResponse,
  ProfileSyncExportResponse,
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
import { ReviewWorkspace, type ReviewEditFormValue, type WorkspaceRow } from "./components/ReviewWorkspace";
import { UploadRunPanel } from "./components/UploadRunPanel";

type DraftSyncReason =
  | "reset"
  | "profileSwitch"
  | "open"
  | "defaultOmit"
  | "laborMappings"
  | "equipmentMappings"
  | "classifications"
  | "rates";

interface DraftSyncToken {
  reason: DraftSyncReason;
  sequence: number;
}

interface LeaveSettingsPromptState {
  destination: "review" | "profile";
  nextProfileName?: string;
  nextProfileDisplayName?: string;
  dirtySections: string[];
  profileDisplayName: string;
}

interface StagedReportItem {
  stagedReportId: string;
  file: File;
  filename: string;
  upload: SourceUploadResponse | null;
}

const emptyEditForm: ReviewEditFormValue = {
  vendorNameNormalized: "",
  recapLaborClassification: "",
  equipmentCategory: "",
  omissionChoice: "unchanged",
};

const maxStagedReports = 10;

function buildStagedReportId(): string {
  return `staged-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
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

function buildEditFormFromRow(row: WorkspaceRow): ReviewEditFormValue {
  return {
    vendorNameNormalized: row.record.vendor_name_normalized ?? row.record.vendor_name ?? "",
    recapLaborClassification: row.record.recap_labor_classification ?? "",
    equipmentCategory: row.record.equipment_category ?? "",
    omissionChoice: "unchanged",
  };
}

function isLaborBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType === "labor";
}

function isEquipmentBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType === "equipment";
}

export default function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<"review" | "settings">("review");
  const [trustedProfiles, setTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [archivedTrustedProfiles, setArchivedTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [selectedTrustedProfileName, setSelectedTrustedProfileName] = useState("");
  const [stagedReports, setStagedReports] = useState<StagedReportItem[]>([]);
  const [activeStagedReportId, setActiveStagedReportId] = useState("");
  const [runDetail, setRunDetail] = useState<ProcessingRunDetailResponse | null>(null);
  const [reviewSession, setReviewSession] = useState<ReviewSessionResponse | null>(null);
  const [profileDetail, setProfileDetail] = useState<PublishedProfileDetailResponse | null>(null);
  const [draftState, setDraftState] = useState<DraftEditorStateResponse | null>(null);
  const [draftSyncToken, setDraftSyncToken] = useState<DraftSyncToken>({ reason: "reset", sequence: 0 });
  const [selectedRecordKey, setSelectedRecordKey] = useState("");
  const [selectedReviewRecordKeys, setSelectedReviewRecordKeys] = useState<string[]>([]);
  const [editForm, setEditForm] = useState<ReviewEditFormValue>(emptyEditForm);
  const [exportArtifact, setExportArtifact] = useState<ExportArtifactResponse | null>(null);
  const [lastDownloadedFilename, setLastDownloadedFilename] = useState("");
  const [lastDownloadedProfileSyncFilename, setLastDownloadedProfileSyncFilename] = useState("");
  const [reviewContextInvalidated, setReviewContextInvalidated] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState(
    "Choose a trusted profile and stage one or more PDFs to start reviewing.",
  );
  const [settingsStatusMessage, setSettingsStatusMessage] = useState(
    "Inspect the live trusted profile and select Edit current profile when you are ready to make changes.",
  );
  const [leaveSettingsPrompt, setLeaveSettingsPrompt] = useState<LeaveSettingsPromptState | null>(null);
  const settingsLeaveGuardRef = useRef<ProfileSettingsLeaveGuard | null>(null);

  const selectedTrustedProfile =
    trustedProfiles.find((profile) => profile.profile_name === selectedTrustedProfileName) ?? null;
  const selectedTrustedProfileId = selectedTrustedProfile?.trusted_profile_id ?? "";
  const activeStagedReport =
    stagedReports.find((report) => report.stagedReportId === activeStagedReportId) ?? stagedReports[0] ?? null;
  const rows = buildWorkspaceRows(runDetail, reviewSession);
  const selectedRow = rows.find((row) => row.recordKey === selectedRecordKey) ?? null;
  const activeReviewProfileMismatch = Boolean(
    runDetail &&
      reviewSession &&
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
  const reviewExportInvalidated = reviewContextInvalidated || activeReviewProfileMismatch;
  const activeReviewProfileLabel =
    runDetail?.trusted_profile_name ?? selectedTrustedProfile?.display_name ?? "the prior trusted profile";
  const reviewContextMessage =
    runDetail && reviewSession && reviewExportInvalidated
      ? activeReviewProfileMismatch
        ? `This loaded review was processed under ${activeReviewProfileLabel}, but the current trusted profile selection is ${selectedTrustedProfile?.display_name ?? "different"}. Reprocess under the selected profile before export is allowed.`
        : `This loaded review was processed under ${activeReviewProfileLabel}, and the trusted profile selection changed afterward. This review is now stale for export and must be reprocessed before export is allowed.`
      : "";

  function advanceDraftSync(reason: DraftSyncReason) {
    setDraftSyncToken((current) => ({
      reason,
      sequence: current.sequence + 1,
    }));
  }

  function registerSettingsLeaveGuard(guard: ProfileSettingsLeaveGuard | null) {
    settingsLeaveGuardRef.current = guard;
  }

  function clearSettingsDraftView() {
    setDraftState(null);
  }

  function completeSettingsProfileSwitch(nextProfileName: string) {
    if (!nextProfileName || nextProfileName === selectedTrustedProfileName) {
      return;
    }
    const nextProfile =
      trustedProfiles.find((profile) => profile.profile_name === nextProfileName) ?? null;
    setSelectedTrustedProfileName(nextProfileName);
    setProfileDetail(null);
    clearSettingsDraftView();
    setLastDownloadedProfileSyncFilename("");
    advanceDraftSync("profileSwitch");
    setSettingsStatusMessage(
      nextProfile
        ? `Loading published settings for ${nextProfile.display_name}.`
        : "Loading trusted profile settings.",
    );
  }

  function completeLeaveSettingsToReview() {
    clearSettingsDraftView();
    setLeaveSettingsPrompt(null);
    setActiveWorkspace("review");
    setErrorMessage("");
  }

  function promptToLeaveSettings(
    destination: "review" | "profile",
    options?: { nextProfileName?: string; nextProfileDisplayName?: string },
  ) {
    const guard = settingsLeaveGuardRef.current;
    if (!guard || !guard.hasUnsavedChanges) {
      setLeaveSettingsPrompt(null);
      if (destination === "review") {
        completeLeaveSettingsToReview();
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

  async function loadSettingsProfileDetail(trustedProfileId: string): Promise<PublishedProfileDetailResponse> {
    return fetchProfileDetail(trustedProfileId);
  }

  function updateStagedReportUpload(stagedReportId: string, upload: SourceUploadResponse | null) {
    setStagedReports((current) =>
      current.map((report) =>
        report.stagedReportId === stagedReportId
          ? {
              ...report,
              upload,
            }
          : report,
      ),
    );
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
        : `Staged ${acceptedCount} report${acceptedCount === 1 ? "" : "s"} for review. Select one queued PDF and open the review workspace when ready.`,
    );
  }

  function handleSelectStagedReport(stagedReportId: string) {
    setActiveStagedReportId(stagedReportId);
    setErrorMessage("");
  }

  function handleRemoveStagedReport(stagedReportId: string) {
    const remaining = stagedReports.filter((report) => report.stagedReportId !== stagedReportId);
    setStagedReports(remaining);
    if (activeStagedReportId === stagedReportId) {
      setActiveStagedReportId(remaining[0]?.stagedReportId ?? "");
    }
    setErrorMessage("");
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
          setStatusMessage("Trusted profiles loaded.");
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
    if (activeWorkspace !== "settings") {
      return;
    }

    setDraftState(null);
    setLastDownloadedProfileSyncFilename("");
    if (!selectedTrustedProfile || !selectedTrustedProfileId) {
      setProfileDetail(null);
      return;
    }

    let cancelled = false;
    setProfileDetail(null);
    setErrorMessage("");
    const trustedProfileId = selectedTrustedProfileId;
    const selectedProfileName = selectedTrustedProfile.profile_name;

    async function loadProfileDetail() {
      try {
        if (cancelled) {
          return;
        }
        const detail = await loadSettingsProfileDetail(trustedProfileId);
        if (cancelled) {
          return;
        }
        setProfileDetail(detail);
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
        setErrorMessage(error instanceof Error ? error.message : "Failed to load profile settings.");
      }
    }

    void loadProfileDetail();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, selectedTrustedProfileId]);

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
      const detail = await loadSettingsProfileDetail(selectedTrustedProfile.trusted_profile_id);
      setProfileDetail(detail);
      patchTrustedProfileSummary(selectedTrustedProfile.profile_name, {
        current_published_version_number: detail.current_published_version.version_number,
        has_open_draft: Boolean(detail.open_draft_id),
      });
      setSettingsStatusMessage(
        `Inspecting live version v${detail.current_published_version.version_number} for ${detail.display_name}.`,
      );
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
    setEditForm(row ? buildEditFormFromRow(row) : emptyEditForm);
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
  ) {
    const nextRows = buildWorkspaceRows(nextRunDetail, nextReviewSession);
    setRunDetail(nextRunDetail);
    setReviewSession(nextReviewSession);
    setExportArtifact(null);
    setLastDownloadedFilename("");
    setReviewContextInvalidated(false);
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
      if (!uploadToUse) {
        uploadToUse = await uploadSourceDocument(stagedReport.file);
        updateStagedReportUpload(stagedReport.stagedReportId, uploadToUse);
      }

      try {
        const { nextRunDetail, nextReviewSession } = await loadReviewWorkspaceFromUpload(uploadToUse);
        applyLoadedReviewWorkspace(
          nextRunDetail,
          nextReviewSession,
          `Loaded ${nextReviewSession.records.length} review records from ${nextRunDetail.source_document_filename}.`,
        );
      } catch (error) {
        if (!(error instanceof ApiRequestError) || error.status !== 410) {
          throw error;
        }

        updateStagedReportUpload(stagedReport.stagedReportId, null);
        const refreshedUpload = await uploadSourceDocument(stagedReport.file);
        updateStagedReportUpload(stagedReport.stagedReportId, refreshedUpload);

        const { nextRunDetail, nextReviewSession } = await loadReviewWorkspaceFromUpload(refreshedUpload);
        applyLoadedReviewWorkspace(
          nextRunDetail,
          nextReviewSession,
          `The cached upload for ${stagedReport.filename} expired from temporary storage, so the queued PDF was uploaded again and reopened in review.`,
        );
      }
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

    if (!hasActiveReview) {
      return;
    }

    setReviewContextInvalidated(true);
    setExportArtifact(null);
    setLastDownloadedFilename("");
    setStatusMessage(
      `Profile selection changed to ${nextProfile?.display_name ?? nextProfileName}. The loaded review was processed under ${activeReviewProfileLabel} and must be reprocessed before export is allowed.`,
    );
  }

  function buildChangedFields(row: WorkspaceRow): ReviewEditFields {
    const changedFields: ReviewEditFields = {};
    const vendorName = editForm.vendorNameNormalized.trim();
    const laborClass = editForm.recapLaborClassification.trim();
    const equipmentCategory = editForm.equipmentCategory.trim();
    const currentVendor = (row.record.vendor_name_normalized ?? row.record.vendor_name ?? "").trim();
    const currentLabor = (row.record.recap_labor_classification ?? "").trim();
    const currentEquipment = (row.record.equipment_category ?? "").trim();

    if (vendorName && vendorName !== currentVendor) {
      changedFields.vendor_name_normalized = vendorName;
    }
    if (laborClass && laborClass !== currentLabor) {
      changedFields.recap_labor_classification = laborClass;
    } else if (!laborClass && currentLabor) {
      changedFields.recap_labor_classification = null;
    }
    if (equipmentCategory && equipmentCategory !== currentEquipment) {
      changedFields.equipment_category = equipmentCategory;
    } else if (!equipmentCategory && currentEquipment) {
      changedFields.equipment_category = null;
    }
    if (editForm.omissionChoice === "omit" && !row.record.is_omitted) {
      changedFields.is_omitted = true;
    }
    if (editForm.omissionChoice === "include" && row.record.is_omitted) {
      changedFields.is_omitted = false;
    }
    return changedFields;
  }

  async function handleApplyEditBatch() {
    await runAction("Applying review change...", async () => {
      if (!runDetail || !reviewSession || !selectedRow) {
        throw new Error("Open the review workspace and choose a row before applying a change.");
      }

      const changedFields = buildChangedFields(selectedRow);
      if (Object.keys(changedFields).length === 0) {
        throw new Error("Change at least one field or omission state before applying a review change.");
      }

      const nextReviewSession = await appendReviewEdits(runDetail.processing_run_id, [
        {
          record_key: selectedRow.recordKey,
          changed_fields: changedFields,
        },
      ]);
      const nextRows = buildWorkspaceRows(runDetail, nextReviewSession);
      setReviewSession(nextReviewSession);
      setExportArtifact(null);
      setLastDownloadedFilename("");
      setSelectedReviewRecordKeys((current) => current.filter((recordKey) => nextRows.some((row) => row.recordKey === recordKey)));
      selectRow(nextRows, selectedRow.recordKey);
      setStatusMessage(`Applied a review change and advanced the session to revision ${nextReviewSession.current_revision}.`);
    });
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

      let usedFallbackCreate = false;
      let draft: DraftEditorStateResponse;
      if (profileDetail?.open_draft_id) {
        try {
          draft = await fetchProfileDraft(profileDetail.open_draft_id);
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
        current
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

  async function handleSaveDefaultOmit(rowsToSave: DefaultOmitRuleRow[]): Promise<boolean> {
    return runAction("Saving default omit rules...", async () => {
      if (!draftState) {
        throw new Error("Edit the current profile before saving default omit rules.");
      }
      const nextDraft = await updateDraftDefaultOmit(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
      advanceDraftSync("defaultOmit");
      setSettingsStatusMessage("Saved default omit rules into the current unpublished profile changes.");
    });
  }

  async function handleSaveLaborMappings(rowsToSave: LaborMappingRow[]): Promise<boolean> {
    return runAction("Saving labor mappings...", async () => {
      if (!draftState) {
        throw new Error("Edit the current profile before saving labor mappings.");
      }
      const nextDraft = await updateDraftLaborMappings(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
      advanceDraftSync("laborMappings");
      setSettingsStatusMessage("Saved labor mappings into the current unpublished profile changes.");
    });
  }

  async function handleSaveEquipmentMappings(rowsToSave: EquipmentMappingRow[]): Promise<boolean> {
    return runAction("Saving equipment mappings...", async () => {
      if (!draftState) {
        throw new Error("Edit the current profile before saving equipment mappings.");
      }
      const nextDraft = await updateDraftEquipmentMappings(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
      advanceDraftSync("equipmentMappings");
      setSettingsStatusMessage("Saved equipment mappings into the current unpublished profile changes.");
    });
  }

  async function handleSaveClassifications(
    laborSlots: ClassificationSlotRow[],
    equipmentSlots: ClassificationSlotRow[],
  ): Promise<boolean> {
    return runAction("Saving classifications...", async () => {
      if (!draftState) {
        throw new Error("Edit the current profile before saving classifications.");
      }
      const nextDraft = await updateDraftClassifications(
        draftState.trusted_profile_draft_id,
        laborSlots,
        equipmentSlots,
      );
      setDraftState(nextDraft);
      advanceDraftSync("classifications");
      setSettingsStatusMessage("Saved labor and equipment classifications into the current unpublished profile changes.");
    });
  }

  async function handleSaveRates(laborRates: LaborRateRow[], equipmentRates: EquipmentRateRow[]): Promise<boolean> {
    return runAction("Saving rates...", async () => {
      if (!draftState) {
        throw new Error("Edit the current profile before saving rates.");
      }
      const nextDraft = await updateDraftRates(draftState.trusted_profile_draft_id, laborRates, equipmentRates);
      setDraftState(nextDraft);
      advanceDraftSync("rates");
      setSettingsStatusMessage("Saved rates into the current unpublished profile changes.");
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
      const draftIdToPublish = trustedProfileDraftId ?? draftState?.trusted_profile_draft_id;
      if (!draftIdToPublish) {
        throw new Error("Edit the current profile before saving profile settings.");
      }

      const publishedDetail = await publishProfileDraft(draftIdToPublish);
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
      setSettingsStatusMessage(
        refreshConfirmed
          ? `Saved profile settings and published live version v${refreshedDetail.current_published_version.version_number} for ${refreshedDetail.display_name}.`
          : `Saved profile settings and published live version v${publishedDetail.current_published_version.version_number} for ${publishedDetail.display_name}. The summary is showing the publish response until the next reload.`,
      );
    });
  }

  async function handleCreateDesktopSyncExport() {
    await runAction("Creating desktop sync archive...", async () => {
      if (!profileDetail) {
        throw new Error("Load a published trusted profile before creating a desktop sync archive.");
      }

      const syncExport: ProfileSyncExportResponse = await createProfileSyncExport(
        profileDetail.current_published_version.trusted_profile_version_id,
      );
      const filename = await downloadArtifact(syncExport.download_url);
      setLastDownloadedProfileSyncFilename(filename);
      setSettingsStatusMessage(
        `Downloaded ${filename} for manual desktop sync from live version v${syncExport.version_number}.`,
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
      setLastDownloadedProfileSyncFilename("");
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
      setLastDownloadedProfileSyncFilename("");
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
    if (prompt.destination === "review") {
      completeLeaveSettingsToReview();
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
    if (prompt.destination === "review") {
      completeLeaveSettingsToReview();
      return;
    }
    setLeaveSettingsPrompt(null);
    if (prompt.nextProfileName) {
      completeSettingsProfileSwitch(prompt.nextProfileName);
    }
  }

  const busy = busyAction !== null;
  const currentWorkspaceStatusMessage = activeWorkspace === "settings" ? settingsStatusMessage : statusMessage;
  const currentWorkspaceTitle = activeWorkspace === "settings" ? "Profile Settings Workspace" : "Job Cost Review Workspace";
  const currentWorkspaceEyebrow = activeWorkspace === "settings" ? "Phase 2A Settings" : "Phase 1 Pilot Review";
  const currentWorkspaceCopy =
    activeWorkspace === "settings"
      ? "The browser remains a thin client. Live profile versions and save rules still come from the backend authoring services."
      : "The browser stays thin. Processing, review lineage, and exact-revision export still come from the accepted backend services.";

  return (
    <main className="app-shell">
      <header className="hero compact-hero">
        <div>
          <p className="eyebrow">{currentWorkspaceEyebrow}</p>
          <h1>{currentWorkspaceTitle}</h1>
          <p className="hero-copy">{currentWorkspaceCopy}</p>
        </div>
        <div className="status-card" aria-live="polite">
          <strong>{busyAction ?? "Workflow status"}</strong>
          <p>{busy ? busyAction : currentWorkspaceStatusMessage}</p>
          {activeWorkspace === "review" && runDetail ? (
            <p className="muted">Reviewing {runDetail.source_document_filename}</p>
          ) : null}
          {activeWorkspace === "settings" && selectedTrustedProfile ? (
            <p className="muted">Editing profile {selectedTrustedProfile.display_name}</p>
          ) : null}
        </div>
      </header>

      <section className="workspace-toggle" aria-label="Workspace mode">
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
          className={activeWorkspace === "settings" ? "toggle-button active" : "toggle-button"}
          onClick={() => {
            setActiveWorkspace("settings");
            setErrorMessage("");
          }}
          aria-pressed={activeWorkspace === "settings"}
        >
          Profile settings
        </button>
      </section>

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
            <p className="eyebrow">Unsaved Profile Settings</p>
            <h2 id="leave-settings-title">Leave profile settings with unsaved sections?</h2>
            <p>
              {leaveSettingsPrompt.profileDisplayName} still has {leaveSettingsPrompt.dirtySections.join(", ")} waiting
              to be saved.
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
        <>
          <UploadRunPanel
            trustedProfiles={trustedProfiles}
            selectedTrustedProfileName={selectedTrustedProfileName}
            selectedTrustedProfile={selectedTrustedProfile}
            stagedReports={stagedReports}
            activeStagedReportId={activeStagedReport?.stagedReportId ?? ""}
            busy={busy}
            onTrustedProfileNameChange={handleReviewTrustedProfileNameChange}
            onStageFiles={handleStageFiles}
            onSelectStagedReport={handleSelectStagedReport}
            onRemoveStagedReport={handleRemoveStagedReport}
            onLaunchReviewWorkspace={handleLaunchReviewWorkspace}
          />

          <ReviewWorkspace
            runDetail={runDetail}
            reviewSession={reviewSession}
            rows={rows}
            selectedRow={selectedRow}
            selectedReviewRecordKeys={selectedReviewRecordKeys}
            editForm={editForm}
            exportArtifact={exportArtifact}
            lastDownloadedFilename={lastDownloadedFilename}
            exportDisabled={reviewExportInvalidated}
            exportDisabledMessage={reviewContextMessage}
            busy={busy}
            onToggleReviewRowSelection={handleReviewRowSelectionChange}
            onSelectRow={(recordKey) => {
              const row = rows.find((item) => item.recordKey === recordKey) ?? null;
              setSelectedRecordKey(recordKey);
              setEditForm(row ? buildEditFormFromRow(row) : emptyEditForm);
            }}
            onEditFormChange={setEditForm}
            onApplyEditBatch={handleApplyEditBatch}
            onApplyBulkOmission={handleApplyBulkOmission}
            onApplyBulkLaborClassification={handleApplyBulkLaborClassification}
            onApplyBulkEquipmentCategory={handleApplyBulkEquipmentCategory}
            onExportAndDownload={handleExportAndDownload}
          />
        </>
      ) : (
        <ProfileSettingsWorkspace
          trustedProfiles={trustedProfiles}
          archivedTrustedProfiles={archivedTrustedProfiles}
          selectedTrustedProfileName={selectedTrustedProfileName}
          selectedTrustedProfile={selectedTrustedProfile}
          profileDetail={profileDetail}
          draftState={draftState}
          draftSyncToken={draftSyncToken}
          busy={busy}
          settingsErrorMessage={errorMessage}
          onTrustedProfileNameChange={handleSettingsTrustedProfileNameChange}
          onReloadProfileDetail={handleReloadSettingsProfileDetail}
          onOpenDraft={handleOpenSettingsDraft}
          onSaveDefaultOmit={handleSaveDefaultOmit}
          onSaveLaborMappings={handleSaveLaborMappings}
          onSaveEquipmentMappings={handleSaveEquipmentMappings}
          onSaveClassifications={handleSaveClassifications}
          onSaveRates={handleSaveRates}
          onPublishDraft={handlePublishDraft}
          onDiscardDraft={handleDiscardProfileDraft}
          onCreateTrustedProfile={handleCreateTrustedProfile}
          onArchiveTrustedProfile={handleArchiveTrustedProfile}
          onUnarchiveTrustedProfile={handleUnarchiveTrustedProfile}
          onCreateDesktopSyncExport={handleCreateDesktopSyncExport}
          onLeaveGuardChange={registerSettingsLeaveGuard}
          lastDownloadedProfileSyncFilename={lastDownloadedProfileSyncFilename}
        />
      )}
    </main>
  );
}
