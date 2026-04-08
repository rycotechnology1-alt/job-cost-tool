import { useEffect, useState } from "react";

import {
  ApiRequestError,
  archiveTrustedProfile,
  appendReviewEdits,
  createTrustedProfile,
  createOrOpenProfileDraft,
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
import { ProfileSettingsWorkspace } from "./components/ProfileSettingsWorkspace";
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

const emptyEditForm: ReviewEditFormValue = {
  vendorNameNormalized: "",
  recapLaborClassification: "",
  equipmentCategory: "",
  omissionChoice: "unchanged",
};

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

export default function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<"review" | "settings">("review");
  const [trustedProfiles, setTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [archivedTrustedProfiles, setArchivedTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [selectedTrustedProfileName, setSelectedTrustedProfileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<SourceUploadResponse | null>(null);
  const [runDetail, setRunDetail] = useState<ProcessingRunDetailResponse | null>(null);
  const [reviewSession, setReviewSession] = useState<ReviewSessionResponse | null>(null);
  const [profileDetail, setProfileDetail] = useState<PublishedProfileDetailResponse | null>(null);
  const [draftState, setDraftState] = useState<DraftEditorStateResponse | null>(null);
  const [draftSyncToken, setDraftSyncToken] = useState<DraftSyncToken>({ reason: "reset", sequence: 0 });
  const [selectedRecordKey, setSelectedRecordKey] = useState("");
  const [editForm, setEditForm] = useState<ReviewEditFormValue>(emptyEditForm);
  const [exportArtifact, setExportArtifact] = useState<ExportArtifactResponse | null>(null);
  const [lastDownloadedFilename, setLastDownloadedFilename] = useState("");
  const [lastDownloadedProfileSyncFilename, setLastDownloadedProfileSyncFilename] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("Choose a trusted profile and a PDF to start reviewing.");
  const [settingsStatusMessage, setSettingsStatusMessage] = useState(
    "Inspect the published trusted profile and open the single mutable draft when you are ready to edit.",
  );

  const selectedTrustedProfile =
    trustedProfiles.find((profile) => profile.profile_name === selectedTrustedProfileName) ?? null;
  const selectedTrustedProfileId = selectedTrustedProfile?.trusted_profile_id ?? "";
  const rows = buildWorkspaceRows(runDetail, reviewSession);
  const selectedRow = rows.find((row) => row.recordKey === selectedRecordKey) ?? rows[0] ?? null;

  function advanceDraftSync(reason: DraftSyncReason) {
    setDraftSyncToken((current) => ({
      reason,
      sequence: current.sequence + 1,
    }));
  }

  async function loadSettingsProfileDetail(trustedProfileId: string): Promise<PublishedProfileDetailResponse> {
    return fetchProfileDetail(trustedProfileId);
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
          `Inspecting published version v${detail.current_published_version.version_number} for ${detail.display_name}.`,
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
  ) {
    setBusyAction(actionLabel);
    setErrorMessage("");
    try {
      await action();
    } catch (error) {
      const normalizedError = error instanceof Error ? error : new Error("Unexpected browser workflow error.");
      setErrorMessage(normalizedError.message);
      if (options?.rethrow) {
        throw normalizedError;
      }
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
        `Inspecting published version v${detail.current_published_version.version_number} for ${detail.display_name}.`,
      );
    });
  }

  function handleSettingsTrustedProfileNameChange(nextProfileName: string) {
    if (!nextProfileName || nextProfileName === selectedTrustedProfileName) {
      return;
    }
    const nextProfile =
      trustedProfiles.find((profile) => profile.profile_name === nextProfileName) ?? null;
    setSelectedTrustedProfileName(nextProfileName);
    setProfileDetail(null);
    setDraftState(null);
    setLastDownloadedProfileSyncFilename("");
    advanceDraftSync("profileSwitch");
    setSettingsStatusMessage(
      nextProfile
        ? `Loading published settings for ${nextProfile.display_name}.`
        : "Loading trusted profile settings.",
    );
  }

  function selectRow(nextRows: WorkspaceRow[], recordKey: string | null) {
    const preferred = recordKey ? nextRows.find((row) => row.recordKey === recordKey) : nextRows[0] ?? null;
    const row = preferred ?? nextRows[0] ?? null;
    setSelectedRecordKey(row?.recordKey ?? "");
    setEditForm(row ? buildEditFormFromRow(row) : emptyEditForm);
  }

  async function handleLaunchReviewWorkspace() {
    await runAction("Opening review workspace...", async () => {
      if (!selectedTrustedProfileName.trim()) {
        throw new Error("Choose a trusted profile before opening the review workspace.");
      }

      const uploadToUse =
        selectedFile !== null
          ? await uploadSourceDocument(selectedFile)
          : upload;
      if (!uploadToUse) {
        throw new Error("Choose a report PDF before opening the review workspace.");
      }

      const createdRun = await createProcessingRun(uploadToUse.upload_id, selectedTrustedProfileName.trim());
      const nextRunDetail = await fetchProcessingRun(createdRun.processing_run_id);
      const nextReviewSession = await openReviewSession(createdRun.processing_run_id);
      const nextRows = buildWorkspaceRows(nextRunDetail, nextReviewSession);

      setUpload(uploadToUse);
      setRunDetail(nextRunDetail);
      setReviewSession(nextReviewSession);
      setExportArtifact(null);
      setLastDownloadedFilename("");
      selectRow(nextRows, nextRows[0]?.recordKey ?? null);
      setStatusMessage(
        `Loaded ${nextReviewSession.records.length} review records from ${nextRunDetail.source_document_filename}.`,
      );
    });
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
    }
    if (equipmentCategory && equipmentCategory !== currentEquipment) {
      changedFields.equipment_category = equipmentCategory;
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
      selectRow(nextRows, selectedRow.recordKey);
      setStatusMessage(`Applied a review change and advanced the session to revision ${nextReviewSession.current_revision}.`);
    });
  }

  async function handleExportAndDownload() {
    await runAction("Exporting workbook...", async () => {
      if (!runDetail || !reviewSession) {
        throw new Error("Open the review workspace before exporting a workbook.");
      }

      const artifact = await createExportArtifact(runDetail.processing_run_id, reviewSession.current_revision);
      const filename = await downloadExportArtifact(artifact.download_url);
      setExportArtifact(artifact);
      setLastDownloadedFilename(filename);
      setStatusMessage(`Downloaded ${filename} from review revision ${artifact.session_revision}.`);
    });
  }

  async function handleOpenSettingsDraft() {
    await runAction("Opening profile draft...", async () => {
      if (!selectedTrustedProfile) {
        throw new Error("Choose a trusted profile before opening a draft.");
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
          ? `Recovered from a missing current draft link and reopened draft ${draft.trusted_profile_draft_id}.`
          : `Draft ${draft.trusted_profile_draft_id} is ready for editing.`,
      );
    });
  }

  async function handleSaveDefaultOmit(rowsToSave: DefaultOmitRuleRow[]) {
    await runAction("Saving default omit rules...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before saving default omit rules.");
      }
      const nextDraft = await updateDraftDefaultOmit(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
      advanceDraftSync("defaultOmit");
      setSettingsStatusMessage("Saved default omit rules to the current draft.");
    });
  }

  async function handleSaveLaborMappings(rowsToSave: LaborMappingRow[]) {
    await runAction("Saving labor mappings...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before saving labor mappings.");
      }
      const nextDraft = await updateDraftLaborMappings(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
      advanceDraftSync("laborMappings");
      setSettingsStatusMessage("Saved labor mappings to the current draft.");
    });
  }

  async function handleSaveEquipmentMappings(rowsToSave: EquipmentMappingRow[]) {
    await runAction("Saving equipment mappings...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before saving equipment mappings.");
      }
      const nextDraft = await updateDraftEquipmentMappings(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
      advanceDraftSync("equipmentMappings");
      setSettingsStatusMessage("Saved equipment mappings to the current draft.");
    });
  }

  async function handleSaveClassifications(
    laborSlots: ClassificationSlotRow[],
    equipmentSlots: ClassificationSlotRow[],
  ) {
    await runAction("Saving classifications...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before saving classifications.");
      }
      const nextDraft = await updateDraftClassifications(
        draftState.trusted_profile_draft_id,
        laborSlots,
        equipmentSlots,
      );
      setDraftState(nextDraft);
      advanceDraftSync("classifications");
      setSettingsStatusMessage("Saved labor and equipment classifications to the current draft.");
    });
  }

  async function handleSaveRates(laborRates: LaborRateRow[], equipmentRates: EquipmentRateRow[]) {
    await runAction("Saving rates...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before saving rates.");
      }
      const nextDraft = await updateDraftRates(draftState.trusted_profile_draft_id, laborRates, equipmentRates);
      setDraftState(nextDraft);
      advanceDraftSync("rates");
      setSettingsStatusMessage("Saved rates to the current draft.");
    });
  }

  async function handlePublishDraft() {
    await runAction("Publishing profile draft...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before publishing.");
      }

      const publishedDetail = await publishProfileDraft(draftState.trusted_profile_draft_id);
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
          ? `Published version v${refreshedDetail.current_published_version.version_number} for ${refreshedDetail.display_name} and reloaded the published summary.`
          : `Published version v${publishedDetail.current_published_version.version_number} for ${publishedDetail.display_name}. The published summary is showing the publish response until the next reload.`,
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
        `Downloaded ${filename} for manual desktop sync from published version v${syncExport.version_number}.`,
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
        `Created ${createdDetail.display_name} from published version v${seedVersionNumber} of ${seedProfile.display_name}. Open a draft when you are ready to edit it.`,
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

  const busy = busyAction !== null;
  const currentWorkspaceStatusMessage = activeWorkspace === "settings" ? settingsStatusMessage : statusMessage;
  const currentWorkspaceTitle = activeWorkspace === "settings" ? "Profile Settings Workspace" : "Job Cost Review Workspace";
  const currentWorkspaceEyebrow = activeWorkspace === "settings" ? "Phase 2A Settings" : "Phase 1 Pilot Review";
  const currentWorkspaceCopy =
    activeWorkspace === "settings"
      ? "The browser remains a thin client. Published versions, draft validation, and immutable publish flow still come from the backend authoring services."
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

      {activeWorkspace === "review" ? (
        <>
          <UploadRunPanel
            trustedProfiles={trustedProfiles}
            selectedTrustedProfileName={selectedTrustedProfileName}
            selectedTrustedProfile={selectedTrustedProfile}
            selectedFileName={selectedFile?.name ?? ""}
            upload={upload}
            busy={busy}
            onTrustedProfileNameChange={setSelectedTrustedProfileName}
            onFileSelected={setSelectedFile}
            onLaunchReviewWorkspace={handleLaunchReviewWorkspace}
          />

          <ReviewWorkspace
            runDetail={runDetail}
            reviewSession={reviewSession}
            rows={rows}
            selectedRow={selectedRow}
            editForm={editForm}
            exportArtifact={exportArtifact}
            lastDownloadedFilename={lastDownloadedFilename}
            busy={busy}
            onSelectRow={(recordKey) => {
              const row = rows.find((item) => item.recordKey === recordKey) ?? null;
              setSelectedRecordKey(recordKey);
              setEditForm(row ? buildEditFormFromRow(row) : emptyEditForm);
            }}
            onEditFormChange={setEditForm}
            onApplyEditBatch={handleApplyEditBatch}
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
          onCreateTrustedProfile={handleCreateTrustedProfile}
          onArchiveTrustedProfile={handleArchiveTrustedProfile}
          onUnarchiveTrustedProfile={handleUnarchiveTrustedProfile}
          onCreateDesktopSyncExport={handleCreateDesktopSyncExport}
          lastDownloadedProfileSyncFilename={lastDownloadedProfileSyncFilename}
        />
      )}
    </main>
  );
}
