import type { ChangeEvent } from "react";

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
  onUpload: () => Promise<void> | void;
  onStartRun: () => Promise<void> | void;
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
  onUpload,
  onStartRun,
}: UploadRunPanelProps) {
  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    onFileSelected(event.target.files?.[0] ?? null);
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>1. Upload And Run</h2>
        <p>Upload one report, choose one read-only trusted profile, then start one immutable processing run.</p>
      </div>
      <div className="form-grid">
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
        <label className="field">
          <span>Source report PDF</span>
          <input type="file" accept=".pdf,application/pdf" onChange={handleFileChange} disabled={busy} />
        </label>
      </div>
      <div className="actions">
        <button type="button" onClick={onUpload} disabled={busy}>
          Upload report
        </button>
        <button
          type="button"
          className="secondary"
          onClick={onStartRun}
          disabled={busy || !upload || !selectedTrustedProfile}
        >
          Start processing run
        </button>
      </div>
      <div className="summary-card">
        <strong>Selected trusted profile</strong>
        {selectedTrustedProfile ? (
          <dl className="summary-list">
            <div>
              <dt>Name</dt>
              <dd>{selectedTrustedProfile.display_name}</dd>
            </div>
            <div>
              <dt>Profile key</dt>
              <dd>{selectedTrustedProfile.profile_name}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{selectedTrustedProfile.version_label ?? "—"}</dd>
            </div>
            <div>
              <dt>Template</dt>
              <dd>{selectedTrustedProfile.template_filename ?? "—"}</dd>
            </div>
            <div>
              <dt>Description</dt>
              <dd>{selectedTrustedProfile.description || "No description."}</dd>
            </div>
          </dl>
        ) : (
          <p>No trusted profile is available for selection.</p>
        )}
      </div>
      <div className="summary-card">
        <strong>Current upload</strong>
        {upload ? (
          <dl className="summary-list">
            <div>
              <dt>Upload id</dt>
              <dd>{upload.upload_id}</dd>
            </div>
            <div>
              <dt>Filename</dt>
              <dd>{upload.original_filename}</dd>
            </div>
            <div>
              <dt>Bytes</dt>
              <dd>{upload.file_size_bytes}</dd>
            </div>
          </dl>
        ) : (
          <p>{selectedFileName ? `Ready to upload ${selectedFileName}.` : "No report uploaded yet."}</p>
        )}
      </div>
    </section>
  );
}
