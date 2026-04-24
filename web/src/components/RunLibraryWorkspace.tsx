import { useEffect, useMemo, useState } from "react";

import type { ProcessingRunResponse } from "../api/contracts";

interface RunLibraryWorkspaceProps {
  openRuns: ProcessingRunResponse[];
  archivedRuns: ProcessingRunResponse[];
  busy: boolean;
  onRefresh: () => Promise<void> | void;
  onOpenLatestReviewed: (run: ProcessingRunResponse) => Promise<void> | void;
  onOpenOriginalProcessed: (run: ProcessingRunResponse) => Promise<void> | void;
  onArchiveRun: (run: ProcessingRunResponse) => Promise<void> | void;
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "Never";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function formatBlockerLabel(count: number): string {
  if (count === 0) {
    return "No blockers";
  }
  return `${count} blocker${count === 1 ? "" : "s"}`;
}

function RunListItem({
  run,
  selected,
  onSelect,
}: {
  run: ProcessingRunResponse;
  selected: boolean;
  onSelect: (run: ProcessingRunResponse) => void;
}) {
  return (
    <button
      type="button"
      className={selected ? "library-run-list-item active" : "library-run-list-item"}
      aria-label={`Select run ${run.source_document_filename}`}
      aria-pressed={selected}
      onClick={() => onSelect(run)}
    >
      <div className="library-run-list-main">
        <span className="library-run-title">{run.source_document_filename}</span>
        <span className="library-run-meta">
          {run.origin_profile_display_name ?? run.trusted_profile_name ?? "Unknown profile"} |{" "}
          {formatDateTime(run.created_at)}
        </span>
      </div>
      <div className="library-run-list-badges">
        <span className="status-pill neutral">{run.status}</span>
        <span className={run.aggregate_blockers.length > 0 ? "status-pill warning" : "status-pill success"}>
          {formatBlockerLabel(run.aggregate_blockers.length)}
        </span>
      </div>
    </button>
  );
}

function SelectedRunPanel({
  run,
  busy,
  onOpenLatestReviewed,
  onOpenOriginalProcessed,
  onArchiveRun,
}: {
  run: ProcessingRunResponse | null;
  busy: boolean;
  onOpenLatestReviewed: (run: ProcessingRunResponse) => Promise<void> | void;
  onOpenOriginalProcessed: (run: ProcessingRunResponse) => Promise<void> | void;
  onArchiveRun: (run: ProcessingRunResponse) => Promise<void> | void;
}) {
  if (!run) {
    return (
      <aside className="workspace-sidebar">
        <div className="workspace-sidebar-inner panel library-selected-panel">
          <p className="empty-state">Select a stored run to inspect lineage details and choose how to reopen it.</p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="workspace-sidebar">
      <div className="workspace-sidebar-inner panel library-selected-panel">
        <div className="sidebar-section">
          <p className="eyebrow">Selected Run</p>
          <h3>{run.source_document_filename}</h3>
          <p className="workspace-copy">
            {run.is_archived ? "Archived" : "Open"} run created {formatDateTime(run.created_at)}
          </p>
        </div>

        <dl className="summary-list library-selected-summary">
          <div>
            <dt>Origin profile</dt>
            <dd>{run.origin_profile_display_name ?? run.trusted_profile_name ?? "-"}</dd>
          </div>
          <div>
            <dt>Profile kind</dt>
            <dd>{run.origin_profile_source_kind ?? "-"}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{run.status}</dd>
          </div>
          <div>
            <dt>Records</dt>
            <dd>{run.record_count}</dd>
          </div>
          <div>
            <dt>Current revision</dt>
            <dd>{run.current_revision}</dd>
          </div>
          <div>
            <dt>Exports</dt>
            <dd>{run.export_count}</dd>
          </div>
          <div>
            <dt>Last export</dt>
            <dd>{formatDateTime(run.last_exported_at)}</dd>
          </div>
          <div>
            <dt>Blockers</dt>
            <dd>{formatBlockerLabel(run.aggregate_blockers.length)}</dd>
          </div>
        </dl>

        <div className="actions library-selected-actions">
          <button type="button" onClick={() => void onOpenLatestReviewed(run)} disabled={busy}>
            Open latest reviewed state
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => void onOpenOriginalProcessed(run)}
            disabled={busy}
          >
            Open original processed state
          </button>
          {!run.is_archived ? (
            <button
              type="button"
              className="secondary-button"
              onClick={() => void onArchiveRun(run)}
              disabled={busy}
            >
              Archive run
            </button>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

export function RunLibraryWorkspace({
  openRuns,
  archivedRuns,
  busy,
  onRefresh,
  onOpenLatestReviewed,
  onOpenOriginalProcessed,
  onArchiveRun,
}: RunLibraryWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<"open" | "archived">("open");
  const [selectedRunId, setSelectedRunId] = useState("");
  const runs = useMemo(
    () => (activeTab === "open" ? openRuns : archivedRuns),
    [activeTab, archivedRuns, openRuns],
  );
  const selectedRun = runs.find((run) => run.processing_run_id === selectedRunId) ?? runs[0] ?? null;

  useEffect(() => {
    setSelectedRunId((current) =>
      runs.some((run) => run.processing_run_id === current) ? current : runs[0]?.processing_run_id ?? "",
    );
  }, [runs]);

  return (
    <section className="workspace-shell library-shell">
      <div className="workspace-header">
        <div className="metric-card review-title-card">
          <p className="eyebrow">Run History</p>
          <h2>Run Library</h2>
          <p className="workspace-copy">
            Reopen stored runs without the original PDF, or archive completed runs to detach them from live profile drift checks.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="secondary-button" onClick={() => void onRefresh()} disabled={busy}>
            Refresh
          </button>
        </div>
      </div>

      <div className="workspace-toolbar review-workspace-toolbar library-tabs-toolbar">
        <div className="workspace-toggle" aria-label="Run library tabs">
          <button
            type="button"
            className={activeTab === "open" ? "toggle-button active" : "toggle-button"}
            aria-pressed={activeTab === "open"}
            onClick={() => setActiveTab("open")}
          >
            Open Runs
          </button>
          <button
            type="button"
            className={activeTab === "archived" ? "toggle-button active" : "toggle-button"}
            aria-pressed={activeTab === "archived"}
            onClick={() => setActiveTab("archived")}
          >
            Archived Runs
          </button>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="panel empty-workspace">
          <p className="empty-state">
            {activeTab === "open"
              ? "No open runs are available yet. Process a PDF to seed the library."
              : "No archived runs are available yet."}
          </p>
        </div>
      ) : (
        <div className="workspace-grid library-dashboard">
          <div className="workspace-main panel library-run-list-panel">
            <div className="panel-heading library-list-heading">
              <div>
                <p className="eyebrow">{activeTab === "open" ? "Open Runs" : "Archived Runs"}</p>
                <h3>{runs.length} stored run{runs.length === 1 ? "" : "s"}</h3>
              </div>
            </div>
            <div className="library-run-list">
              {runs.map((run) => (
                <RunListItem
                  key={run.processing_run_id}
                  run={run}
                  selected={selectedRun?.processing_run_id === run.processing_run_id}
                  onSelect={(nextRun) => setSelectedRunId(nextRun.processing_run_id)}
                />
              ))}
            </div>
          </div>
          <SelectedRunPanel
            run={selectedRun}
            busy={busy}
            onOpenLatestReviewed={onOpenLatestReviewed}
            onOpenOriginalProcessed={onOpenOriginalProcessed}
            onArchiveRun={onArchiveRun}
          />
        </div>
      )}
    </section>
  );
}
