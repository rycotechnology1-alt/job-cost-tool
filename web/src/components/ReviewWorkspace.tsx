import { Fragment, useEffect, useState } from "react";

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
  selectedReviewRecordKeys: string[];
  editForm: ReviewEditFormValue;
  exportArtifact: ExportArtifactResponse | null;
  lastDownloadedFilename: string;
  exportDisabled: boolean;
  exportDisabledMessage: string;
  busy: boolean;
  onToggleReviewRowSelection: (recordKey: string, isSelected: boolean) => void;
  onSelectRow: (recordKey: string) => void;
  onEditFormChange: (value: ReviewEditFormValue) => void;
  onApplyEditBatch: () => Promise<void> | void;
  onApplyBulkOmission: (nextOmissionState: boolean) => Promise<void> | void;
  onApplyBulkLaborClassification: (targetClassification: string) => Promise<void> | void;
  onApplyBulkEquipmentCategory: (targetCategory: string) => Promise<void> | void;
  onExportAndDownload: () => Promise<void> | void;
}

interface ReviewFamilyGroup {
  familyKey: string;
  label: string;
  rows: WorkspaceRow[];
  rawCost: number;
  includedCost: number;
  omittedCost: number;
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

function buildSelectChoices(options: string[], currentValue: string): Array<{ value: string; label: string; disabled?: boolean }> {
  const trimmedCurrent = currentValue.trim();
  const hasCurrentValue = trimmedCurrent.length > 0;
  const normalizedOptions = new Set(options.map((option) => option.trim().toLocaleLowerCase()));
  const choices: Array<{ value: string; label: string; disabled?: boolean }> = [
    { value: "", label: "No override" },
  ];

  if (hasCurrentValue && !normalizedOptions.has(trimmedCurrent.toLocaleLowerCase())) {
    choices.push({
      value: trimmedCurrent,
      label: `${trimmedCurrent} (legacy invalid value)`,
      disabled: true,
    });
  }

  for (const option of options) {
    choices.push({ value: option, label: option });
  }
  return choices;
}

function isLaborBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType === "labor";
}

function isEquipmentBulkCompatibleRow(row: WorkspaceRow): boolean {
  const normalizedType = (row.record.record_type_normalized ?? row.record.record_type ?? "").trim().toLowerCase();
  return normalizedType === "equipment";
}

