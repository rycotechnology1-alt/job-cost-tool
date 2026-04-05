import type { ExportArtifactResponse, ReviewSessionResponse } from "../api/contracts";

interface ExportPanelProps {
  reviewSession: ReviewSessionResponse | null;
  exportArtifact: ExportArtifactResponse | null;
  requestedRevision: string;
  busy: boolean;
  onRequestedRevisionChange: (value: string) => void;
  onRequestExport: () => Promise<void> | void;
  onDownloadArtifact: () => Promise<void> | void;
}

export function ExportPanel({
  reviewSession,
  exportArtifact,
  requestedRevision,
  busy,
  onRequestedRevisionChange,
  onRequestExport,
  onDownloadArtifact,
}: ExportPanelProps) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>4. Export</h2>
        <p>Request one export bound to an exact session revision, then download the resulting artifact.</p>
      </div>
      {!reviewSession ? (
        <p className="empty-state">Open the review session before requesting an exact-revision export.</p>
      ) : (
        <>
          <div className="form-grid">
            <label className="field">
              <span>session_revision</span>
              <input
                value={requestedRevision}
                onChange={(event) => onRequestedRevisionChange(event.target.value)}
                inputMode="numeric"
              />
            </label>
          </div>
          <div className="actions">
            <button type="button" onClick={onRequestExport} disabled={busy}>
              Request export
            </button>
            <button type="button" className="secondary" onClick={onDownloadArtifact} disabled={busy || !exportArtifact}>
              Download artifact
            </button>
          </div>
          <div className="summary-card">
            <strong>Current export artifact</strong>
            {exportArtifact ? (
              <dl className="summary-list">
                <div>
                  <dt>Artifact id</dt>
                  <dd>{exportArtifact.export_artifact_id}</dd>
                </div>
                <div>
                  <dt>Revision</dt>
                  <dd>{exportArtifact.session_revision}</dd>
                </div>
                <div>
                  <dt>Template artifact</dt>
                  <dd>{exportArtifact.template_artifact_id ?? "—"}</dd>
                </div>
                <div>
                  <dt>Download</dt>
                  <dd>{exportArtifact.download_url}</dd>
                </div>
              </dl>
            ) : (
              <p>No export artifact requested yet.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}
