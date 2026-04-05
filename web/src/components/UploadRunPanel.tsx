import type { ChangeEvent, DragEvent } from "react";

import type { SourceUploadResponse, TrustedProfileResponse } from "../api/contracts";

interface UploadRunPanelProps {
  trustedProfiles: TrustedProfileResponse[];
  selectedTrustedProfileName: string;
  selectedTrustedProfile: TrustedProfileResponse | null;
  selectedFileName: string;
  upload: SourceUploadResponse | null;
  busy: boolean;
  onTrustedProfileNameChange: (value: string) => void;
  onFileSelected: (file: File | null) => void;
  onLaunchReviewWorkspace: () => Promise<void> | void;
}

export function UploadRunPanel({
  trustedProfiles,
  selectedTrustedProfileName,
  selectedTrustedProfile,
  selectedFileName,
  upload,
  busy,
  onTrustedProfileNameChange,
  onFileSelected,
  onLaunchReviewWorkspace,
}: UploadRunPanelProps) {
  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    onFileSelected(event.target.files?.[0] ?? null);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    onFileSelected(event.dataTransfer.files?.[0] ?? null);
  }

  return (
    <section className="setup-panel">
      <div className="panel-heading">
        <h2>Open Review Workspace</h2>
        <p>Choose one trusted profile, drop or browse for one PDF, then go straight into review.</p>
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
          <strong>{selectedFileName || upload?.original_filename || "Drop a PDF here or browse"}</strong>
          <small>
            {selectedFileName || upload
              ? "The current selection will be uploaded and opened in the review workspace."
              : "Choose a single job-cost PDF to process with the selected trusted profile."}
          </small>
          <input
            aria-label="Source report PDF"
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileChange}
            disabled={busy}
          />
        </label>

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
                <dt>Last file</dt>
                <dd>{upload?.original_filename ?? selectedFileName ?? "-"}</dd>
              </div>
            </dl>
          </div>
      </div>
      <div className="actions">
        <button
          type="button"
          onClick={onLaunchReviewWorkspace}
          disabled={busy || !selectedTrustedProfile || !(selectedFileName || upload)}
        >
          Open review workspace
        </button>
      </div>
    </section>
  );
}
