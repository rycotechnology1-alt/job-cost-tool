import { type ReactNode, useEffect, useState } from "react";

import type {
  ClassificationSlotRow,
  DefaultOmitRuleRow,
  DraftEditorStateResponse,
  EquipmentMappingRow,
  EquipmentRateRow,
  LaborMappingRow,
  LaborRateRow,
  PublishedProfileDetailResponse,
  TrustedProfileResponse,
} from "../api/contracts";

interface ProfileSettingsWorkspaceProps {
  trustedProfiles: TrustedProfileResponse[];
  selectedTrustedProfileName: string;
  selectedTrustedProfile: TrustedProfileResponse | null;
  profileDetail: PublishedProfileDetailResponse | null;
  draftState: DraftEditorStateResponse | null;
  busy: boolean;
  onTrustedProfileNameChange: (value: string) => void;
  onOpenDraft: () => Promise<void> | void;
  onSaveDefaultOmit: (rows: DefaultOmitRuleRow[]) => Promise<void> | void;
  onSaveLaborMappings: (rows: LaborMappingRow[]) => Promise<void> | void;
  onSaveEquipmentMappings: (rows: EquipmentMappingRow[]) => Promise<void> | void;
  onSaveClassifications: (
    laborSlots: ClassificationSlotRow[],
    equipmentSlots: ClassificationSlotRow[],
  ) => Promise<void> | void;
  onSaveRates: (laborRates: LaborRateRow[], equipmentRates: EquipmentRateRow[]) => Promise<void> | void;
  onPublishDraft: () => Promise<void> | void;
  onCreateDesktopSyncExport: () => Promise<void> | void;
  lastDownloadedProfileSyncFilename: string;
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function emptyDefaultOmitRule(): DefaultOmitRuleRow {
  return { phase_code: "", phase_name: "" };
}

function emptyLaborMappingRow(): LaborMappingRow {
  return {
    raw_value: "",
    target_classification: "",
    notes: "",
    is_observed: false,
  };
}

function emptyEquipmentMappingRow(): EquipmentMappingRow {
  return {
    raw_description: "",
    target_category: "",
    is_observed: false,
  };
}

function findPhaseName(phaseCode: string, options: DefaultOmitRuleRow[]): string {
  const normalizedPhaseCode = phaseCode.trim();
  if (!normalizedPhaseCode) {
    return "";
  }
  return options.find((option) => option.phase_code === normalizedPhaseCode)?.phase_name ?? "";
}

function hasObservedUnmappedRows(
  laborMappings: LaborMappingRow[],
  equipmentMappings: EquipmentMappingRow[],
): boolean {
  return (
    laborMappings.some((row) => row.is_observed && !row.target_classification.trim()) ||
    equipmentMappings.some((row) => row.is_observed && !row.target_category.trim())
  );
}

function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-heading settings-heading">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {action ? <div className="settings-heading-action">{action}</div> : null}
    </div>
  );
}

function DeferredDomainCard({ title, payload }: { title: string; payload: Record<string, unknown> }) {
  return (
    <details className="system-details" open>
      <summary>{title}</summary>
      <pre className="json-block">{prettyJson(payload)}</pre>
    </details>
  );
}

function ObservedBadge() {
  return <span className="observed-badge">Observed</span>;
}

