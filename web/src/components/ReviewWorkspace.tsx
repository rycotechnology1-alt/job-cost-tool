import type {
  ExportArtifactResponse,
  ProcessingRunDetailResponse,
  ReviewSessionResponse,
} from "../api/contracts";

export interface ReviewEditFormValue {
  vendorNameNormalized: string;
  recapLaborClassification: string;
  equipmentCategory: string;
  omissionChoice: "unchanged" | "omit" | "include";
}

export interface WorkspaceRow {
  recordKey: string;
  recordIndex: number;
  sourcePage: number | null;
  sourceLineText: string | null;
  record: ReviewSessionResponse["records"][number];
  canonicalRecord: ProcessingRunDetailResponse["run_records"][number]["canonical_record"];
}

interface ReviewWorkspaceProps {
  runDetail: ProcessingRunDetailResponse | null;
  reviewSession: ReviewSessionResponse | null;
  rows: WorkspaceRow[];
  selectedRow: WorkspaceRow | null;
  editForm: ReviewEditFormValue;
  exportArtifact: ExportArtifactResponse | null;
  lastDownloadedFilename: string;
  busy: boolean;
  onSelectRow: (recordKey: string) => void;
  onEditFormChange: (value: ReviewEditFormValue) => void;
  onApplyEditBatch: () => Promise<void> | void;
  onExportAndDownload: () => Promise<void> | void;
}

