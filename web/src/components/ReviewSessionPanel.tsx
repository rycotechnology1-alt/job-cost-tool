import type { ProcessingRunDetailResponse, ReviewSessionResponse } from "../api/contracts";

export interface ReviewEditFormValue {
  recordKey: string;
  vendorNameNormalized: string;
  recapLaborClassification: string;
  equipmentCategory: string;
  omissionChoice: "unchanged" | "omit" | "include";
}

interface ReviewSessionPanelProps {
  runDetail: ProcessingRunDetailResponse | null;
  reviewSession: ReviewSessionResponse | null;
  editForm: ReviewEditFormValue;
  busy: boolean;
  onOpenReviewSession: () => Promise<void> | void;
  onEditFormChange: (value: ReviewEditFormValue) => void;
  onApplyEditBatch: () => Promise<void> | void;
}

function recordDisplayValue(value: string | number | boolean | null): string {
  if (value === null || value === "") {
    return "—";
  }
  return String(value);
}

export function ReviewSessionPanel({
  runDetail,
  reviewSession,
  editForm,
  busy,
  onOpenReviewSession,
  onEditFormChange,
  onApplyEditBatch,
}: ReviewSessionPanelProps) {
  const runRecordKeys = runDetail?.run_records.map((record) => record.record_key) ?? [];
  const reviewRows =
    reviewSession?.records.map((record, index) => ({
      recordKey: runDetail?.run_records[index]?.record_key ?? `row-${index}`,
      record,
    })) ?? [];

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>3. Review Session</h2>
        <p>Open the run’s review session, inspect the current revision, and submit append-only edit deltas.</p>
      </div>
      <div className="actions">
        <button type="button" onClick={onOpenReviewSession} disabled={busy || !runDetail}>
          Open review session
        </button>
      </div>
      {!reviewSession ? (
        <p className="empty-state">Open the run’s review session to inspect effective records and append edits.</p>
      ) : (
        <>
          <dl className="summary-list compact">
            <div>
              <dt>Review session</dt>
              <dd>{reviewSession.review_session_id}</dd>
            </div>
            <div>
              <dt>Current revision</dt>
              <dd>{reviewSession.current_revision}</dd>
            </div>
            <div>
              <dt>Displayed revision</dt>
              <dd>{reviewSession.session_revision}</dd>
            </div>
            <div>
              <dt>Records</dt>
              <dd>{reviewSession.records.length}</dd>
            </div>
          </dl>
          <div className="status-block">
            <strong>Blocking issues</strong>
            {reviewSession.blocking_issues.length > 0 ? (
              <ul className="message-list">
                {reviewSession.blocking_issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            ) : (
              <p>No blocking issues.</p>
            )}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>record_key</th>
                  <th>Vendor</th>
                  <th>Labor class</th>
                  <th>Equipment</th>
                  <th>Omitted</th>
                  <th>Warnings</th>
                </tr>
              </thead>
              <tbody>
                {reviewRows.map(({ recordKey, record }) => (
                  <tr key={recordKey}>
                    <td>{recordKey}</td>
                    <td>{recordDisplayValue(record.vendor_name_normalized ?? record.vendor_name)}</td>
                    <td>{recordDisplayValue(record.recap_labor_classification)}</td>
                    <td>{recordDisplayValue(record.equipment_category)}</td>
                    <td>{record.is_omitted ? "yes" : "no"}</td>
                    <td>{record.warnings.length > 0 ? record.warnings.join("; ") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="edit-card">
            <h3>Append edit batch</h3>
            <div className="form-grid">
              <label className="field">
                <span>record_key</span>
                <select
                  value={editForm.recordKey}
                  onChange={(event) =>
                    onEditFormChange({
                      ...editForm,
                      recordKey: event.target.value,
                    })
                  }
                >
                  {runRecordKeys.map((recordKey) => (
                    <option key={recordKey} value={recordKey}>
                      {recordKey}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Vendor name</span>
                <input
                  value={editForm.vendorNameNormalized}
                  onChange={(event) =>
                    onEditFormChange({
                      ...editForm,
                      vendorNameNormalized: event.target.value,
                    })
                  }
                  placeholder="Vendor Edited"
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
                  placeholder="103 Journeyman"
                />
              </label>
              <label className="field">
                <span>Equipment category</span>
                <input
                  value={editForm.equipmentCategory}
                  onChange={(event) =>
                    onEditFormChange({
                      ...editForm,
                      equipmentCategory: event.target.value,
                    })
                  }
                  placeholder="Pick-up Truck"
                />
              </label>
              <label className="field">
                <span>Omission state</span>
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
              <button type="button" onClick={onApplyEditBatch} disabled={busy || runRecordKeys.length === 0}>
                Submit edit batch
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
