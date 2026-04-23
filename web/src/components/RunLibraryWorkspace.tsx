import { useMemo, useState } from "react";

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

function RunCard({
  run,
  busy,
  allowArchive,
  onOpenLatestReviewed,
  onOpenOriginalProcessed,
  onArchiveRun,
}: {
  run: ProcessingRunResponse;
  busy: boolean;
  allowArchive: boolean;
  onOpenLatestReviewed: (run: ProcessingRunResponse) => Promise<void> | void;
  onOpenOriginalProcessed: (run: ProcessingRunResponse) => Promise<void> | void;
  onArchiveRun: (run: ProcessingRunResponse) => Promise<void> | void;
}) {
  return (
    <article className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{run.is_archived ? "Archived" : "Open"} Run</p>
          <h3>{run.source_document_filename}</h3>
          <p>
            {run.origin_profile_display_name ?? run.trusted_profile_name ?? "Unknown profile"} · Created{" "}
            {formatDateTime(run.created_at)}
          </p>
        </div>
        <div className="status-pill neutral">{run.status}</div>
      </div>

      <dl className="summary-list compact">
        <div>
          <dt>Origin profile</dt>
          <dd>{run.origin_profile_display_name ?? run.trusted_profile_name ?? "-"}</dd>
        </div>
        <div>
          <dt>Profile kind</dt>
          <dd>{run.origin_profile_source_kind ?? "-"}</dd>
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

      <div className="actions">
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
        {allowArchive ? (
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
    </article>
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
  const runs = useMemo(
    () => (activeTab === "open" ? openRuns : archivedRuns),
    [activeTab, archivedRuns, openRuns],
  );

  return (
    <section className="workspace-shell">
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

      <div className="workspace-toolbar review-workspace-toolbar">
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
        <div className="workspace-grid">
          <div className="workspace-main">
            {runs.map((run) => (
              <RunCard
                key={run.processing_run_id}
                run={run}
                busy={busy}
                allowArchive={!run.is_archived}
                onOpenLatestReviewed={onOpenLatestReviewed}
                onOpenOriginalProcessed={onOpenOriginalProcessed}
                onArchiveRun={onArchiveRun}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
