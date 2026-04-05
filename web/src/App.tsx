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
  ProcessingRunResponse,
  ReviewEditFields,
  ReviewSessionResponse,
  SourceUploadResponse,
  TrustedProfileResponse,
} from "./api/contracts";
import { ExportPanel } from "./components/ExportPanel";
import { ReviewSessionPanel, type ReviewEditFormValue } from "./components/ReviewSessionPanel";
import { RunRecordsPanel } from "./components/RunRecordsPanel";
import { UploadRunPanel } from "./components/UploadRunPanel";

const emptyEditForm: ReviewEditFormValue = {
  recordKey: "",
  vendorNameNormalized: "",
  recapLaborClassification: "",
  equipmentCategory: "",
  omissionChoice: "unchanged",
};

export default function App() {
  const [trustedProfiles, setTrustedProfiles] = useState<TrustedProfileResponse[]>([]);
  const [selectedTrustedProfileName, setSelectedTrustedProfileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<SourceUploadResponse | null>(null);
  const [runSummary, setRunSummary] = useState<ProcessingRunResponse | null>(null);
  const [runDetail, setRunDetail] = useState<ProcessingRunDetailResponse | null>(null);
  const [reviewSession, setReviewSession] = useState<ReviewSessionResponse | null>(null);
  const [exportArtifact, setExportArtifact] = useState<ExportArtifactResponse | null>(null);
  const [editForm, setEditForm] = useState<ReviewEditFormValue>(emptyEditForm);
  const [requestedRevision, setRequestedRevision] = useState("0");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("Waiting for a source report.");

  const selectedTrustedProfile =
    trustedProfiles.find((profile) => profile.profile_name === selectedTrustedProfileName) ?? null;

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
    const nextRecordKey = runDetail?.run_records[0]?.record_key ?? "";
    setEditForm((current) =>
      current.recordKey
        ? current
        : {
            ...current,
            recordKey: nextRecordKey,
          },
    );
  }, [runDetail]);

  useEffect(() => {
    if (reviewSession) {
      setRequestedRevision(String(reviewSession.current_revision));
    }
  }, [reviewSession]);

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

  function resetWorkflowDownstream() {
    setRunSummary(null);
    setRunDetail(null);
    setReviewSession(null);
    setExportArtifact(null);
    setEditForm(emptyEditForm);
    setRequestedRevision("0");
  }

  async function handleUpload() {
    await runAction("Uploading report...", async () => {
      if (!selectedFile) {
        throw new Error("Choose a report PDF before uploading.");
      }
      const nextUpload = await uploadSourceDocument(selectedFile);
      setUpload(nextUpload);
      resetWorkflowDownstream();
      setStatusMessage(`Uploaded ${nextUpload.original_filename}.`);
    });
  }

  async function handleStartRun() {
    await runAction("Starting processing run...", async () => {
      if (!upload) {
        throw new Error("Upload a report before starting a processing run.");
      }
      const profileName = selectedTrustedProfileName.trim();
      if (!profileName) {
        throw new Error("Choose a trusted profile before starting a processing run.");
      }
      const createdRun = await createProcessingRun(upload.upload_id, profileName);
      const runState = await fetchProcessingRun(createdRun.processing_run_id);
      setRunSummary(createdRun);
      setRunDetail(runState);
      setReviewSession(null);
      setExportArtifact(null);
      setEditForm({
        ...emptyEditForm,
        recordKey: runState.run_records[0]?.record_key ?? "",
      });
      setStatusMessage(`Created processing run ${createdRun.processing_run_id}.`);
    });
  }

  async function handleOpenReviewSession() {
    await runAction("Opening review session...", async () => {
      if (!runDetail) {
        throw new Error("Create a processing run before opening the review session.");
      }
      const session = await openReviewSession(runDetail.processing_run_id);
      setReviewSession(session);
      setExportArtifact(null);
      setStatusMessage(`Opened review session ${session.review_session_id} at revision ${session.current_revision}.`);
    });
  }

  function buildChangedFields(): ReviewEditFields {
    const changedFields: ReviewEditFields = {};
    const vendorName = editForm.vendorNameNormalized.trim();
    const laborClass = editForm.recapLaborClassification.trim();
    const equipmentCategory = editForm.equipmentCategory.trim();

    if (vendorName) {
      changedFields.vendor_name_normalized = vendorName;
    }
    if (laborClass) {
      changedFields.recap_labor_classification = laborClass;
    }
    if (equipmentCategory) {
      changedFields.equipment_category = equipmentCategory;
    }
    if (editForm.omissionChoice === "omit") {
      changedFields.is_omitted = true;
    }
    if (editForm.omissionChoice === "include") {
      changedFields.is_omitted = false;
    }
    return changedFields;
  }

  async function handleApplyEditBatch() {
    await runAction("Submitting edit batch...", async () => {
      if (!runDetail) {
        throw new Error("Create a processing run before submitting edits.");
      }
      if (!editForm.recordKey) {
        throw new Error("Choose a record_key before submitting an edit batch.");
      }

      const changedFields = buildChangedFields();
      if (Object.keys(changedFields).length === 0) {
        throw new Error("Choose at least one field change before submitting an edit batch.");
      }

      const session = await appendReviewEdits(runDetail.processing_run_id, [
        {
          record_key: editForm.recordKey,
          changed_fields: changedFields,
        },
      ]);
      setReviewSession(session);
      setExportArtifact(null);
      setRequestedRevision(String(session.current_revision));
      setEditForm({
        ...emptyEditForm,
        recordKey: editForm.recordKey,
      });
      setStatusMessage(`Appended review edits and advanced the session to revision ${session.current_revision}.`);
    });
  }

  async function handleRequestExport() {
    await runAction("Requesting export...", async () => {
      if (!runDetail) {
        throw new Error("Create a processing run before requesting an export.");
      }
      const sessionRevision = Number.parseInt(requestedRevision, 10);
      if (Number.isNaN(sessionRevision) || sessionRevision < 0) {
        throw new Error("session_revision must be a whole number greater than or equal to 0.");
      }
      const artifact = await createExportArtifact(runDetail.processing_run_id, sessionRevision);
      setExportArtifact(artifact);
      setStatusMessage(`Created export artifact ${artifact.export_artifact_id} from revision ${artifact.session_revision}.`);
    });
  }

  async function handleDownloadArtifact() {
    await runAction("Downloading export artifact...", async () => {
      if (!exportArtifact) {
        throw new Error("Request an export artifact before downloading.");
      }
      const filename = await downloadExportArtifact(exportArtifact.download_url);
      setStatusMessage(`Downloaded ${filename}.`);
    });
  }

  const busy = busyAction !== null;

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Phase 1 Browser Workflow</p>
          <h1>Job Cost Tool</h1>
          <p className="hero-copy">
            This browser shell stays intentionally thin. The backend remains the source of truth for immutable runs,
            append-only review revisions, and exact-revision exports.
          </p>
        </div>
        <div className="status-card" aria-live="polite">
          <strong>{busyAction ?? "Workflow status"}</strong>
          <p>{busy ? busyAction : statusMessage}</p>
          {runSummary ? <p className="muted">Latest run: {runSummary.processing_run_id}</p> : null}
        </div>
      </header>

      {errorMessage ? (
        <div className="banner error" role="alert">
          {errorMessage}
        </div>
      ) : null}

      <div className="workflow-grid">
        <UploadRunPanel
          trustedProfiles={trustedProfiles}
          selectedTrustedProfileName={selectedTrustedProfileName}
          selectedTrustedProfile={selectedTrustedProfile}
          selectedFileName={selectedFile?.name ?? ""}
          upload={upload}
          busy={busy}
          onTrustedProfileNameChange={setSelectedTrustedProfileName}
          onFileSelected={setSelectedFile}
          onUpload={handleUpload}
          onStartRun={handleStartRun}
        />
        <RunRecordsPanel runDetail={runDetail} />
        <ReviewSessionPanel
          runDetail={runDetail}
          reviewSession={reviewSession}
          editForm={editForm}
          busy={busy}
          onOpenReviewSession={handleOpenReviewSession}
          onEditFormChange={setEditForm}
          onApplyEditBatch={handleApplyEditBatch}
        />
        <ExportPanel
          reviewSession={reviewSession}
          exportArtifact={exportArtifact}
          requestedRevision={requestedRevision}
          busy={busy}
          onRequestedRevisionChange={setRequestedRevision}
          onRequestExport={handleRequestExport}
          onDownloadArtifact={handleDownloadArtifact}
        />
      </div>
    </main>
  );
}