export function ProfileSettingsWorkspace({
  trustedProfiles,
  selectedTrustedProfileName,
  selectedTrustedProfile,
  profileDetail,
  draftState,
  busy,
  onTrustedProfileNameChange,
  onOpenDraft,
  onSaveDefaultOmit,
  onSaveLaborMappings,
  onSaveEquipmentMappings,
  onSaveClassifications,
  onSaveRates,
  onPublishDraft,
  onCreateDesktopSyncExport,
  lastDownloadedProfileSyncFilename,
}: ProfileSettingsWorkspaceProps) {
  const [defaultOmitRules, setDefaultOmitRules] = useState<DefaultOmitRuleRow[]>([]);
  const [laborMappings, setLaborMappings] = useState<LaborMappingRow[]>([]);
  const [equipmentMappings, setEquipmentMappings] = useState<EquipmentMappingRow[]>([]);
  const [laborSlots, setLaborSlots] = useState<ClassificationSlotRow[]>([]);
  const [equipmentSlots, setEquipmentSlots] = useState<ClassificationSlotRow[]>([]);
  const [laborRates, setLaborRates] = useState<LaborRateRow[]>([]);
  const [equipmentRates, setEquipmentRates] = useState<EquipmentRateRow[]>([]);

  useEffect(() => {
    if (!draftState) {
      setDefaultOmitRules([]);
      setLaborMappings([]);
      setEquipmentMappings([]);
      setLaborSlots([]);
      setEquipmentSlots([]);
      setLaborRates([]);
      setEquipmentRates([]);
      return;
    }
    setDefaultOmitRules(draftState.default_omit_rules.map((row) => ({ ...row })));
    setLaborMappings(draftState.labor_mappings.map((row) => ({ ...row })));
    setEquipmentMappings(draftState.equipment_mappings.map((row) => ({ ...row })));
    setLaborSlots(draftState.labor_slots.map((row) => ({ ...row })));
    setEquipmentSlots(draftState.equipment_slots.map((row) => ({ ...row })));
    setLaborRates(draftState.labor_rates.map((row) => ({ ...row })));
    setEquipmentRates(draftState.equipment_rates.map((row) => ({ ...row })));
  }, [draftState]);

  const detailToRender = draftState ?? profileDetail;
  const deferredDomains = detailToRender?.deferred_domains ?? null;
  const openDraftId = draftState?.trusted_profile_draft_id ?? profileDetail?.open_draft_id ?? null;
  const laborTargets = laborSlots.filter((row) => row.active && row.label.trim()).map((row) => row.label.trim());
  const equipmentTargets = equipmentSlots.filter((row) => row.active && row.label.trim()).map((row) => row.label.trim());
  const observedDraftNote = hasObservedUnmappedRows(laborMappings, equipmentMappings);

  return (
    <section className="workspace-shell settings-shell">
      <div className="workspace-header">
        <div>
          <p className="eyebrow">Profile Settings</p>
          <h2>{selectedTrustedProfile?.display_name ?? "Choose a trusted profile"}</h2>
          <p className="workspace-copy">
            Inspect the published trusted profile, open the single mutable draft, edit the approved Phase 2A settings
            slice, and publish a new immutable version for future processing.
          </p>
        </div>
        <div className="summary-card">
          <label className="field">
            <span>Trusted profile</span>
            <select
              aria-label="Settings trusted profile"
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
          <div className="actions">
            <button type="button" onClick={onOpenDraft} disabled={busy || !selectedTrustedProfile}>
              {openDraftId ? "Open current draft" : "Create draft from published version"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={onPublishDraft}
              disabled={busy || !draftState}
            >
              Publish draft
            </button>
          </div>
        </div>
      </div>

      {!selectedTrustedProfile ? (
        <div className="panel empty-workspace">
          <p className="empty-state">Choose a trusted profile to inspect the published configuration and open a draft.</p>
        </div>
      ) : null}

      {profileDetail ? (
        <div className="settings-grid">
          <div className="panel settings-main">
            <SectionHeader
              title="Published Profile Summary"
              description="Published versions are read-only. Open the single draft to edit the approved Phase 2A domains."
              action={
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void onCreateDesktopSyncExport()}
                  disabled={busy}
                >
                  Create desktop sync archive
                </button>
              }
            />
            <dl className="summary-list settings-summary-grid">
              <div>
                <dt>Profile key</dt>
                <dd>{profileDetail.profile_name}</dd>
              </div>
              <div>
                <dt>Display name</dt>
                <dd>{profileDetail.display_name}</dd>
              </div>
              <div>
                <dt>Description</dt>
                <dd>{profileDetail.description || "-"}</dd>
              </div>
              <div>
                <dt>Version label</dt>
                <dd>{profileDetail.version_label ?? "-"}</dd>
              </div>
              <div>
                <dt>Published version</dt>
                <dd>v{profileDetail.current_published_version.version_number}</dd>
              </div>
              <div>
                <dt>Content hash</dt>
                <dd className="hash-text">{profileDetail.current_published_version.content_hash}</dd>
              </div>
              <div>
                <dt>Template reference</dt>
                <dd>{profileDetail.current_published_version.template_artifact_ref ?? "-"}</dd>
              </div>
              <div>
                <dt>Template file hash</dt>
                <dd className="hash-text">{profileDetail.current_published_version.template_file_hash ?? "-"}</dd>
              </div>
              <div>
                <dt>Open draft</dt>
                <dd>{profileDetail.open_draft_id ?? "None"}</dd>
              </div>
            </dl>
            <p className="muted">
              Desktop sync archives always come from the current published version only. Drafts are never exported.
            </p>
            {lastDownloadedProfileSyncFilename ? (
              <div className="workspace-callout success">
                <strong>Manual desktop-sync archive ready</strong>
                <p>{lastDownloadedProfileSyncFilename}</p>
              </div>
            ) : null}

            {draftState ? (
              <>
                {draftState.validation_errors.length > 0 ? (
                  <div className="banner warning">
                    <strong>Draft validation issues</strong>
                    <ul className="message-list">
                      {draftState.validation_errors.map((issue) => (
                        <li key={issue}>{issue}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {observedDraftNote ? (
                  <div className="banner warning" role="status">
                    <strong>Observed placeholders remain in this draft.</strong>
                    <p>
                      Rows tagged <ObservedBadge /> were auto-added from unmapped values seen during processing. They
                      may remain blank and still be published.
                    </p>
                  </div>
                ) : null}

                <div className="workspace-callout success">
                  <strong>Editing draft {draftState.trusted_profile_draft_id}</strong>
                  <p>
                    Based on published version v{draftState.current_published_version.version_number}. Draft content
                    hash: <span className="hash-text">{draftState.draft_content_hash}</span>
                  </p>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Default Omit Rules"
                    description="Edit the phase codes that start omitted by default for future runs."
                    action={
                      <button type="button" onClick={() => void onSaveDefaultOmit(defaultOmitRules)} disabled={busy}>
                        Save default omit rules
                      </button>
                    }
                  />
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Phase code</th>
                          <th>Phase name</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {defaultOmitRules.map((row, index) => (
                          <tr key={`default-omit-${index}`}>
                            <td>
                              <input
                                aria-label={`Default omit phase code ${index + 1}`}
                                list="default-omit-phase-options"
                                value={row.phase_code}
                                onChange={(event) => {
                                  const nextPhaseCode = event.target.value;
                                  setDefaultOmitRules(
                                    defaultOmitRules.map((item, itemIndex) =>
                                      itemIndex === index
                                        ? {
                                            phase_code: nextPhaseCode,
                                            phase_name: findPhaseName(
                                              nextPhaseCode,
                                              draftState.default_omit_phase_options,
                                            ),
                                          }
                                        : item,
                                    ),
                                  );
                                }}
                              />
                            </td>
                            <td>{row.phase_name || findPhaseName(row.phase_code, draftState.default_omit_phase_options) || "-"}</td>
                            <td>
                              <button
                                type="button"
                                className="tertiary-button"
                                onClick={() =>
                                  setDefaultOmitRules(defaultOmitRules.filter((_, itemIndex) => itemIndex !== index))
                                }
                                disabled={busy}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <datalist id="default-omit-phase-options">
                      {draftState.default_omit_phase_options.map((option) => (
                        <option key={option.phase_code} value={option.phase_code}>
                          {option.phase_name}
                        </option>
                      ))}
                    </datalist>
                  </div>
                  <div className="actions">
                    <button
                      type="button"
                      className="tertiary-button"
                      onClick={() => setDefaultOmitRules([...defaultOmitRules, emptyDefaultOmitRule()])}
                      disabled={busy}
                    >
                      Add default omit rule
                    </button>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Labor Mappings"
                    description="Raw-first labor mappings remain editable, including blank observed placeholders."
                    action={
                      <button type="button" onClick={() => void onSaveLaborMappings(laborMappings)} disabled={busy}>
                        Save labor mappings
                      </button>
                    }
                  />
                  <p className="muted">
                    Observed rows were auto-added from unmapped labor values seen during processing. Leave them blank or
                    map them when ready.
                  </p>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Raw value</th>
                          <th>Target classification</th>
                          <th>Notes</th>
                          <th>Observed</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {laborMappings.map((row, index) => (
                          <tr key={`labor-mapping-${index}`}>
                            <td>
                              <input
                                aria-label={`Labor raw value ${index + 1}`}
                                value={row.raw_value}
                                onChange={(event) =>
                                  setLaborMappings(
                                    laborMappings.map((item, itemIndex) =>
                                      itemIndex === index ? { ...item, raw_value: event.target.value } : item,
                                    ),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <select
                                aria-label={`Labor target classification ${index + 1}`}
                                value={row.target_classification}
                                onChange={(event) =>
                                  setLaborMappings(
                                    laborMappings.map((item, itemIndex) =>
                                      itemIndex === index
                                        ? { ...item, target_classification: event.target.value }
                                        : item,
                                    ),
                                  )
                                }
                              >
                                <option value="">Unmapped</option>
                                {laborTargets.map((target) => (
                                  <option key={target} value={target}>
                                    {target}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <input
                                aria-label={`Labor notes ${index + 1}`}
                                value={row.notes}
                                onChange={(event) =>
                                  setLaborMappings(
                                    laborMappings.map((item, itemIndex) =>
                                      itemIndex === index ? { ...item, notes: event.target.value } : item,
                                    ),
                                  )
                                }
                              />
                            </td>
                            <td>{row.is_observed ? <ObservedBadge /> : <span className="muted">User row</span>}</td>
                            <td>
                              <button
                                type="button"
                                className="tertiary-button"
                                onClick={() => setLaborMappings(laborMappings.filter((_, itemIndex) => itemIndex !== index))}
                                disabled={busy}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="actions">
                    <button
                      type="button"
                      className="tertiary-button"
                      onClick={() => setLaborMappings([...laborMappings, emptyLaborMappingRow()])}
                      disabled={busy}
                    >
                      Add labor mapping row
                    </button>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Equipment Mappings"
                    description="Equipment raw keys stay separate from the resolved recap category."
                    action={
                      <button type="button" onClick={() => void onSaveEquipmentMappings(equipmentMappings)} disabled={busy}>
                        Save equipment mappings
                      </button>
                    }
                  />
                  <p className="muted">
                    Observed equipment rows were auto-added from unmapped keys seen during processing and can remain
                    unresolved.
                  </p>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Raw description</th>
                          <th>Target category</th>
                          <th>Observed</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {equipmentMappings.map((row, index) => (
                          <tr key={`equipment-mapping-${index}`}>
                            <td>
                              <input
                                aria-label={`Equipment raw description ${index + 1}`}
                                value={row.raw_description}
                                onChange={(event) =>
                                  setEquipmentMappings(
                                    equipmentMappings.map((item, itemIndex) =>
                                      itemIndex === index ? { ...item, raw_description: event.target.value } : item,
                                    ),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <select
                                aria-label={`Equipment target category ${index + 1}`}
                                value={row.target_category}
                                onChange={(event) =>
                                  setEquipmentMappings(
                                    equipmentMappings.map((item, itemIndex) =>
                                      itemIndex === index ? { ...item, target_category: event.target.value } : item,
                                    ),
                                  )
                                }
                              >
                                <option value="">Unmapped</option>
                                {equipmentTargets.map((target) => (
                                  <option key={target} value={target}>
                                    {target}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>{row.is_observed ? <ObservedBadge /> : <span className="muted">User row</span>}</td>
                            <td>
                              <button
                                type="button"
                                className="tertiary-button"
                                onClick={() =>
                                  setEquipmentMappings(
                                    equipmentMappings.filter((_, itemIndex) => itemIndex !== index),
                                  )
                                }
                                disabled={busy}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="actions">
                    <button
                      type="button"
                      className="tertiary-button"
                      onClick={() => setEquipmentMappings([...equipmentMappings, emptyEquipmentMappingRow()])}
                      disabled={busy}
                    >
                      Add equipment mapping row
                    </button>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Classifications"
                    description="Edit slot labels and active state only. Slot ids remain stable and backend validation handles dependent updates."
                    action={
                      <button
                        type="button"
                        onClick={() => void onSaveClassifications(laborSlots, equipmentSlots)}
                        disabled={busy}
                      >
                        Save classifications
                      </button>
                    }
                  />
                  <div className="settings-two-column">
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Labor slot id</th>
                            <th>Label</th>
                            <th>Active</th>
                          </tr>
                        </thead>
                        <tbody>
                          {laborSlots.map((row, index) => (
                            <tr key={`labor-slot-${row.slot_id}`}>
                              <td className="cell-primary">{row.slot_id}</td>
                              <td>
                                <input
                                  aria-label={`Labor classification label ${index + 1}`}
                                  value={row.label}
                                  onChange={(event) =>
                                    setLaborSlots(
                                      laborSlots.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, label: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                              </td>
                              <td>
                                <label className="checkbox-field">
                                  <input
                                    type="checkbox"
                                    checked={row.active}
                                    onChange={(event) =>
                                      setLaborSlots(
                                        laborSlots.map((item, itemIndex) =>
                                          itemIndex === index ? { ...item, active: event.target.checked } : item,
                                        ),
                                      )
                                    }
                                  />
                                  <span>{row.active ? "Active" : "Inactive"}</span>
                                </label>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Equipment slot id</th>
                            <th>Label</th>
                            <th>Active</th>
                          </tr>
                        </thead>
                        <tbody>
                          {equipmentSlots.map((row, index) => (
                            <tr key={`equipment-slot-${row.slot_id}`}>
                              <td className="cell-primary">{row.slot_id}</td>
                              <td>
                                <input
                                  aria-label={`Equipment classification label ${index + 1}`}
                                  value={row.label}
                                  onChange={(event) =>
                                    setEquipmentSlots(
                                      equipmentSlots.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, label: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                              </td>
                              <td>
                                <label className="checkbox-field">
                                  <input
                                    type="checkbox"
                                    checked={row.active}
                                    onChange={(event) =>
                                      setEquipmentSlots(
                                        equipmentSlots.map((item, itemIndex) =>
                                          itemIndex === index ? { ...item, active: event.target.checked } : item,
                                        ),
                                      )
                                    }
                                  />
                                  <span>{row.active ? "Active" : "Inactive"}</span>
                                </label>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Rates"
                    description="Rates stay backend-validated. Unmapped observed rows do not block editing or publish on their own."
                    action={
                      <button type="button" onClick={() => void onSaveRates(laborRates, equipmentRates)} disabled={busy}>
                        Save rates
                      </button>
                    }
                  />
                  <div className="settings-two-column">
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Labor classification</th>
                            <th>Standard</th>
                            <th>Overtime</th>
                            <th>Double time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {laborRates.map((row, index) => (
                            <tr key={`labor-rate-${row.classification}`}>
                              <td className="cell-primary">{row.classification}</td>
                              <td>
                                <input
                                  aria-label={`Labor standard rate ${index + 1}`}
                                  value={row.standard_rate}
                                  onChange={(event) =>
                                    setLaborRates(
                                      laborRates.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, standard_rate: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                              </td>
                              <td>
                                <input
                                  aria-label={`Labor overtime rate ${index + 1}`}
                                  value={row.overtime_rate}
                                  onChange={(event) =>
                                    setLaborRates(
                                      laborRates.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, overtime_rate: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                              </td>
                              <td>
                                <input
                                  aria-label={`Labor double time rate ${index + 1}`}
                                  value={row.double_time_rate}
                                  onChange={(event) =>
                                    setLaborRates(
                                      laborRates.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, double_time_rate: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Equipment category</th>
                            <th>Rate</th>
                          </tr>
                        </thead>
                        <tbody>
                          {equipmentRates.map((row, index) => (
                            <tr key={`equipment-rate-${row.category}`}>
                              <td className="cell-primary">{row.category}</td>
                              <td>
                                <input
                                  aria-label={`Equipment rate ${index + 1}`}
                                  value={row.rate}
                                  onChange={(event) =>
                                    setEquipmentRates(
                                      equipmentRates.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, rate: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="workspace-callout">
                <strong>No draft is open for this profile.</strong>
                <p>
                  Inspect the published version below, then create or open the single mutable draft to edit the
                  approved Phase 2A settings slice.
                </p>
              </div>
            )}
          </div>

          <aside className="workspace-sidebar">
            <div className="workspace-sidebar-inner panel">
              <SectionHeader
                title="Read-only Deferred Domains"
                description="These domains remain non-editable in Phase 2A."
              />
              <p className="muted">Read only in Phase 2A. Template identity is still part of the published version.</p>
              {deferredDomains ? (
                <>
                  <DeferredDomainCard title="Vendor Normalization" payload={deferredDomains.vendor_normalization} />
                  <DeferredDomainCard title="Phase Mapping" payload={deferredDomains.phase_mapping} />
                  <DeferredDomainCard title="Input Model" payload={deferredDomains.input_model} />
                  <DeferredDomainCard title="Recap Template Map" payload={deferredDomains.recap_template_map} />
                </>
              ) : (
                <p className="empty-state">
                  Published deferred-domain inspection will appear here once the profile detail loads.
                </p>
              )}
            </div>
          </aside>
        </div>
      ) : selectedTrustedProfile ? (
        <div className="panel empty-workspace">
          <p className="empty-state">Loading published profile detail for the selected trusted profile.</p>
        </div>
      ) : null}
    </section>
  );
}