function formatFamilyLabel(value: string | null | undefined): string {
  const normalized = String(value ?? "unknown")
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");

  if (!normalized) {
    return "Unknown";
  }

  return normalized
    .split(" ")
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function buildFamilyKey(row: WorkspaceRow): string {
  const rawValue = row.record.record_type_normalized ?? row.record.record_type ?? "unknown";
  return String(rawValue).trim().toLocaleLowerCase() || "unknown";
}

function buildFamilyGroups(rows: WorkspaceRow[]): ReviewFamilyGroup[] {
  const groups = new Map<string, ReviewFamilyGroup>();

  for (const row of rows) {
    const familyKey = buildFamilyKey(row);
    const cost = typeof row.record.cost === "number" ? row.record.cost : 0;
    const existingGroup = groups.get(familyKey);
    if (existingGroup) {
      existingGroup.rows.push(row);
      existingGroup.rawCost += cost;
      if (row.record.is_omitted) {
        existingGroup.omittedCost += cost;
      } else {
        existingGroup.includedCost += cost;
      }
      continue;
    }

    groups.set(familyKey, {
      familyKey,
      label: formatFamilyLabel(row.record.record_type_normalized ?? row.record.record_type),
      rows: [row],
      rawCost: cost,
      includedCost: row.record.is_omitted ? 0 : cost,
      omittedCost: row.record.is_omitted ? cost : 0,
    });
  }

  return [...groups.values()];
}

export function ReviewWorkspace({
  runDetail,
  reviewSession,
  rows,
  selectedRow,
  selectedReviewRecordKeys,
  editForm,
  exportArtifact,
  lastDownloadedFilename,
  exportDisabled,
  exportDisabledMessage,
  busy,
  onToggleReviewRowSelection,
  onSelectRow,
  onEditFormChange,
  onApplyEditBatch,
  onApplyBulkOmission,
  onApplyBulkLaborClassification,
  onApplyBulkEquipmentCategory,
  onExportAndDownload,
}: ReviewWorkspaceProps) {
  const currentBlockers = reviewSession?.blocking_issues ?? [];
  const aggregateBlockers = runDetail?.aggregate_blockers ?? [];
  const exportRevision = reviewSession?.current_revision ?? 0;
  const selectedReviewRecordKeySet = new Set(selectedReviewRecordKeys);
  const laborChoices = buildSelectChoices(
    reviewSession?.labor_classification_options ?? [],
    editForm.recapLaborClassification,
  );
  const equipmentChoices = buildSelectChoices(
    reviewSession?.equipment_classification_options ?? [],
    editForm.equipmentCategory,
  );
  const hasInvalidLaborSelection =
    editForm.recapLaborClassification.trim().length > 0 &&
    !reviewSession?.labor_classification_options.some(
      (option) => option.trim().toLocaleLowerCase() === editForm.recapLaborClassification.trim().toLocaleLowerCase(),
    );
  const hasInvalidEquipmentSelection =
    editForm.equipmentCategory.trim().length > 0 &&
    !reviewSession?.equipment_classification_options.some(
      (option) => option.trim().toLocaleLowerCase() === editForm.equipmentCategory.trim().toLocaleLowerCase(),
    );
  const reviewTotals = rows.reduce(
    (totals, row) => {
      const cost = typeof row.record.cost === "number" ? row.record.cost : 0;
      totals.rawCost += cost;
      if (row.record.is_omitted) {
        totals.omittedCost += cost;
      } else {
        totals.includedCost += cost;
      }
      return totals;
    },
    {
      rawCost: 0,
      includedCost: 0,
      omittedCost: 0,
    },
  );
  const familyGroups = buildFamilyGroups(rows);
  const familyStateKey = familyGroups.map((group) => group.familyKey).join("|");
  const selectedReviewRows = rows.filter((row) => selectedReviewRecordKeySet.has(row.recordKey));
  const canBulkOmit = selectedReviewRows.some((row) => !row.record.is_omitted);
  const canBulkInclude = selectedReviewRows.some((row) => row.record.is_omitted);
  const [bulkLaborClassification, setBulkLaborClassification] = useState("");
  const [bulkEquipmentCategory, setBulkEquipmentCategory] = useState("");
  const [expandedFamilies, setExpandedFamilies] = useState<Record<string, boolean>>({});
  const laborCompatibleSelection = selectedReviewRows.length > 0 && selectedReviewRows.every(isLaborBulkCompatibleRow);
  const equipmentCompatibleSelection = selectedReviewRows.length > 0 && selectedReviewRows.every(isEquipmentBulkCompatibleRow);
  const canBulkApplyLaborClassification =
    laborCompatibleSelection &&
    bulkLaborClassification.trim().length > 0 &&
    selectedReviewRows.some((row) => (row.record.recap_labor_classification ?? "").trim() !== bulkLaborClassification.trim());
  const canBulkApplyEquipmentCategory =
    equipmentCompatibleSelection &&
    bulkEquipmentCategory.trim().length > 0 &&
    selectedReviewRows.some((row) => (row.record.equipment_category ?? "").trim() !== bulkEquipmentCategory.trim());

  useEffect(() => {
    setExpandedFamilies((current) => {
      const nextState: Record<string, boolean> = {};
      for (const group of familyGroups) {
        nextState[group.familyKey] = current[group.familyKey] ?? false;
      }
      return nextState;
    });
  }, [familyStateKey]);

  useEffect(() => {
    if (selectedReviewRows.length === 0) {
      setBulkLaborClassification("");
      setBulkEquipmentCategory("");
    }
  }, [selectedReviewRows.length]);

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
          <div>
            <dt>Full raw total</dt>
            <dd>{formatCurrency(reviewTotals.rawCost)}</dd>
          </div>
          <div>
            <dt>Included total</dt>
            <dd>{formatCurrency(reviewTotals.includedCost)}</dd>
          </div>
          <div>
            <dt>Omitted total</dt>
            <dd>{formatCurrency(reviewTotals.omittedCost)}</dd>
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
            {exportDisabledMessage ? (
              <div className="banner warning" role="status">
                <strong>Review context is stale for export.</strong>
                <p>{exportDisabledMessage}</p>
              </div>
            ) : null}
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

            <div className="review-bulk-bar">
              <div>
                <strong>{selectedReviewRecordKeys.length} row{selectedReviewRecordKeys.length === 1 ? "" : "s"} selected</strong>
                <p className="muted">Rows stay grouped by family. Use bulk omit/include or apply one shared target to the current selection.</p>
              </div>
              <div className="actions review-bulk-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onApplyBulkOmission(true)}
                  disabled={busy || selectedReviewRecordKeys.length === 0 || !canBulkOmit}
                >
                  Bulk omit selected
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onApplyBulkOmission(false)}
                  disabled={busy || selectedReviewRecordKeys.length === 0 || !canBulkInclude}
                >
                  Bulk include selected
                </button>
                <label className="field bulk-field">
                  <span>Bulk labor class</span>
                  <select
                    aria-label="Bulk labor classification"
                    value={bulkLaborClassification}
                    onChange={(event) => setBulkLaborClassification(event.target.value)}
                    disabled={busy || selectedReviewRecordKeys.length === 0}
                  >
                    <option value="">Choose labor class</option>
                    {reviewSession.labor_classification_options.map((option) => (
                      <option key={`bulk-labor-${option}`} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onApplyBulkLaborClassification(bulkLaborClassification)}
                  disabled={busy || !canBulkApplyLaborClassification}
                >
                  Apply labor class
                </button>
                <label className="field bulk-field">
                  <span>Bulk equipment class</span>
                  <select
                    aria-label="Bulk equipment category"
                    value={bulkEquipmentCategory}
                    onChange={(event) => setBulkEquipmentCategory(event.target.value)}
                    disabled={busy || selectedReviewRecordKeys.length === 0}
                  >
                    <option value="">Choose equipment class</option>
                    {reviewSession.equipment_classification_options.map((option) => (
                      <option key={`bulk-equipment-${option}`} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onApplyBulkEquipmentCategory(bulkEquipmentCategory)}
                  disabled={busy || !canBulkApplyEquipmentCategory}
                >
                  Apply equipment class
                </button>
              </div>
            </div>
            {selectedReviewRows.length > 0 && !laborCompatibleSelection ? (
              <p className="muted bulk-hint">Bulk labor classification works only when every selected row is a labor row.</p>
            ) : null}
            {selectedReviewRows.length > 0 && !equipmentCompatibleSelection ? (
              <p className="muted bulk-hint">Bulk equipment category works only when every selected row is an equipment row.</p>
            ) : null}

            <div className="table-wrap workspace-table-wrap">
              <table className="review-table">
                <thead>
                  <tr>
                    <th>Select</th>
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
                  {familyGroups.map((group) => {
                    const isExpanded = expandedFamilies[group.familyKey] ?? false;
                    return (
                      <Fragment key={group.familyKey}>
                        <tr key={`${group.familyKey}-group`} className="review-group-row">
                          <td colSpan={8}>
                            <button
                              type="button"
                              className="review-group-toggle"
                              aria-expanded={isExpanded}
                              onClick={() =>
                                setExpandedFamilies((current) => ({
                                  ...current,
                                  [group.familyKey]: !(current[group.familyKey] ?? false),
                                }))
                              }
                            >
                              <span className="review-group-title">
                                {isExpanded ? "Hide" : "Show"} {group.label}
                              </span>
                              <span>{group.rows.length} rows</span>
                              <span>Raw {formatCurrency(group.rawCost)}</span>
                              <span>Included {formatCurrency(group.includedCost)}</span>
                              {group.omittedCost > 0 ? <span>Omitted {formatCurrency(group.omittedCost)}</span> : null}
                            </button>
                          </td>
                        </tr>
                        {isExpanded
                          ? group.rows.map((row) => {
                              const currentType = row.record.record_type_normalized ?? row.record.record_type;
                              const currentVendor = row.record.vendor_name_normalized ?? row.record.vendor_name;
                              const currentLabor =
                                row.record.recap_labor_classification ??
                                row.record.labor_class_normalized ??
                                row.record.labor_class_raw;
                              const currentEquipment = row.record.equipment_category ?? row.record.equipment_description;
                              const warningClass = row.record.warnings.length > 0 ? "warning" : "";
                              const omittedClass = row.record.is_omitted ? "omitted" : "";
                              const selectedClass = selectedRow?.recordKey === row.recordKey ? "selected" : "";
                              const bulkSelectedClass = selectedReviewRecordKeySet.has(row.recordKey) ? "bulk-selected" : "";
                              return (
                                <tr
                                  key={row.recordKey}
                                  className={`workspace-row ${selectedClass} ${warningClass} ${omittedClass} ${bulkSelectedClass}`.trim()}
                                  onClick={() => onSelectRow(row.recordKey)}
                                  aria-selected={selectedRow?.recordKey === row.recordKey}
                                >
                                  <td onClick={(event) => event.stopPropagation()}>
                                    <input
                                      aria-label={`Select ${row.record.raw_description || row.recordKey}`}
                                      type="checkbox"
                                      checked={selectedReviewRecordKeySet.has(row.recordKey)}
                                      onChange={(event) => onToggleReviewRowSelection(row.recordKey, event.target.checked)}
                                    />
                                  </td>
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
                            })
                          : null}
                      </Fragment>
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
                    <p className="muted">
                      Labor and equipment edits must use the target classifications captured in this run&apos;s trusted
                      profile snapshot.
                    </p>
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
                        <select
                          value={editForm.recapLaborClassification}
                          onChange={(event) =>
                            onEditFormChange({
                              ...editForm,
                              recapLaborClassification: event.target.value,
                            })
                          }
                        >
                          {laborChoices.map((choice) => (
                            <option key={`labor-${choice.value || "blank"}`} value={choice.value} disabled={choice.disabled}>
                              {choice.label}
                            </option>
                          ))}
                        </select>
                        {hasInvalidLaborSelection ? (
                          <span className="field-error">
                            This review currently contains a legacy labor classification that is outside the run&apos;s
                            trusted profile list. Choose a configured labor classification or leave it blank.
                          </span>
                        ) : null}
                      </label>
                      <label className="field">
                        <span>Equipment class</span>
                        <select
                          value={editForm.equipmentCategory}
                          onChange={(event) =>
                            onEditFormChange({
                              ...editForm,
                              equipmentCategory: event.target.value,
                            })
                          }
                        >
                          {equipmentChoices.map((choice) => (
                            <option
                              key={`equipment-${choice.value || "blank"}`}
                              value={choice.value}
                              disabled={choice.disabled}
                            >
                              {choice.label}
                            </option>
                          ))}
                        </select>
                        {hasInvalidEquipmentSelection ? (
                          <span className="field-error">
                            This review currently contains a legacy equipment classification that is outside the run&apos;s
                            trusted profile list. Choose a configured equipment classification or leave it blank.
                          </span>
                        ) : null}
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
                    {exportDisabledMessage ? (
                      <p className="field-error">{exportDisabledMessage}</p>
                    ) : null}
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
                      <button type="button" onClick={onExportAndDownload} disabled={busy || exportDisabled}>
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
