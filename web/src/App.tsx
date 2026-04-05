import { useEffect, useState } from "react";

import {
  appendReviewEdits,
  createExportArtifact,
  createProcessingRun,
  downloadExportArtifact,
  fetchTrustedProfiles,
  fetchProcessingRun,
  openReviewSession,
  uploadSourceDocument,
} from "./api/client";
import type {
  ExportArtifactResponse,
  ProcessingRunDetailResponse,
  ReviewEditFields,
  ReviewSessionResponse,
  SourceUploadResponse,
  TrustedProfileResponse,
} from "./api/contracts";
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
  const [trustedProfiles, setTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [selectedTrustedProfileName, setSelectedTrustedProfileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<SourceUploadResponse | null>(null);
  const [runDetail, setRunDetail] = useState<ProcessingRunDetailResponse | null>(null);
  const [reviewSession, setReviewSession] = useState<ReviewSessionResponse | null>(null);
  const [selectedRecordKey, setSelectedRecordKey] = useState("");
  const [editForm, setEditForm] = useState<ReviewEditFormValue>(emptyEditForm);
  const [exportArtifact, setExportArtifact] = useState<ExportArtifactResponse | null>(null);
  const [lastDownloadedFilename, setLastDownloadedFilename] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("Choose a trusted profile and a PDF to start reviewing.");

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

  const busy = busyAction !== null;

  return (
    <main className="app-shell">
      <header className="hero compact-hero">
        <div>
          <p className="eyebrow">Phase 1 Pilot Review</p>
          <h1>Job Cost Review Workspace</h1>
          <p className="hero-copy">
            The browser stays thin. Processing, review lineage, and exact-revision export still come from the accepted
            backend services.
          </p>
        </div>
        <div className="status-card" aria-live="polite">
          <strong>{busyAction ?? "Workflow status"}</strong>
          <p>{busy ? busyAction : statusMessage}</p>
          {runDetail ? <p className="muted">Reviewing {runDetail.source_document_filename}</p> : null}
        </div>
      </header>

      {errorMessage ? (
        <div className="banner error" role="alert">
          {errorMessage}
        </div>
      ) : null}

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
    </main>
  );
}