function renderPrimary(value: string | number | null | undefined, fallback = "-"): string {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatSourceLabel(row: WorkspaceRow): string {
  const pageText = row.sourcePage ? `Page ${row.sourcePage}` : "Page -";
  const phaseText = row.record.phase_code ? `Phase ${row.record.phase_code}` : "Phase -";
  return `${pageText} | ${phaseText}`;
}

function buildAttentionSummary(row: WorkspaceRow): string {
  if (row.record.warnings.length > 0) {
    return `${row.record.warnings.length} warning${row.record.warnings.length === 1 ? "" : "s"}`;
  }
  if (row.record.is_omitted) {
    return "Omitted";
  }
  return "Ready";
}

export function ReviewWorkspace({
  runDetail,
  reviewSession,
  rows,
  selectedRow,
  editForm,
  exportArtifact,
  lastDownloadedFilename,
  busy,
  onSelectRow,
  onEditFormChange,
  onApplyEditBatch,
  onExportAndDownload,
}: ReviewWorkspaceProps) {
  const currentBlockers = reviewSession?.blocking_issues ?? [];
  const aggregateBlockers = runDetail?.aggregate_blockers ?? [];
  const exportRevision = reviewSession?.current_revision ?? 0;

  return (
    <section className="workspace-shell">
      <div className="workspace-header">
        <div>
          <p className="eyebrow">Review Workspace</p>
          <h2>{runDetail?.source_document_filename ?? "Choose a file to begin review"}</h2>
          <p className="workspace-copy">
            Review the current row set, inspect source context, apply one append-only edit at a time, and export the
            current revision when you trust the result.
          </p>
        </div>
        <dl className="summary-list compact workspace-metrics">
          <div>
            <dt>Trusted profile</dt>
            <dd>{runDetail?.trusted_profile_name ?? "-"}</dd>
          </div>
          <div>
            <dt>Records</dt>
            <dd>{reviewSession?.records.length ?? runDetail?.record_count ?? 0}</dd>
          </div>
          <div>
            <dt>Current revision</dt>
            <dd>{reviewSession?.current_revision ?? "-"}</dd>
          </div>
          <div>
            <dt>Run status</dt>
            <dd>{runDetail?.status ?? "Waiting"}</dd>
          </div>
        </dl>
      </div>

      {!runDetail || !reviewSession ? (
        <div className="panel empty-workspace">
          <p className="empty-state">Open a report in the review workspace to inspect rows and apply corrections.</p>
        </div>
      ) : (
        <div className="workspace-grid">
          <div className="workspace-main panel">
            {currentBlockers.length > 0 ? (
              <div className="banner warning">
                <strong>Current blockers</strong>
                <ul className="message-list">
                  {currentBlockers.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="workspace-callout success">
                <strong>No current blockers.</strong>
                <p>The current review revision is exportable under the accepted workflow.</p>
              </div>
            )}

            <div className="table-wrap workspace-table-wrap">
              <table className="review-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Vendor</th>
                    <th>Labor Class</th>
                    <th>Equipment Class</th>
                    <th>Cost</th>
                    <th>Source</th>
                    <th>Attention</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const currentType = row.record.record_type_normalized ?? row.record.record_type;
                    const currentVendor = row.record.vendor_name_normalized ?? row.record.vendor_name;
                    const currentLabor =
                      row.record.recap_labor_classification ?? row.record.labor_class_normalized ?? row.record.labor_class_raw;
                    const currentEquipment = row.record.equipment_category ?? row.record.equipment_description;
                    const warningClass = row.record.warnings.length > 0 ? "warning" : "";
                    const omittedClass = row.record.is_omitted ? "omitted" : "";
                    const selectedClass = selectedRow?.recordKey === row.recordKey ? "selected" : "";
                    return (
                      <tr
                        key={row.recordKey}
                        className={`workspace-row ${selectedClass} ${warningClass} ${omittedClass}`.trim()}
                        onClick={() => onSelectRow(row.recordKey)}
                        aria-selected={selectedRow?.recordKey === row.recordKey}
                      >
                        <td>
                          <div className="cell-primary">{renderPrimary(currentType)}</div>
                          <div className="cell-secondary">{renderPrimary(row.record.record_type, "-")}</div>
                        </td>
                        <td>
                          <div className="cell-primary">{renderPrimary(currentVendor)}</div>
                          <div className="cell-secondary">
                            {renderPrimary(row.record.vendor_name ?? row.record.vendor_id_raw)}
                          </div>
                        </td>
                        <td>
                          <div className="cell-primary">{renderPrimary(currentLabor)}</div>
                          <div className="cell-secondary">{renderPrimary(row.record.labor_class_raw)}</div>
                        </td>
                        <td>
                          <div className="cell-primary">{renderPrimary(currentEquipment)}</div>
                          <div className="cell-secondary">{renderPrimary(row.record.equipment_description)}</div>
                        </td>
                        <td>
                          <div className="cell-primary">{formatCurrency(row.record.cost)}</div>
                          <div className="cell-secondary">
                            {row.record.hours ? `${row.record.hours} ${row.record.hour_type ?? "hrs"}` : "-"}
                          </div>
                        </td>
                        <td>
                          <div className="cell-primary">{renderPrimary(row.record.raw_description)}</div>
                          <div className="cell-secondary">{formatSourceLabel(row)}</div>
                        </td>
                        <td>
                          <div className="attention-pill">{buildAttentionSummary(row)}</div>
                          <div className="cell-secondary">{row.record.is_omitted ? "Hidden from export" : "Included"}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <aside className="workspace-sidebar">
            <div className="workspace-sidebar-inner panel">
              {!selectedRow ? (
                <p className="empty-state">Select a row to inspect its source context and apply edits.</p>
              ) : (
                <>
                  <div className="sidebar-section">
                    <p className="eyebrow">Selected Row</p>
                    <h3>{renderPrimary(selectedRow.record.vendor_name_normalized ?? selectedRow.record.raw_description)}</h3>
                    <p className="workspace-copy">{formatSourceLabel(selectedRow)}</p>
                  </div>

                  <div className="status-block">
                    <strong>Current row warnings</strong>
                    {selectedRow.record.warnings.length > 0 ? (
                      <ul className="message-list">
                        {selectedRow.record.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>No row warnings.</p>
                    )}
                  </div>

                  <div className="summary-card">
                    <strong>Current values</strong>
                    <dl className="summary-list">
                      <div>
                        <dt>Type</dt>
                        <dd>{renderPrimary(selectedRow.record.record_type_normalized ?? selectedRow.record.record_type)}</dd>
                      </div>
                      <div>
                        <dt>Vendor</dt>
                        <dd>{renderPrimary(selectedRow.record.vendor_name_normalized ?? selectedRow.record.vendor_name)}</dd>
                      </div>
                      <div>
                        <dt>Labor class</dt>
                        <dd>
                          {renderPrimary(
                            selectedRow.record.recap_labor_classification ??
                              selectedRow.record.labor_class_normalized ??
                              selectedRow.record.labor_class_raw,
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Equipment class</dt>
                        <dd>{renderPrimary(selectedRow.record.equipment_category ?? selectedRow.record.equipment_description)}</dd>
                      </div>
                      <div>
                        <dt>Cost</dt>
                        <dd>{formatCurrency(selectedRow.record.cost)}</dd>
                      </div>
                      <div>
                        <dt>Omission</dt>
                        <dd>{selectedRow.record.is_omitted ? "Currently omitted" : "Currently included"}</dd>
                      </div>
                    </dl>
                  </div>

                  <div className="summary-card">
                    <strong>Raw and parsed context</strong>
                    <dl className="summary-list">
                      <div>
                        <dt>Raw description</dt>
                        <dd>{renderPrimary(selectedRow.record.raw_description)}</dd>
                      </div>
                      <div>
                        <dt>Source line</dt>
                        <dd>{renderPrimary(selectedRow.sourceLineText ?? selectedRow.record.source_line_text)}</dd>
                      </div>
                      <div>
                        <dt>Vendor parsed</dt>
                        <dd>{renderPrimary(selectedRow.record.vendor_name ?? selectedRow.record.vendor_id_raw)}</dd>
                      </div>
                      <div>
                        <dt>Labor parsed</dt>
                        <dd>{renderPrimary(selectedRow.record.labor_class_raw)}</dd>
                      </div>
                      <div>
                        <dt>Equipment parsed</dt>
                        <dd>{renderPrimary(selectedRow.record.equipment_description)}</dd>
                      </div>
                      <div>
                        <dt>Confidence</dt>
                        <dd>{renderPrimary(selectedRow.record.confidence)}</dd>
                      </div>
                    </dl>
                  </div>

                  <div className="edit-card">
                    <h3>Edit selected row</h3>
                    <div className="form-grid">
                      <label className="field">
                        <span>Vendor</span>
                        <input
                          value={editForm.vendorNameNormalized}
                          onChange={(event) =>
                            onEditFormChange({
                              ...editForm,
                              vendorNameNormalized: event.target.value,
                            })
                          }
                          placeholder="Vendor name"
                        />
                      </label>
                      <label className="field">
                        <span>Labor class</span>
                        <input
                          value={editForm.recapLaborClassification}
                          onChange={(event) =>
                            onEditFormChange({
                              ...editForm,
                              recapLaborClassification: event.target.value,
                            })
                          }
                          placeholder="Recap labor class"
                        />
                      </label>
                      <label className="field">
                        <span>Equipment class</span>
                        <input
                          value={editForm.equipmentCategory}
                          onChange={(event) =>
                            onEditFormChange({
                              ...editForm,
                              equipmentCategory: event.target.value,
                            })
                          }
                          placeholder="Equipment class"
                        />
                      </label>
                      <label className="field">
                        <span>Omission</span>
                        <select
                          value={editForm.omissionChoice}
                          onChange={(event) =>
                            onEditFormChange({
                              ...editForm,
                              omissionChoice: event.target.value as ReviewEditFormValue["omissionChoice"],
                            })
                          }
                        >
                          <option value="unchanged">Leave unchanged</option>
                          <option value="omit">Mark omitted</option>
                          <option value="include">Mark included</option>
                        </select>
                      </label>
                    </div>
                    <div className="actions">
                      <button type="button" onClick={onApplyEditBatch} disabled={busy}>
                        Apply review change
                      </button>
                    </div>
                  </div>

                  <div className="summary-card export-card">
                    <strong>Export workbook</strong>
                    <p>Downloads the current review revision and keeps exact-revision lineage under the hood.</p>
                    <dl className="summary-list compact">
                      <div>
                        <dt>Current revision</dt>
                        <dd>{exportRevision}</dd>
                      </div>
                      <div>
                        <dt>Historical export</dt>
                        <dd>{reviewSession.historical_export_status.is_reproducible ? "Ready" : "Legacy only"}</dd>
                      </div>
                      <div>
                        <dt>Last workbook</dt>
                        <dd>{lastDownloadedFilename || "None yet"}</dd>
                      </div>
                    </dl>
                    <div className="actions">
                      <button type="button" onClick={onExportAndDownload} disabled={busy}>
                        Export and download workbook
                      </button>
                    </div>
                    {exportArtifact ? (
                      <p className="muted">
                        Last export used review revision {exportArtifact.session_revision}.
                      </p>
                    ) : null}
                  </div>

                  <details className="system-details">
                    <summary>System details</summary>
                    <dl className="summary-list">
                      <div>
                        <dt>Processing blockers</dt>
                        <dd>{aggregateBlockers.length > 0 ? aggregateBlockers.join("; ") : "None"}</dd>
                      </div>
                      <div>
                        <dt>Processing run id</dt>
                        <dd>{runDetail.processing_run_id}</dd>
                      </div>
                      <div>
                        <dt>Review session id</dt>
                        <dd>{reviewSession.review_session_id}</dd>
                      </div>
                      <div>
                        <dt>Selected row key</dt>
                        <dd>{selectedRow.recordKey}</dd>
                      </div>
                      {exportArtifact ? (
                        <div>
                          <dt>Last export id</dt>
                          <dd>{exportArtifact.export_artifact_id}</dd>
                        </div>
                      ) : null}
                    </dl>
                  </details>
                </>
              )}
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}
