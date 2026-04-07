import { useEffect, useState } from "react";

import {
  appendReviewEdits,
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
  updateDraftClassifications,
  updateDraftDefaultOmit,
  updateDraftEquipmentMappings,
  updateDraftLaborMappings,
  updateDraftRates,
  uploadSourceDocument,
} from "./api/client";
import type {
  ClassificationSlotRow,
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
  const [selectedTrustedProfileName, setSelectedTrustedProfileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<SourceUploadResponse | null>(null);
  const [runDetail, setRunDetail] = useState<ProcessingRunDetailResponse | null>(null);
  const [reviewSession, setReviewSession] = useState<ReviewSessionResponse | null>(null);
  const [profileDetail, setProfileDetail] = useState<PublishedProfileDetailResponse | null>(null);
  const [draftState, setDraftState] = useState<DraftEditorStateResponse | null>(null);
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
  const rows = buildWorkspaceRows(runDetail, reviewSession);
  const selectedRow = rows.find((row) => row.recordKey === selectedRecordKey) ?? rows[0] ?? null;

  useEffect(() => {
    let cancelled = false;

    async function loadTrustedProfiles() {
      try {
        const profiles = await fetchTrustedProfiles();
        if (cancelled) {
          return;
        }
        setTrustedProfiles(profiles);
        setSelectedTrustedProfileName((current) => {
          const existingMatch = profiles.some((profile) => profile.profile_name === current);
          if (existingMatch) {
            return current;
          }
          const activeProfile = profiles.find((profile) => profile.is_active_profile);
          return activeProfile?.profile_name ?? profiles[0]?.profile_name ?? "";
        });
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

    setDraftState(null);
    setLastDownloadedProfileSyncFilename("");
    if (!selectedTrustedProfile) {
      setProfileDetail(null);
      return;
    }

    let cancelled = false;
    setProfileDetail(null);
    setErrorMessage("");
    const trustedProfileId = selectedTrustedProfile.trusted_profile_id;

    async function loadProfileDetail() {
      try {
        const detail = await fetchProfileDetail(trustedProfileId);
        if (cancelled) {
          return;
        }
        setProfileDetail(detail);
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
  }, [activeWorkspace, selectedTrustedProfile]);

  async function runAction(actionLabel: string, action: () => Promise<void>) {
    setBusyAction(actionLabel);
    setErrorMessage("");
    try {
      await action();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Unexpected browser workflow error.");
    } finally {
      setBusyAction(null);
    }
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

      const draft = profileDetail?.open_draft_id
        ? await fetchProfileDraft(profileDetail.open_draft_id)
        : await createOrOpenProfileDraft(selectedTrustedProfile.trusted_profile_id);
      setDraftState(draft);
      setProfileDetail((current) =>
        current
          ? {
              ...current,
              open_draft_id: draft.trusted_profile_draft_id,
            }
          : current,
      );
      setSettingsStatusMessage(`Draft ${draft.trusted_profile_draft_id} is ready for editing.`);
    });
  }

  async function handleSaveDefaultOmit(rowsToSave: DefaultOmitRuleRow[]) {
    await runAction("Saving default omit rules...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before saving default omit rules.");
      }
      const nextDraft = await updateDraftDefaultOmit(draftState.trusted_profile_draft_id, rowsToSave);
      setDraftState(nextDraft);
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
      setSettingsStatusMessage("Saved rates to the current draft.");
    });
  }

  async function handlePublishDraft() {
    await runAction("Publishing profile draft...", async () => {
      if (!draftState) {
        throw new Error("Open a draft before publishing.");
      }

      const publishedDetail = await publishProfileDraft(draftState.trusted_profile_draft_id);
      setProfileDetail(publishedDetail);
      setDraftState(null);
      setSettingsStatusMessage(
        `Published version v${publishedDetail.current_published_version.version_number} for ${publishedDetail.display_name}.`,
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
          selectedTrustedProfileName={selectedTrustedProfileName}
          selectedTrustedProfile={selectedTrustedProfile}
          profileDetail={profileDetail}
          draftState={draftState}
          busy={busy}
          onTrustedProfileNameChange={setSelectedTrustedProfileName}
          onOpenDraft={handleOpenSettingsDraft}
          onSaveDefaultOmit={handleSaveDefaultOmit}
          onSaveLaborMappings={handleSaveLaborMappings}
          onSaveEquipmentMappings={handleSaveEquipmentMappings}
          onSaveClassifications={handleSaveClassifications}
          onSaveRates={handleSaveRates}
          onPublishDraft={handlePublishDraft}
          onCreateDesktopSyncExport={handleCreateDesktopSyncExport}
          lastDownloadedProfileSyncFilename={lastDownloadedProfileSyncFilename}
        />
      )}
    </main>
  );
}
