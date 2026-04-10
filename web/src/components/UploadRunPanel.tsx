import type { ChangeEvent, DragEvent } from "react";

import type { SourceUploadResponse, TrustedProfileResponse } from "../api/contracts";

export interface StagedReportSummary {
  stagedReportId: string;
  filename: string;
  upload: SourceUploadResponse | null;
}

interface UploadRunPanelProps {
  trustedProfiles: TrustedProfileResponse[];
  selectedTrustedProfileName: string;
  selectedTrustedProfile: TrustedProfileResponse | null;
  stagedReports: StagedReportSummary[];
  activeStagedReportId: string;
  busy: boolean;
  onTrustedProfileNameChange: (value: string) => void;
  onStageFiles: (files: File[]) => void;
  onSelectStagedReport: (stagedReportId: string) => void;
  onRemoveStagedReport: (stagedReportId: string) => void;
  onLaunchReviewWorkspace: () => Promise<void> | void;
}

export function UploadRunPanel({
  trustedProfiles,
  selectedTrustedProfileName,
  selectedTrustedProfile,
  stagedReports,
  activeStagedReportId,
  busy,
  onTrustedProfileNameChange,
  onStageFiles,
  onSelectStagedReport,
  onRemoveStagedReport,
  onLaunchReviewWorkspace,
}: UploadRunPanelProps) {
  const activeStagedReport =
    stagedReports.find((report) => report.stagedReportId === activeStagedReportId) ?? stagedReports[0] ?? null;

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    onStageFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    onStageFiles(Array.from(event.dataTransfer.files ?? []));
  }

  return (
    <section className="setup-panel">
      <div className="panel-heading">
        <h2>Open Review Workspace</h2>
        <p>Choose one trusted profile, stage up to 10 PDFs, then open whichever queued report you want to review.</p>
      </div>
      <div className="setup-grid">
        <label className="field">
          <span>Trusted profile</span>
          <select
            name="trusted-profile"
            value={selectedTrustedProfileName}
            onChange={(event) => onTrustedProfileNameChange(event.target.value)}
            disabled={busy || trustedProfiles.length === 0}
          >
            {trustedProfiles.length === 0 ? <option value="">No trusted profiles available</option> : null}
            {trustedProfiles.map((profile) => (
              <option key={profile.profile_name} value={profile.profile_name}>
                {profile.display_name}
              </option>
            ))}
          </select>
        </label>

        <label
          className="dropzone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <span className="dropzone-label">Source report PDF</span>
          <strong>{activeStagedReport?.filename ?? "Drop one or more PDFs here or browse"}</strong>
          <small>
            {stagedReports.length > 0
              ? "Queued PDFs stay staged here so you can open the next report without reselecting it."
              : "Add one or more job-cost PDFs to build a small staged review queue."}
          </small>
          <input
            aria-label="Source report PDF"
            type="file"
            accept=".pdf,application/pdf"
            multiple
            onChange={handleFileChange}
            disabled={busy}
          />
        </label>

        <div className="setup-summary staged-report-summary">
          <div className="staged-report-header">
            <strong>Staged reports</strong>
            <span className="status-pill neutral">{stagedReports.length} queued</span>
          </div>
          {stagedReports.length === 0 ? (
            <p className="muted">No PDFs are staged yet.</p>
          ) : (
            <div className="staged-report-list" role="list" aria-label="Staged reports">
              {stagedReports.map((report) => {
                const isActive = report.stagedReportId === activeStagedReport?.stagedReportId;
                return (
                  <div
                    key={report.stagedReportId}
                    className={isActive ? "staged-report-item active" : "staged-report-item"}
                    role="listitem"
                  >
                    <button
                      type="button"
                      className="staged-report-select"
                      aria-pressed={isActive}
                      onClick={() => onSelectStagedReport(report.stagedReportId)}
                      disabled={busy}
                    >
                      <strong>{report.filename}</strong>
                      <small>{report.upload ? "Cached upload ready" : "Ready to upload when opened"}</small>
                    </button>
                    <button
                      type="button"
                      className="tertiary-button"
                      onClick={() => onRemoveStagedReport(report.stagedReportId)}
                      disabled={busy}
                    >
                      Remove
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="setup-summary">
          <strong>{selectedTrustedProfile?.display_name ?? "No trusted profile selected"}</strong>
          <p>{selectedTrustedProfile?.description || "Select one validated trusted profile for this pilot review."}</p>
          <dl className="summary-list compact">
            <div>
              <dt>Profile key</dt>
              <dd>{selectedTrustedProfile?.profile_name ?? "-"}</dd>
            </div>
            <div>
              <dt>Template</dt>
              <dd>{selectedTrustedProfile?.template_filename ?? "-"}</dd>
            </div>
            <div>
              <dt>Queued file</dt>
              <dd>{activeStagedReport?.filename ?? "-"}</dd>
            </div>
          </dl>
        </div>
      </div>
      <div className="actions">
        <button
          type="button"
          onClick={onLaunchReviewWorkspace}
          disabled={busy || !selectedTrustedProfile || !activeStagedReport}
        >
          Open review workspace
        </button>
      </div>
    </section>
  );
}
