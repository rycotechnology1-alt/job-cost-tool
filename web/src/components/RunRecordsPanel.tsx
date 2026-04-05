import type { ProcessingRunDetailResponse } from "../api/contracts";

interface RunRecordsPanelProps {
  runDetail: ProcessingRunDetailResponse | null;
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return value.toString();
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

export function RunRecordsPanel({ runDetail }: RunRecordsPanelProps) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>2. Processing Run</h2>
        <p>The backend remains the source of truth for immutable run status, ordered run records, and blockers.</p>
      </div>
      {!runDetail ? (
        <p className="empty-state">Start a processing run to inspect immutable records and aggregate blockers.</p>
      ) : (
        <>
          <dl className="summary-list compact">
            <div>
              <dt>Run id</dt>
              <dd>{runDetail.processing_run_id}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{runDetail.status}</dd>
            </div>
            <div>
              <dt>Trusted profile</dt>
              <dd>{runDetail.trusted_profile_name ?? "—"}</dd>
            </div>
            <div>
              <dt>Records</dt>
              <dd>{runDetail.record_count}</dd>
            </div>
          </dl>
          <div className="status-block">
            <strong>Aggregate blockers</strong>
            {runDetail.aggregate_blockers.length > 0 ? (
              <ul className="message-list">
                {runDetail.aggregate_blockers.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            ) : (
              <p>No aggregate blockers.</p>
            )}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>record_key</th>
                  <th>Type</th>
                  <th>Phase</th>
                  <th>Vendor</th>
                  <th>Cost</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {runDetail.run_records.map((record) => (
                  <tr key={record.run_record_id}>
                    <td>{record.record_key}</td>
                    <td>{renderValue(record.canonical_record.record_type_normalized ?? record.canonical_record.record_type)}</td>
                    <td>{renderValue(record.canonical_record.phase_code)}</td>
                    <td>{renderValue(record.canonical_record.vendor_name_normalized ?? record.canonical_record.vendor_name)}</td>
                    <td>{renderValue(record.canonical_record.cost)}</td>
                    <td>{renderValue(record.source_line_text)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
