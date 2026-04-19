import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError } from "../api/client";

import type {
  ClassificationSlotRow,
  CreateTrustedProfileRequest,
  DefaultOmitRuleRow,
  DraftSaveRequest,
  DraftEditorStateResponse,
  EquipmentMappingRow,
  EquipmentRateRow,
  ExportSettingsResponse,
  LaborMappingRow,
  LaborRateRow,
  PublishedProfileDetailResponse,
  TrustedProfileResponse,
} from "../api/contracts";

type DraftSyncReason =
  | "reset"
  | "profileSwitch"
  | "open"
  | "save"
  | "defaultOmit"
  | "laborMappings"
  | "equipmentMappings"
  | "classifications"
  | "exportSettings"
  | "rates";

interface DraftSyncToken {
  reason: DraftSyncReason;
  sequence: number;
}

export interface ProfileSettingsLeaveGuard {
  hasUnpublishedChanges: boolean;
  dirtySections: string[];
  draftId: string | null;
  profileDisplayName: string;
  saveAllDirtySections: () => Promise<boolean>;
  discardCurrentDraft: () => Promise<boolean>;
}

interface ProfileSettingsWorkspaceProps {
  trustedProfiles: TrustedProfileResponse[];
  archivedTrustedProfiles: TrustedProfileResponse[];
  selectedTrustedProfileName: string;
  selectedTrustedProfile: TrustedProfileResponse | null;
  profileDetail: PublishedProfileDetailResponse | null;
  draftState: DraftEditorStateResponse | null;
  profileDetailLoading: boolean;
  draftSyncToken: DraftSyncToken;
  busy: boolean;
  settingsErrorMessage: string;
  onTrustedProfileNameChange: (value: string) => void;
  onReloadProfileDetail: () => Promise<void> | void;
  onOpenDraft: () => Promise<void> | void;
  onSaveDraft: (request: Omit<DraftSaveRequest, "expected_draft_revision">) => Promise<boolean> | boolean;
  onPublishDraft: (trustedProfileDraftId?: string) => Promise<boolean> | boolean;
  onDiscardDraft: (trustedProfileDraftId: string) => Promise<boolean> | boolean;
  onCreateTrustedProfile: (request: CreateTrustedProfileRequest) => Promise<void> | void;
  onArchiveTrustedProfile: () => Promise<void> | void;
  onUnarchiveTrustedProfile: (trustedProfileId: string, displayName: string) => Promise<void> | void;
  onLeaveGuardChange?: (guard: ProfileSettingsLeaveGuard | null) => void;
}

interface ValidationResult {
  rowErrors: Record<number, string[]>;
  messages: string[];
}

interface RetainedDraftWorkspaceState {
  trusted_profile_id: string;
  trusted_profile_draft_id: string;
  draft_content_hash: string;
  published_version_number: number;
  default_omit_rules: DefaultOmitRuleRow[];
  labor_mappings: LaborMappingRow[];
  equipment_mappings: EquipmentMappingRow[];
  labor_slots: ClassificationSlotRow[];
  equipment_slots: ClassificationSlotRow[];
  export_settings: ExportSettingsResponse;
  labor_rates: LaborRateRow[];
  equipment_rates: EquipmentRateRow[];
  dirty_sections: string[];
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function cloneRows<T>(rows: T[]): T[] {
  return rows.map((row) => ({ ...row }));
}

function cloneDraftWorkspaceState(
  state: RetainedDraftWorkspaceState,
): RetainedDraftWorkspaceState {
  return {
    trusted_profile_id: state.trusted_profile_id,
    trusted_profile_draft_id: state.trusted_profile_draft_id,
    draft_content_hash: state.draft_content_hash,
    published_version_number: state.published_version_number,
    default_omit_rules: cloneRows(state.default_omit_rules),
    labor_mappings: cloneRows(state.labor_mappings),
    equipment_mappings: cloneRows(state.equipment_mappings),
    labor_slots: cloneRows(state.labor_slots),
    equipment_slots: cloneRows(state.equipment_slots),
    export_settings: { labor_minimum_hours: { ...state.export_settings.labor_minimum_hours } },
    labor_rates: cloneRows(state.labor_rates),
    equipment_rates: cloneRows(state.equipment_rates),
    dirty_sections: [...state.dirty_sections],
  };
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
    is_required_for_recent_processing: false,
  };
}

function emptyEquipmentMappingRow(): EquipmentMappingRow {
  return {
    raw_description: "",
    raw_pattern: "",
    target_category: "",
    is_observed: false,
    is_required_for_recent_processing: false,
    prediction_target: null,
    prediction_confidence_label: null,
  };
}

function emptyExportSettings(): ExportSettingsResponse {
  return {
    labor_minimum_hours: {
      enabled: false,
      threshold_hours: "",
      minimum_hours: "",
    },
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

function compareRows<T>(left: T[], right: T[]): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function compareValue<T>(left: T, right: T): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function normalizeKey(value: string | null | undefined): string {
  return String(value ?? "").trim().toUpperCase();
}

function createValidationResult(): ValidationResult {
  return {
    rowErrors: {},
    messages: [],
  };
}

function appendRowError(result: ValidationResult, index: number, message: string) {
  result.rowErrors[index] = [...(result.rowErrors[index] ?? []), message];
  if (!result.messages.includes(message)) {
    result.messages.push(message);
  }
}

function buildDefaultOmitValidation(rows: DefaultOmitRuleRow[]): ValidationResult {
  const result = createValidationResult();
  const seen = new Map<string, number>();

  rows.forEach((row, index) => {
    const phaseCode = row.phase_code.trim();
    if (!phaseCode) {
      appendRowError(result, index, "Each default omit rule needs a phase code.");
      return;
    }
    const normalized = normalizeKey(phaseCode);
    const existingIndex = seen.get(normalized);
    if (existingIndex !== undefined) {
      appendRowError(result, existingIndex, "Default omit phase codes must be unique.");
      appendRowError(result, index, "Default omit phase codes must be unique.");
      return;
    }
    seen.set(normalized, index);
  });

  return result;
}

function buildLaborMappingValidation(rows: LaborMappingRow[], validTargets: string[]): ValidationResult {
  const result = createValidationResult();
  const seen = new Map<string, number>();

  rows.forEach((row, index) => {
    const rawValue = row.raw_value.trim();
    if (!rawValue) {
      appendRowError(result, index, "Each labor mapping row needs a raw value.");
    }
    const normalized = normalizeKey(rawValue);
    if (normalized) {
      const existingIndex = seen.get(normalized);
      if (existingIndex !== undefined) {
        appendRowError(result, existingIndex, "Labor mapping raw values must be unique.");
        appendRowError(result, index, "Labor mapping raw values must be unique.");
      } else {
        seen.set(normalized, index);
      }
    }
    if (row.target_classification.trim() && !validTargets.includes(row.target_classification.trim())) {
      appendRowError(result, index, "Choose an active labor classification target or clear the mapping.");
    }
  });

  return result;
}

function buildEquipmentMappingValidation(rows: EquipmentMappingRow[], validTargets: string[]): ValidationResult {
  const result = createValidationResult();
  const seen = new Map<string, number>();

  rows.forEach((row, index) => {
    const rawDescription = row.raw_description.trim();
    const canonicalKey = normalizeKey(row.raw_pattern || rawDescription);
    if (!rawDescription) {
      appendRowError(result, index, "Each equipment mapping row needs a raw description.");
    }
    if (canonicalKey) {
      const existingIndex = seen.get(canonicalKey);
      if (existingIndex !== undefined) {
        appendRowError(result, existingIndex, "Equipment mapping raw keys must be unique.");
        appendRowError(result, index, "Equipment mapping raw keys must be unique.");
      } else {
        seen.set(canonicalKey, index);
      }
    }
    if (row.target_category.trim() && !validTargets.includes(row.target_category.trim())) {
      appendRowError(result, index, "Choose an active equipment classification target or clear the mapping.");
    }
  });

  return result;
}

function buildClassificationValidation(rows: ClassificationSlotRow[], label: string, activeCapacity: number): ValidationResult {
  const result = createValidationResult();
  const seen = new Map<string, number>();
  let activeCount = 0;

  rows.forEach((row, index) => {
    const normalizedLabel = normalizeKey(row.label);
    if (row.active && !normalizedLabel) {
      appendRowError(result, index, `Active ${label} classification slots need labels.`);
      return;
    }
    if (!row.active || !normalizedLabel) {
      return;
    }
    activeCount += 1;
    const existingIndex = seen.get(normalizedLabel);
    if (existingIndex !== undefined) {
      appendRowError(result, existingIndex, `Active ${label} classification labels must be unique.`);
      appendRowError(result, index, `Active ${label} classification labels must be unique.`);
      return;
    }
    seen.set(normalizedLabel, index);
  });
  if (activeCapacity > 0 && activeCount > activeCapacity) {
    result.messages.push(
      `Active ${label} classifications exceed template capacity (${activeCapacity} active slot${activeCapacity === 1 ? "" : "s"} available).`,
    );
  }

  return result;
}

function isNumericOrBlank(value: string): boolean {
  const trimmed = value.trim();
  return trimmed === "" || !Number.isNaN(Number(trimmed));
}

function buildRatesValidation(laborRates: LaborRateRow[], equipmentRates: EquipmentRateRow[]): ValidationResult {
  const result = createValidationResult();

  laborRates.forEach((row, index) => {
    if (!isNumericOrBlank(row.standard_rate)) {
      appendRowError(result, index, "Labor standard rates must be numeric or blank.");
    }
    if (!isNumericOrBlank(row.overtime_rate)) {
      appendRowError(result, index, "Labor overtime rates must be numeric or blank.");
    }
    if (!isNumericOrBlank(row.double_time_rate)) {
      appendRowError(result, index, "Labor double-time rates must be numeric or blank.");
    }
  });

  equipmentRates.forEach((row, index) => {
    if (!isNumericOrBlank(row.rate)) {
      appendRowError(result, laborRates.length + index, "Equipment rates must be numeric or blank.");
    }
  });

  return result;
}

function buildExportSettingsValidation(exportSettings: ExportSettingsResponse): ValidationResult {
  const result = createValidationResult();
  const rule = exportSettings.labor_minimum_hours;
  const thresholdValue = rule.threshold_hours.trim();
  const minimumValue = rule.minimum_hours.trim();
  const thresholdNumber = thresholdValue === "" ? Number.NaN : Number(thresholdValue);
  const minimumNumber = minimumValue === "" ? Number.NaN : Number(minimumValue);

  if (!rule.enabled && !thresholdValue && !minimumValue) {
    return result;
  }
  if (rule.enabled && !thresholdValue) {
    result.messages.push("Labor minimum-hours threshold is required when the rule is enabled.");
  }
  if (rule.enabled && !minimumValue) {
    result.messages.push("Labor minimum-hours value is required when the rule is enabled.");
  }
  if (thresholdValue && Number.isNaN(thresholdNumber)) {
    result.messages.push("Labor minimum-hours threshold must be numeric.");
  }
  if (minimumValue && Number.isNaN(minimumNumber)) {
    result.messages.push("Labor minimum-hours value must be numeric.");
  }
  if (!Number.isNaN(thresholdNumber) && thresholdNumber <= 0) {
    result.messages.push("Labor minimum-hours threshold must be greater than 0.");
  }
  if (!Number.isNaN(minimumNumber) && minimumNumber <= 0) {
    result.messages.push("Labor minimum-hours value must be greater than 0.");
  }
  if (
    !Number.isNaN(thresholdNumber) &&
    !Number.isNaN(minimumNumber) &&
    minimumNumber < thresholdNumber
  ) {
    result.messages.push("Labor minimum-hours value must be greater than or equal to the threshold.");
  }
  return result;
}

function hasConfiguredLaborRate(row: LaborRateRow): boolean {
  return [row.standard_rate, row.overtime_rate, row.double_time_rate].some((value) => value.trim().length > 0);
}

function hasConfiguredEquipmentRate(row: EquipmentRateRow): boolean {
  return row.rate.trim().length > 0;
}

function buildCurrentSlotStateByPreviousLabel(previousSlots: ClassificationSlotRow[], currentSlots: ClassificationSlotRow[]) {
  const currentSlotsById = new Map(currentSlots.map((slot) => [slot.slot_id, slot]));
  const previousLabelState = new Map<string, { active: boolean }>();

  previousSlots.forEach((slot) => {
    const labelKey = normalizeKey(slot.label);
    if (!labelKey) {
      return;
    }
    previousLabelState.set(labelKey, {
      active: Boolean(currentSlotsById.get(slot.slot_id)?.active),
    });
  });

  return previousLabelState;
}

function filterLaborRatesForCurrentSlots(
  laborRates: LaborRateRow[],
  previousSlots: ClassificationSlotRow[],
  currentSlots: ClassificationSlotRow[],
): LaborRateRow[] {
  const previousLabelState = buildCurrentSlotStateByPreviousLabel(previousSlots, currentSlots);
  const activeCurrentLabels = new Set(
    currentSlots.filter((slot) => slot.active).map((slot) => normalizeKey(slot.label)).filter(Boolean),
  );

  return laborRates.filter((row) => {
    const labelKey = normalizeKey(row.classification);
    const previousState = previousLabelState.get(labelKey);
    if (previousState) {
      return previousState.active;
    }
    return activeCurrentLabels.has(labelKey);
  });
}

function filterEquipmentRatesForCurrentSlots(
  equipmentRates: EquipmentRateRow[],
  previousSlots: ClassificationSlotRow[],
  currentSlots: ClassificationSlotRow[],
): EquipmentRateRow[] {
  const previousLabelState = buildCurrentSlotStateByPreviousLabel(previousSlots, currentSlots);
  const activeCurrentLabels = new Set(
    currentSlots.filter((slot) => slot.active).map((slot) => normalizeKey(slot.label)).filter(Boolean),
  );

  return equipmentRates.filter((row) => {
    const labelKey = normalizeKey(row.category);
    const previousState = previousLabelState.get(labelKey);
    if (previousState) {
      return previousState.active;
    }
    return activeCurrentLabels.has(labelKey);
  });
}

function buildRetiredLaborRateLabels(
  laborRates: LaborRateRow[],
  previousSlots: ClassificationSlotRow[],
  currentSlots: ClassificationSlotRow[],
): string[] {
  const previousLabelState = buildCurrentSlotStateByPreviousLabel(previousSlots, currentSlots);
  return laborRates
    .filter((row) => {
      const previousState = previousLabelState.get(normalizeKey(row.classification));
      return Boolean(previousState && !previousState.active && hasConfiguredLaborRate(row));
    })
    .map((row) => row.classification.trim())
    .filter(Boolean);
}

function buildRetiredEquipmentRateLabels(
  equipmentRates: EquipmentRateRow[],
  previousSlots: ClassificationSlotRow[],
  currentSlots: ClassificationSlotRow[],
): string[] {
  const previousLabelState = buildCurrentSlotStateByPreviousLabel(previousSlots, currentSlots);
  return equipmentRates
    .filter((row) => {
      const previousState = previousLabelState.get(normalizeKey(row.category));
      return Boolean(previousState && !previousState.active && hasConfiguredEquipmentRate(row));
    })
    .map((row) => row.category.trim())
    .filter(Boolean);
}

function buildTargetOptions(currentValue: string, validTargets: string[]) {
  const trimmedCurrentValue = currentValue.trim();
  if (!trimmedCurrentValue || validTargets.includes(trimmedCurrentValue)) {
    return validTargets;
  }
  return [trimmedCurrentValue, ...validTargets];
}

function buildNextSlotId(rows: ClassificationSlotRow[], prefix: string): string {
  const nextSequence =
    rows.reduce((maxValue, row) => {
      const match = row.slot_id.match(new RegExp(`^${prefix}_(\\d+)$`, "i"));
      if (!match) {
        return maxValue;
      }
      return Math.max(maxValue, Number(match[1]));
    }, 0) + 1;
  return `${prefix}_${nextSequence}`;
}

const MAX_PROFILE_DISPLAY_NAME_LENGTH = 32;

function buildProfileNameFromDisplayName(displayName: string): string {
  return displayName
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^A-Za-z0-9_-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .toLowerCase();
}

function buildCreateProfileValidation(
  displayName: string,
  trustedProfiles: TrustedProfileResponse[],
): ValidationResult {
  const result = createValidationResult();
  const trimmedDisplayName = displayName.trim();
  const generatedProfileName = buildProfileNameFromDisplayName(trimmedDisplayName);

  if (!trimmedDisplayName) {
    appendRowError(result, 0, "A display name is required.");
  } else if (trimmedDisplayName.length > MAX_PROFILE_DISPLAY_NAME_LENGTH) {
    appendRowError(result, 0, `Display names must stay within ${MAX_PROFILE_DISPLAY_NAME_LENGTH} characters.`);
  } else if (!generatedProfileName) {
    appendRowError(result, 0, "Display names must include letters or numbers.");
  }
  if (
    trimmedDisplayName &&
    trustedProfiles.some((profile) => profile.display_name.trim().toUpperCase() === trimmedDisplayName.toUpperCase())
  ) {
    appendRowError(result, 0, "That display name is already in use by another active trusted profile.");
  }
  if (
    generatedProfileName &&
    trustedProfiles.some((profile) => profile.profile_name.trim().toUpperCase() === generatedProfileName.toUpperCase())
  ) {
    appendRowError(result, 0, "That display name resolves to a profile key already in use.");
  }

  return result;
}

function mergeMessages(...messageGroups: Array<string[] | undefined>): string[] {
  return [...new Set(messageGroups.flatMap((messages) => messages ?? []).filter(Boolean))];
}

function formatArchivedAt(value: string | null): string {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function profileSourceLabel(sourceKind: string): string {
  switch (sourceKind) {
    case "seeded":
      return "Default profile";
    case "filesystem_bootstrap":
      return "Filesystem-backed";
    case "published_clone":
      return "Web-created";
    default:
      return sourceKind;
  }
}

function profileSourceTone(sourceKind: string): "neutral" | "success" | "warning" | "error" {
  switch (sourceKind) {
    case "published_clone":
      return "success";
    case "filesystem_bootstrap":
      return "warning";
    default:
      return "neutral";
  }
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

function RequiredObservedBadge() {
  return <span className="required-observed-badge">Required now</span>;
}

function StatusPill({ tone, children }: { tone: "neutral" | "success" | "warning" | "error"; children: ReactNode }) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}

function RowMessages({ messages }: { messages?: string[] }) {
  if (!messages || messages.length === 0) {
    return null;
  }
  return (
    <div className="field-messages">
      {messages.map((message) => (
        <p key={message} className="field-error">
          {message}
        </p>
      ))}
    </div>
  );
}

function SectionStatusPill({
  dirty,
  errorCount,
}: {
  dirty: boolean;
  errorCount: number;
}) {
  return (
    <StatusPill tone={errorCount > 0 ? "error" : dirty ? "warning" : "success"}>
      {errorCount > 0 ? `${errorCount} issue${errorCount === 1 ? "" : "s"}` : dirty ? "Unsaved" : "Saved"}
    </StatusPill>
  );
}

function buildLaborMappingRowKey(row: LaborMappingRow, index: number): string {
  return `labor:${index}`;
}

function buildEquipmentMappingRowKey(row: EquipmentMappingRow, index: number): string {
  return `equipment:${index}`;
}

export function ProfileSettingsWorkspace({
  trustedProfiles,
  archivedTrustedProfiles,
  selectedTrustedProfileName,
  selectedTrustedProfile,
  profileDetail,
  draftState,
  profileDetailLoading,
  draftSyncToken,
  busy,
  settingsErrorMessage,
  onTrustedProfileNameChange,
  onReloadProfileDetail,
  onOpenDraft,
  onSaveDraft,
  onPublishDraft,
  onDiscardDraft,
  onCreateTrustedProfile,
  onArchiveTrustedProfile,
  onUnarchiveTrustedProfile,
  onLeaveGuardChange,
}: ProfileSettingsWorkspaceProps) {
  const [defaultOmitRules, setDefaultOmitRules] = useState<DefaultOmitRuleRow[]>([]);
  const [laborMappings, setLaborMappings] = useState<LaborMappingRow[]>([]);
  const [equipmentMappings, setEquipmentMappings] = useState<EquipmentMappingRow[]>([]);
  const [laborSlots, setLaborSlots] = useState<ClassificationSlotRow[]>([]);
  const [equipmentSlots, setEquipmentSlots] = useState<ClassificationSlotRow[]>([]);
  const [exportSettings, setExportSettings] = useState<ExportSettingsResponse>(emptyExportSettings());
  const [laborRates, setLaborRates] = useState<LaborRateRow[]>([]);
  const [equipmentRates, setEquipmentRates] = useState<EquipmentRateRow[]>([]);
  const [newProfileDisplayName, setNewProfileDisplayName] = useState("");
  const [newProfileDescription, setNewProfileDescription] = useState("");
  const [createServerFieldErrors, setCreateServerFieldErrors] = useState<Record<string, string[]>>({});
  const [createServerMessage, setCreateServerMessage] = useState("");
  const [selectedLaborMappingKeys, setSelectedLaborMappingKeys] = useState<string[]>([]);
  const [selectedEquipmentMappingKeys, setSelectedEquipmentMappingKeys] = useState<string[]>([]);
  const [bulkLaborTarget, setBulkLaborTarget] = useState("");
  const [bulkEquipmentTarget, setBulkEquipmentTarget] = useState("");
  const [retainedDraftStates, setRetainedDraftStates] = useState<Record<string, RetainedDraftWorkspaceState>>({});
  const [restoredDraftNotice, setRestoredDraftNotice] = useState("");
  const lastDraftIdRef = useRef<string | null>(null);
  const hydratedDraftKeyRef = useRef<string | null>(null);

  function clearLocalEditorState() {
    setDefaultOmitRules([]);
    setLaborMappings([]);
    setEquipmentMappings([]);
    setLaborSlots([]);
    setEquipmentSlots([]);
    setExportSettings(emptyExportSettings());
    setLaborRates([]);
    setEquipmentRates([]);
  }

  function syncAllFromDraft(nextDraftState: DraftEditorStateResponse) {
    setDefaultOmitRules(cloneRows(nextDraftState.default_omit_rules));
    setLaborMappings(cloneRows(nextDraftState.labor_mappings));
    setEquipmentMappings(cloneRows(nextDraftState.equipment_mappings));
    setLaborSlots(cloneRows(nextDraftState.labor_slots));
    setEquipmentSlots(cloneRows(nextDraftState.equipment_slots));
    setExportSettings({ labor_minimum_hours: { ...nextDraftState.export_settings.labor_minimum_hours } });
    setLaborRates(cloneRows(nextDraftState.labor_rates));
    setEquipmentRates(cloneRows(nextDraftState.equipment_rates));
  }

  function syncAllFromRetainedDraft(nextDraftState: RetainedDraftWorkspaceState) {
    setDefaultOmitRules(cloneRows(nextDraftState.default_omit_rules));
    setLaborMappings(cloneRows(nextDraftState.labor_mappings));
    setEquipmentMappings(cloneRows(nextDraftState.equipment_mappings));
    setLaborSlots(cloneRows(nextDraftState.labor_slots));
    setEquipmentSlots(cloneRows(nextDraftState.equipment_slots));
    setExportSettings({ labor_minimum_hours: { ...nextDraftState.export_settings.labor_minimum_hours } });
    setLaborRates(cloneRows(nextDraftState.labor_rates));
    setEquipmentRates(cloneRows(nextDraftState.equipment_rates));
  }

  const selectedTrustedProfileId = selectedTrustedProfile?.trusted_profile_id ?? "";
  const selectedProfileDetail =
    profileDetail && profileDetail.trusted_profile_id === selectedTrustedProfileId ? profileDetail : null;
  const selectedProfileDraft =
    draftState && draftState.trusted_profile_id === selectedTrustedProfileId ? draftState : null;

  useEffect(() => {
    if (!selectedTrustedProfileId || !selectedProfileDraft) {
      clearLocalEditorState();
      lastDraftIdRef.current = null;
      hydratedDraftKeyRef.current = null;
      if (draftSyncToken.reason === "reset" || draftSyncToken.reason === "profileSwitch") {
        setRestoredDraftNotice("");
      }
      return;
    }

    const isNewDraft = lastDraftIdRef.current !== selectedProfileDraft.trusted_profile_draft_id;
    lastDraftIdRef.current = selectedProfileDraft.trusted_profile_draft_id;
    const retainedDraftState = retainedDraftStates[selectedTrustedProfileId];

    if (
      isNewDraft &&
      retainedDraftState &&
      retainedDraftState.trusted_profile_draft_id === selectedProfileDraft.trusted_profile_draft_id &&
      retainedDraftState.draft_content_hash === selectedProfileDraft.draft_content_hash &&
      draftSyncToken.reason === "open"
    ) {
      syncAllFromRetainedDraft(retainedDraftState);
      setRestoredDraftNotice(
        `Restored ${retainedDraftState.dirty_sections.join(", ")} from unsaved browser edits kept for this profile in this tab.`,
      );
      return;
    }

    setRestoredDraftNotice("");

    if (isNewDraft || draftSyncToken.reason === "reset") {
      syncAllFromDraft(selectedProfileDraft);
      return;
    }

    switch (draftSyncToken.reason) {
      case "open":
      case "profileSwitch":
        break;
      case "save":
        syncAllFromDraft(selectedProfileDraft);
        break;
      case "defaultOmit":
        setDefaultOmitRules(cloneRows(selectedProfileDraft.default_omit_rules));
        break;
      case "laborMappings":
        setLaborMappings(cloneRows(selectedProfileDraft.labor_mappings));
        break;
      case "equipmentMappings":
        setEquipmentMappings(cloneRows(selectedProfileDraft.equipment_mappings));
        break;
      case "classifications":
        setLaborSlots(cloneRows(selectedProfileDraft.labor_slots));
        setEquipmentSlots(cloneRows(selectedProfileDraft.equipment_slots));
        setLaborMappings(cloneRows(selectedProfileDraft.labor_mappings));
        setEquipmentMappings(cloneRows(selectedProfileDraft.equipment_mappings));
        setLaborRates(cloneRows(selectedProfileDraft.labor_rates));
        setEquipmentRates(cloneRows(selectedProfileDraft.equipment_rates));
        break;
      case "exportSettings":
        setExportSettings({ labor_minimum_hours: { ...selectedProfileDraft.export_settings.labor_minimum_hours } });
        break;
      case "rates":
        setLaborRates(cloneRows(selectedProfileDraft.labor_rates));
        setEquipmentRates(cloneRows(selectedProfileDraft.equipment_rates));
        break;
      default:
        syncAllFromDraft(selectedProfileDraft);
        break;
    }
  }, [selectedProfileDraft, draftSyncToken, selectedTrustedProfileId]);

  useEffect(() => {
    setNewProfileDisplayName("");
    setNewProfileDescription("");
    setCreateServerFieldErrors({});
    setCreateServerMessage("");
  }, [selectedTrustedProfileName]);

  useEffect(() => {
    setCreateServerFieldErrors({});
    setCreateServerMessage("");
  }, [newProfileDisplayName, newProfileDescription]);

  useEffect(() => {
    if (draftSyncToken.reason !== "reset" || !selectedTrustedProfileId || selectedProfileDraft) {
      return;
    }
    setRetainedDraftStates((current) => {
      if (!current[selectedTrustedProfileId]) {
        return current;
      }
      const next = { ...current };
      delete next[selectedTrustedProfileId];
      return next;
    });
  }, [selectedProfileDraft, draftSyncToken.reason, selectedTrustedProfileId]);

  const detailToRender = selectedProfileDraft ?? selectedProfileDetail;
  const openDraftId = selectedProfileDraft?.trusted_profile_draft_id ?? selectedProfileDetail?.open_draft_id ?? null;
  const templateMetadata = detailToRender?.template_metadata ?? null;
  const laborActiveCapacity = templateMetadata?.labor_active_slot_capacity ?? 0;
  const equipmentActiveCapacity = templateMetadata?.equipment_active_slot_capacity ?? 0;
  const laborActiveCount = laborSlots.filter((row) => row.active && row.label.trim()).length;
  const equipmentActiveCount = equipmentSlots.filter((row) => row.active && row.label.trim()).length;
  const laborInactiveCount = laborSlots.filter((row) => !row.active && row.label.trim()).length;
  const equipmentInactiveCount = equipmentSlots.filter((row) => !row.active && row.label.trim()).length;
  const laborTargets = laborSlots.filter((row) => row.active && row.label.trim()).map((row) => row.label.trim());
  const equipmentTargets = equipmentSlots.filter((row) => row.active && row.label.trim()).map((row) => row.label.trim());
  const observedDraftNote = hasObservedUnmappedRows(laborMappings, equipmentMappings);
  const laborMappingEntries = laborMappings
    .map((row, index) => ({
      row,
      index,
      rowKey: buildLaborMappingRowKey(row, index),
    }))
    .sort((left, right) => {
      const leftPriority = left.row.is_required_for_recent_processing
        ? 0
        : left.row.is_observed && !left.row.target_classification.trim()
          ? 1
          : 2;
      const rightPriority = right.row.is_required_for_recent_processing
        ? 0
        : right.row.is_observed && !right.row.target_classification.trim()
          ? 1
          : 2;
      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }
      return buildLaborMappingRowKey(left.row, left.index).localeCompare(buildLaborMappingRowKey(right.row, right.index));
    });
  const equipmentMappingEntries = equipmentMappings
    .map((row, index) => ({
      row,
      index,
      rowKey: buildEquipmentMappingRowKey(row, index),
    }))
    .sort((left, right) => {
      const leftPriority = left.row.is_required_for_recent_processing
        ? 0
        : left.row.is_observed && !left.row.target_category.trim()
          ? 1
          : 2;
      const rightPriority = right.row.is_required_for_recent_processing
        ? 0
        : right.row.is_observed && !right.row.target_category.trim()
          ? 1
          : 2;
      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }
      return buildEquipmentMappingRowKey(left.row, left.index).localeCompare(buildEquipmentMappingRowKey(right.row, right.index));
    });

  const defaultOmitValidation = useMemo(() => buildDefaultOmitValidation(defaultOmitRules), [defaultOmitRules]);
  const laborMappingValidation = useMemo(
    () => buildLaborMappingValidation(laborMappings, laborTargets),
    [laborMappings, laborTargets],
  );
  const equipmentMappingValidation = useMemo(
    () => buildEquipmentMappingValidation(equipmentMappings, equipmentTargets),
    [equipmentMappings, equipmentTargets],
  );
  const laborClassificationValidation = useMemo(
    () => buildClassificationValidation(laborSlots, "labor", laborActiveCapacity),
    [laborActiveCapacity, laborSlots],
  );
  const equipmentClassificationValidation = useMemo(
    () => buildClassificationValidation(equipmentSlots, "equipment", equipmentActiveCapacity),
    [equipmentActiveCapacity, equipmentSlots],
  );
  const exportSettingsValidation = useMemo(() => buildExportSettingsValidation(exportSettings), [exportSettings]);
  const effectiveLaborRates = useMemo(
    () =>
      selectedProfileDraft
        ? filterLaborRatesForCurrentSlots(laborRates, selectedProfileDraft.labor_slots, laborSlots)
        : laborRates,
    [selectedProfileDraft, laborRates, laborSlots],
  );
  const effectiveEquipmentRates = useMemo(
    () =>
      selectedProfileDraft
        ? filterEquipmentRatesForCurrentSlots(equipmentRates, selectedProfileDraft.equipment_slots, equipmentSlots)
        : equipmentRates,
    [selectedProfileDraft, equipmentRates, equipmentSlots],
  );
  const retiredLaborRateLabels = useMemo(
    () =>
      selectedProfileDraft
        ? buildRetiredLaborRateLabels(laborRates, selectedProfileDraft.labor_slots, laborSlots)
        : [],
    [selectedProfileDraft, laborRates, laborSlots],
  );
  const retiredEquipmentRateLabels = useMemo(
    () =>
      selectedProfileDraft
        ? buildRetiredEquipmentRateLabels(equipmentRates, selectedProfileDraft.equipment_slots, equipmentSlots)
        : [],
    [selectedProfileDraft, equipmentRates, equipmentSlots],
  );
  const classificationIssueCount =
    laborClassificationValidation.messages.length + equipmentClassificationValidation.messages.length;
  const ratesValidation = useMemo(() => buildRatesValidation(laborRates, equipmentRates), [equipmentRates, laborRates]);

  const defaultOmitDirty = selectedProfileDraft ? !compareRows(defaultOmitRules, selectedProfileDraft.default_omit_rules) : false;
  const laborMappingsDirty = selectedProfileDraft ? !compareRows(laborMappings, selectedProfileDraft.labor_mappings) : false;
  const equipmentMappingsDirty = selectedProfileDraft ? !compareRows(equipmentMappings, selectedProfileDraft.equipment_mappings) : false;
  const classificationsDirty =
    selectedProfileDraft &&
    (!compareRows(laborSlots, selectedProfileDraft.labor_slots) || !compareRows(equipmentSlots, selectedProfileDraft.equipment_slots));
  const localRatesDirty =
    selectedProfileDraft &&
    (!compareRows(laborRates, selectedProfileDraft.labor_rates) || !compareRows(equipmentRates, selectedProfileDraft.equipment_rates));
  const exportSettingsDirty =
    selectedProfileDraft &&
    !compareValue(exportSettings, selectedProfileDraft.export_settings);
  const retiredRatesDirty =
    selectedProfileDraft &&
    (!compareRows(effectiveLaborRates, selectedProfileDraft.labor_rates) ||
      !compareRows(effectiveEquipmentRates, selectedProfileDraft.equipment_rates));
  const ratesDirty = Boolean(localRatesDirty || retiredRatesDirty);
  const currentDraftHydrationKey = selectedProfileDraft
    ? `${selectedProfileDraft.trusted_profile_draft_id}:${selectedProfileDraft.draft_content_hash}`
    : null;

  const dirtySections = [
    defaultOmitDirty ? "default omit rules" : "",
    laborMappingsDirty ? "labor mappings" : "",
    equipmentMappingsDirty ? "equipment mappings" : "",
    classificationsDirty ? "classifications" : "",
    exportSettingsDirty ? "export settings" : "",
    ratesDirty ? "rates" : "",
  ].filter(Boolean);

  const hasLocalValidationIssues =
    (defaultOmitDirty && defaultOmitValidation.messages.length > 0) ||
    (laborMappingsDirty && laborMappingValidation.messages.length > 0) ||
    (equipmentMappingsDirty && equipmentMappingValidation.messages.length > 0) ||
    (classificationsDirty && classificationIssueCount > 0) ||
    (exportSettingsDirty && exportSettingsValidation.messages.length > 0) ||
    (ratesDirty && ratesValidation.messages.length > 0);

  const saveProfileDisabled =
    busy ||
    !selectedProfileDraft ||
    hasLocalValidationIssues ||
    selectedProfileDraft.validation_errors.length > 0;

  const saveReadinessLabel = !selectedProfileDraft
    ? "Select Edit current profile"
    : selectedProfileDraft.validation_errors.length > 0 || hasLocalValidationIssues
      ? "Fix validation issues"
      : dirtySections.length === 0
        ? "Save to clear unpublished changes"
        : "Ready to save profile settings";

  const saveReadinessTone = !selectedProfileDraft
    ? "neutral"
    : selectedProfileDraft.validation_errors.length > 0 || hasLocalValidationIssues
      ? "error"
      : "success";
  const createProfileValidation = useMemo(
    () => buildCreateProfileValidation(newProfileDisplayName, trustedProfiles),
    [newProfileDisplayName, trustedProfiles],
  );
  const generatedProfileName = useMemo(
    () => buildProfileNameFromDisplayName(newProfileDisplayName),
    [newProfileDisplayName],
  );
  const createProfileDisplayMessages = mergeMessages(
    createProfileValidation.rowErrors[0],
    createServerFieldErrors.profile_name,
    createServerFieldErrors.display_name,
  );
  const currentPublishedVersionNumber =
    selectedProfileDetail?.current_published_version.version_number ??
    selectedProfileDraft?.current_published_version.version_number ??
    selectedTrustedProfile?.current_published_version_number ??
    null;
  const selectedProfileSourceLabel = selectedTrustedProfile ? profileSourceLabel(selectedTrustedProfile.source_kind) : "";
  const canArchiveSelectedProfile =
    selectedTrustedProfile?.source_kind === "published_clone" &&
    !openDraftId &&
    !selectedProfileDraft;
  const createProfileDisabled =
    busy ||
    !selectedTrustedProfile ||
    createProfileValidation.messages.length > 0;
  const selectedRetainedDraftState = selectedTrustedProfileId
    ? retainedDraftStates[selectedTrustedProfileId] ?? null
    : null;
  const workspaceViewLabel = selectedProfileDraft
    ? "Editing current profile"
    : "Viewing live profile";
  const workspaceViewTone = selectedProfileDraft ? "warning" : "neutral";
  const canOpenCurrentProfile = Boolean(selectedTrustedProfile && selectedProfileDetail);

  useEffect(() => {
    const validKeys = new Set(laborMappingEntries.map((entry) => entry.rowKey));
    setSelectedLaborMappingKeys((current) => {
      const next = current.filter((rowKey) => validKeys.has(rowKey));
      return next.length === current.length && next.every((rowKey, index) => rowKey === current[index]) ? current : next;
    });
  }, [laborMappingEntries]);

  useEffect(() => {
    const validKeys = new Set(equipmentMappingEntries.map((entry) => entry.rowKey));
    setSelectedEquipmentMappingKeys((current) => {
      const next = current.filter((rowKey) => validKeys.has(rowKey));
      return next.length === current.length && next.every((rowKey, index) => rowKey === current[index]) ? current : next;
    });
  }, [equipmentMappingEntries]);

  useEffect(() => {
    if (
      !selectedProfileDraft ||
      !selectedTrustedProfileId ||
      !currentDraftHydrationKey
    ) {
      hydratedDraftKeyRef.current = null;
      return;
    }
    if (dirtySections.length === 0) {
      hydratedDraftKeyRef.current = currentDraftHydrationKey;
    }
  }, [currentDraftHydrationKey, dirtySections.length, selectedProfileDraft, selectedTrustedProfileId]);

  useEffect(() => {
    if (!selectedTrustedProfileId || !selectedProfileDraft) {
      return;
    }
    if (!currentDraftHydrationKey || hydratedDraftKeyRef.current !== currentDraftHydrationKey) {
      return;
    }

    setRetainedDraftStates((current) => {
      const existing = current[selectedTrustedProfileId];
      if (dirtySections.length === 0) {
        if (!existing) {
          return current;
        }
        const next = { ...current };
        delete next[selectedTrustedProfileId];
        return next;
      }

      const nextState: RetainedDraftWorkspaceState = {
        trusted_profile_id: selectedProfileDraft.trusted_profile_id,
        trusted_profile_draft_id: selectedProfileDraft.trusted_profile_draft_id,
        draft_content_hash: selectedProfileDraft.draft_content_hash,
        published_version_number: selectedProfileDraft.current_published_version.version_number,
        default_omit_rules: cloneRows(defaultOmitRules),
        labor_mappings: cloneRows(laborMappings),
        equipment_mappings: cloneRows(equipmentMappings),
        labor_slots: cloneRows(laborSlots),
        equipment_slots: cloneRows(equipmentSlots),
        export_settings: { labor_minimum_hours: { ...exportSettings.labor_minimum_hours } },
        labor_rates: cloneRows(laborRates),
        equipment_rates: cloneRows(equipmentRates),
        dirty_sections: [...dirtySections],
      };

      if (existing && JSON.stringify(existing) === JSON.stringify(nextState)) {
        return current;
      }

      return {
        ...current,
        [selectedTrustedProfileId]: nextState,
      };
    });
  }, [
    defaultOmitRules,
    dirtySections,
    selectedProfileDraft,
    equipmentMappings,
    equipmentRates,
    equipmentSlots,
    exportSettings,
    laborMappings,
    laborRates,
    laborSlots,
    currentDraftHydrationKey,
    selectedTrustedProfileId,
  ]);

  function handleLaborMappingSelectionChange(rowKey: string, isSelected: boolean) {
    setSelectedLaborMappingKeys((current) => {
      if (isSelected) {
        return current.includes(rowKey) ? current : [...current, rowKey];
      }
      return current.filter((candidate) => candidate !== rowKey);
    });
  }

  function handleEquipmentMappingSelectionChange(rowKey: string, isSelected: boolean) {
    setSelectedEquipmentMappingKeys((current) => {
      if (isSelected) {
        return current.includes(rowKey) ? current : [...current, rowKey];
      }
      return current.filter((candidate) => candidate !== rowKey);
    });
  }

  function handleBulkLaborTargetApply() {
    const nextTarget = bulkLaborTarget.trim();
    if (!nextTarget || selectedLaborMappingKeys.length === 0) {
      return;
    }
    const selectedKeySet = new Set(selectedLaborMappingKeys);
    setLaborMappings(
      laborMappings.map((row, index) =>
        selectedKeySet.has(buildLaborMappingRowKey(row, index))
          ? { ...row, target_classification: nextTarget, is_required_for_recent_processing: false }
          : row,
      ),
    );
    setSelectedLaborMappingKeys([]);
    setBulkLaborTarget("");
  }

  function handleBulkEquipmentTargetApply() {
    const nextTarget = bulkEquipmentTarget.trim();
    if (!nextTarget || selectedEquipmentMappingKeys.length === 0) {
      return;
    }
    const selectedKeySet = new Set(selectedEquipmentMappingKeys);
    setEquipmentMappings(
      equipmentMappings.map((row, index) =>
        selectedKeySet.has(buildEquipmentMappingRowKey(row, index))
          ? {
              ...row,
              target_category: nextTarget,
              is_required_for_recent_processing: false,
              prediction_target: null,
              prediction_confidence_label: null,
            }
          : row,
      ),
    );
    setSelectedEquipmentMappingKeys([]);
    setBulkEquipmentTarget("");
  }

  function handleApplyEquipmentPrediction(rowIndex: number, predictionTarget: string) {
    setEquipmentMappings(
      equipmentMappings.map((row, index) =>
        index === rowIndex
          ? {
              ...row,
              target_category: predictionTarget,
              is_required_for_recent_processing: false,
              prediction_target: null,
              prediction_confidence_label: null,
            }
          : row,
      ),
    );
  }

  async function saveAllDirtySections(): Promise<boolean> {
    if (!selectedProfileDraft) {
      return true;
    }
    if (defaultOmitDirty && defaultOmitValidation.messages.length > 0) {
      return false;
    }
    if (laborMappingsDirty && laborMappingValidation.messages.length > 0) {
      return false;
    }
    if (equipmentMappingsDirty && equipmentMappingValidation.messages.length > 0) {
      return false;
    }
    if (classificationsDirty && classificationIssueCount > 0) {
      return false;
    }
    if (exportSettingsDirty && exportSettingsValidation.messages.length > 0) {
      return false;
    }
    if (ratesDirty && ratesValidation.messages.length > 0) {
      return false;
    }
    if (dirtySections.length === 0) {
      return true;
    }
    if (
      !(await onSaveDraft({
        default_omit_rules: defaultOmitRules,
        labor_mappings: laborMappings,
        equipment_mappings: equipmentMappings,
        labor_slots: laborSlots,
        equipment_slots: equipmentSlots,
        labor_rates: effectiveLaborRates,
        equipment_rates: effectiveEquipmentRates,
        export_settings: exportSettings,
      }))
    ) {
      return false;
    }
    setRestoredDraftNotice("");
    return true;
  }

  async function handlePrimarySettingsAction() {
    if (!selectedProfileDraft) {
      await onOpenDraft();
      return;
    }
    const saved = await saveAllDirtySections();
    if (!saved) {
      return;
    }
    await onPublishDraft(selectedProfileDraft.trusted_profile_draft_id);
  }

  async function discardCurrentDraft(): Promise<boolean> {
    if (!openDraftId) {
      return true;
    }
    const discarded = await onDiscardDraft(openDraftId);
    if (!discarded) {
      return false;
    }
    setRestoredDraftNotice("");
    hydratedDraftKeyRef.current = null;
    if (selectedTrustedProfileId) {
      setRetainedDraftStates((current) => {
        if (!current[selectedTrustedProfileId]) {
          return current;
        }
        const next = { ...current };
        delete next[selectedTrustedProfileId];
        return next;
      });
    }
    return true;
  }

  useEffect(() => {
    if (!onLeaveGuardChange) {
      return;
    }
    onLeaveGuardChange({
      hasUnpublishedChanges: Boolean(openDraftId),
      dirtySections: [...dirtySections],
      draftId: openDraftId,
      profileDisplayName: selectedTrustedProfile?.display_name ?? "this trusted profile",
      saveAllDirtySections,
      discardCurrentDraft,
    });
    return () => {
      onLeaveGuardChange(null);
    };
  }, [
    dirtySections,
    discardCurrentDraft,
    openDraftId,
    onLeaveGuardChange,
    saveAllDirtySections,
    selectedTrustedProfile?.display_name,
  ]);

  async function handleCreateProfile() {
    setCreateServerFieldErrors({});
    setCreateServerMessage("");
    try {
      await onCreateTrustedProfile({
        profile_name: generatedProfileName,
        display_name: newProfileDisplayName.trim(),
        description: newProfileDescription.trim(),
      });
      setNewProfileDisplayName("");
      setNewProfileDescription("");
    } catch (error) {
      if (error instanceof ApiRequestError) {
        setCreateServerFieldErrors(error.fieldErrors);
        const hasFieldErrors = Object.keys(error.fieldErrors).length > 0;
        setCreateServerMessage(hasFieldErrors ? "" : error.message);
        return;
      }
      setCreateServerMessage(error instanceof Error ? error.message : "Failed to create the trusted profile.");
    }
  }

  function handleTrustedProfileSelection(nextProfileName: string) {
    if (!nextProfileName || nextProfileName === selectedTrustedProfileName) {
      return;
    }
    onTrustedProfileNameChange(nextProfileName);
  }

  async function handleArchiveProfile() {
    if (!selectedTrustedProfile) {
      return;
    }
    if (
      !window.confirm(
        `Archive ${selectedTrustedProfile.display_name}? Archived profiles stay in lineage history but disappear from active web selectors.`,
      )
    ) {
      return;
    }
    await onArchiveTrustedProfile();
  }

  async function handleUnarchiveProfile(profile: TrustedProfileResponse) {
    if (
      !window.confirm(
        `Restore ${profile.display_name} to the active trusted profile lists? Restored profiles become selectable again for settings and future review runs.`,
      )
    ) {
      return;
    }
    await onUnarchiveTrustedProfile(profile.trusted_profile_id, profile.display_name);
  }

  return (
    <section className="workspace-shell settings-shell">
      <h2 className="sr-only">{selectedTrustedProfile?.display_name ?? "Choose a trusted profile"}</h2>

      <div className="settings-console">
        <aside className="settings-sidebar-column" aria-label="Profile settings controls">
          <div className="summary-card settings-summary-card">
            <label className="field">
            <span>Trusted profile</span>
            <select
              aria-label="Settings trusted profile"
              value={selectedTrustedProfileName}
              onChange={(event) => handleTrustedProfileSelection(event.target.value)}
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
              <button
                type="button"
                onClick={() => void handlePrimarySettingsAction()}
                disabled={selectedProfileDraft ? saveProfileDisabled : busy || profileDetailLoading || !canOpenCurrentProfile}
              >
                {selectedProfileDraft ? "Save profile settings" : "Edit current profile"}
              </button>
            </div>
            <p className="muted">
              Live profile settings drive processing. Changes stay in this editor until you save profile settings.
            </p>
            {trustedProfiles.length > 0 ? (
              <div className="workspace-callout">
              <strong>Profiles in this organization</strong>
              <div className="profile-list profile-list-selector">
                {trustedProfiles.map((profile) => (
                  <button
                    key={profile.trusted_profile_id}
                    type="button"
                    aria-label={profile.display_name}
                    aria-pressed={profile.profile_name === selectedTrustedProfileName}
                    className={profile.profile_name === selectedTrustedProfileName ? "profile-list-item active" : "profile-list-item"}
                    onClick={() => handleTrustedProfileSelection(profile.profile_name)}
                    disabled={busy}
                  >
                    <div className="profile-list-item-summary">
                      <strong className="profile-list-item-name">{profile.display_name}</strong>
                    </div>
                    <div className="profile-list-item-version">
                      <StatusPill tone="neutral">v{profile.current_published_version_number}</StatusPill>
                    </div>
                    {profile.has_open_draft ? (
                      <div className="settings-inline-status profile-list-item-badges">
                      {profile.has_open_draft ? <StatusPill tone="warning">Unpublished changes</StatusPill> : null}
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>
            ) : null}
            <div className="workspace-callout">
            <strong>Create another trusted profile</strong>
            <p>
              New profiles start from the currently selected profile&apos;s live version only. Unpublished profile
              changes and browser-only edits are not copied.
            </p>
            {createServerMessage ? (
              <div className="banner warning" role="status">
                <strong>Create profile could not be completed.</strong>
                <p>{createServerMessage}</p>
              </div>
            ) : null}
            {selectedTrustedProfile ? (
              <p className="muted">
                Seed source: {selectedTrustedProfile.display_name} ({selectedProfileSourceLabel}), live version v
                {currentPublishedVersionNumber ?? selectedTrustedProfile.current_published_version_number}.
              </p>
            ) : null}
            <label className="field">
              <span>Display name</span>
              <input
                aria-label="New profile display name"
                aria-invalid={createProfileDisplayMessages.length > 0 ? "true" : "false"}
                className={createProfileDisplayMessages.length > 0 ? "field-invalid" : undefined}
                value={newProfileDisplayName}
                onChange={(event) => setNewProfileDisplayName(event.target.value.slice(0, MAX_PROFILE_DISPLAY_NAME_LENGTH))}
                placeholder="Alternate Profile"
                disabled={busy || !selectedTrustedProfile}
              />
              <RowMessages messages={createProfileDisplayMessages} />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                aria-label="New profile description"
                value={newProfileDescription}
                onChange={(event) => setNewProfileDescription(event.target.value)}
                rows={3}
                placeholder="Describe when this trusted profile should be used."
                disabled={busy || !selectedTrustedProfile}
              />
            </label>
            {createProfileValidation.messages.length > 0 &&
            createProfileValidation.messages.some(
              (message) =>
                !createProfileDisplayMessages.includes(message),
            ) ? (
              <RowMessages
                messages={createProfileValidation.messages.filter(
                  (message) => !createProfileDisplayMessages.includes(message),
                )}
              />
            ) : null}
            <div className="actions">
              <button type="button" onClick={() => void handleCreateProfile()} disabled={createProfileDisabled}>
                Create profile from published version
              </button>
            </div>
            <p className="muted">Profile keys are stable logical ids and should be treated as permanent.</p>
            </div>
            {selectedTrustedProfile ? (
              <div className="workspace-callout">
              <strong>Selected profile state</strong>
              <div className="settings-inline-status">
                <StatusPill tone="neutral">{selectedTrustedProfile.display_name}</StatusPill>
                <StatusPill tone={profileSourceTone(selectedTrustedProfile.source_kind)}>
                  {selectedProfileSourceLabel}
                </StatusPill>
                <StatusPill tone={selectedTrustedProfile.has_open_draft ? "warning" : "success"}>
                  {selectedTrustedProfile.has_open_draft ? "Unpublished changes" : "Live only"}
                </StatusPill>
                <StatusPill tone="neutral">Live v{selectedTrustedProfile.current_published_version_number}</StatusPill>
                <StatusPill tone={workspaceViewTone}>{workspaceViewLabel}</StatusPill>
                {selectedRetainedDraftState ? <StatusPill tone="warning">Local unsaved edits retained</StatusPill> : null}
                {selectedTrustedProfile.is_active_profile ? <StatusPill tone="neutral">Desktop active</StatusPill> : null}
              </div>
              <p className="muted">
                The selected profile controls both the live profile view and any unpublished changes you continue in
                this tab. Local unsaved browser edits stay scoped to one profile at a time.
              </p>
            </div>
          ) : null}
            <div className="workspace-callout">
            <strong>Profile lifecycle</strong>
            <p>User-created profiles can be archived to remove them from active web selectors without deleting published history.</p>
            <div className="actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => void handleArchiveProfile()}
                disabled={busy || !canArchiveSelectedProfile}
              >
                Archive selected profile
              </button>
            </div>
            <p className="muted">
              {selectedTrustedProfile?.source_kind !== "published_clone"
                ? "Bundled default profiles stay read-only in hosted settings. Create a web-owned profile when you need organization-specific changes."
                : openDraftId
                  ? "Save or discard the unpublished profile changes before archiving this profile."
                  : "Archiving hides the profile from active selectors but preserves its versions, runs, and review lineage history."}
            </p>
            </div>
            <div className="workspace-callout">
            <strong>Archived profiles</strong>
            <p className="muted">
              Archived profiles remain in lineage history, stay out of active review/profile selectors, and cannot be
              edited until they are restored.
            </p>
            {archivedTrustedProfiles.length === 0 ? (
              <p className="empty-state">No archived trusted profiles are currently stored for this organization.</p>
            ) : (
              <div className="profile-list">
                {archivedTrustedProfiles.map((profile) => (
                  <div key={profile.trusted_profile_id} className="profile-list-item archived">
                    <div>
                      <strong>{profile.display_name}</strong>
                      <p className="muted">{profile.profile_name}</p>
                      <p className="muted">Archived {formatArchivedAt(profile.archived_at)}</p>
                    </div>
                    <div className="settings-inline-status">
                      <StatusPill tone={profileSourceTone(profile.source_kind)}>{profileSourceLabel(profile.source_kind)}</StatusPill>
                      <StatusPill tone="neutral">v{profile.current_published_version_number}</StatusPill>
                      <StatusPill tone="warning">Archived</StatusPill>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void handleUnarchiveProfile(profile)}
                        disabled={busy}
                      >
                        Restore to active profiles
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            </div>
          </div>
        </aside>

        <div className="settings-content-column">
          {!selectedTrustedProfile ? (
            <div className="panel empty-workspace">
              <p className="empty-state">Choose a trusted profile to inspect the live configuration and edit the current profile.</p>
            </div>
          ) : null}

          {settingsErrorMessage ? (
            <div className="banner error" role="alert">
              <strong>Settings workflow needs attention</strong>
              <p>{settingsErrorMessage}</p>
              {selectedProfileDraft ? (
                <p className="muted">Unsaved browser edits remain on screen while you retry or continue adjusting the current profile.</p>
              ) : null}
              <div className="actions">
                {!selectedProfileDetail ? (
                  <button type="button" className="secondary-button" onClick={() => void onReloadProfileDetail()} disabled={busy}>
                    Retry loading live profile
                  </button>
                ) : !selectedProfileDraft ? (
                  <button type="button" className="secondary-button" onClick={() => void onOpenDraft()} disabled={busy}>
                    Retry editing current profile
                  </button>
                ) : (
                  <button type="button" className="secondary-button" onClick={() => void onReloadProfileDetail()} disabled={busy}>
                    Reload live summary
                  </button>
                )}
              </div>
            </div>
          ) : null}

          {selectedProfileDetail ? (
            <div className="settings-grid settings-content-grid">
              <div className="panel settings-main settings-console-main">
            <div className="settings-status-strip">
              <div className="status-block settings-status-card">
                <strong>Live profile</strong>
                <p>Live version v{selectedProfileDetail.current_published_version.version_number} remains the web-processing source.</p>
              </div>
              <div className="status-block settings-status-card">
                <strong>Editing state</strong>
                <p>{selectedProfileDraft ? "Editing current profile settings." : "Viewing live profile settings only."}</p>
              </div>
              <div className="status-block settings-status-card">
                <strong>Browser changes</strong>
                <p>
                  {selectedProfileDraft
                    ? dirtySections.length > 0
                      ? `${dirtySections.length} section(s) still need saving.`
                      : "All browser edits match the current unpublished profile changes."
                    : selectedRetainedDraftState
                      ? "Unpublished profile changes are retained in this tab. Select Edit current profile to keep working."
                      : "No local profile edits are currently retained in this tab."}
                </p>
              </div>
              <div className="status-block settings-status-card">
                <strong>Save status</strong>
                <p>{saveReadinessLabel}</p>
              </div>
            </div>

            {!selectedProfileDraft && selectedRetainedDraftState ? (
              <div className="workspace-callout">
                <strong>Unpublished profile changes are retained for this profile.</strong>
                <p>
                  This tab kept {selectedRetainedDraftState.dirty_sections.join(", ")} ready to continue the next time
                  you select <em>Edit current profile</em>.
                </p>
              </div>
            ) : null}

            {draftState ? (
              <>
                {draftState.validation_errors.length > 0 ? (
                  <div className="banner warning">
                    <strong>Profile settings need attention before saving.</strong>
                    <ul className="message-list">
                      {draftState.validation_errors.map((issue) => (
                        <li key={issue}>{issue}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {observedDraftNote ? (
                  <div className="banner warning" role="status">
                    <strong>Observed placeholders remain in these profile changes.</strong>
                    <p>
                      Rows tagged <ObservedBadge /> were auto-added from unmapped values seen during processing. They
                      may remain blank and still be saved.
                    </p>
                  </div>
                ) : null}

                <div className="workspace-callout success">
                  <strong>Editing current profile</strong>
                  <p>
                    Based on live version v{draftState.current_published_version.version_number}. Saving profile
                    settings publishes these changes for future processing.
                  </p>
                  <div className="settings-inline-status">
                    <StatusPill tone="neutral">Live v{draftState.current_published_version.version_number}</StatusPill>
                    <StatusPill tone={dirtySections.length > 0 ? "warning" : "success"}>
                      {dirtySections.length > 0 ? `${dirtySections.length} unsaved section(s)` : "No unsaved browser changes"}
                    </StatusPill>
                    <StatusPill tone={saveReadinessTone}>{saveReadinessLabel}</StatusPill>
                  </div>
                  {restoredDraftNotice ? (
                    <p className="muted">{restoredDraftNotice}</p>
                  ) : null}
                  <div className="actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void discardCurrentDraft()}
                      disabled={busy}
                    >
                      Discard profile changes
                    </button>
                  </div>
                </div>

                {dirtySections.length > 0 ? (
                  <div className="workspace-callout">
                    <strong>Profile settings are waiting on unsaved sections.</strong>
                    <p>Save profile settings to apply {dirtySections.join(", ")} to the live profile.</p>
                  </div>
                ) : null}

                {hasLocalValidationIssues ? (
                  <div className="banner warning" role="status">
                    <strong>Fix inline issues before saving profile settings.</strong>
                    <p>The affected fields are marked directly in the editable Phase 2A sections below.</p>
                  </div>
                ) : null}

                <div className="settings-section">
                  <SectionHeader
                    title="Default Omit Rules"
                    description="Edit the phase codes that start omitted by default for future runs."
                    action={
                      <SectionStatusPill
                        dirty={defaultOmitDirty}
                        errorCount={defaultOmitValidation.messages.length}
                      />
                    }
                  />
                  {defaultOmitValidation.messages.length > 0 ? <RowMessages messages={defaultOmitValidation.messages} /> : null}
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
                        {defaultOmitRules.length === 0 ? (
                          <tr>
                            <td colSpan={3}>
                              <p className="empty-state">No default omit rules are saved yet.</p>
                            </td>
                          </tr>
                        ) : (
                          defaultOmitRules.map((row, index) => (
                            <tr key={`default-omit-${index}`}>
                              <td>
                                <input
                                  aria-label={`Default omit phase code ${index + 1}`}
                                  aria-invalid={defaultOmitValidation.rowErrors[index] ? "true" : "false"}
                                  className={defaultOmitValidation.rowErrors[index] ? "field-invalid" : undefined}
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
                                <RowMessages messages={defaultOmitValidation.rowErrors[index]} />
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
                          ))
                        )}
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
                      <SectionStatusPill
                        dirty={laborMappingsDirty}
                        errorCount={laborMappingValidation.messages.length}
                      />
                    }
                  />
                  <p className="muted">
                    Required unmapped labor values from recent processing appear first. Observed rows were auto-added from
                    labor values seen during processing and can stay blank until you are ready to map them.
                  </p>
                  {laborMappingValidation.messages.length > 0 ? <RowMessages messages={laborMappingValidation.messages} /> : null}
                  <div className="review-bulk-bar settings-bulk-bar">
                    <div>
                      <strong>{selectedLaborMappingKeys.length} labor row{selectedLaborMappingKeys.length === 1 ? "" : "s"} selected</strong>
                      <p className="muted">Choose one labor target to apply it across the current mapping selection.</p>
                    </div>
                    <div className="actions review-bulk-actions">
                      <label className="field bulk-field">
                        <span>Bulk labor target</span>
                        <select
                          aria-label="Bulk labor mapping target"
                          value={bulkLaborTarget}
                          onChange={(event) => setBulkLaborTarget(event.target.value)}
                          disabled={busy || laborMappings.length === 0}
                        >
                          <option value="">Choose labor target</option>
                          {laborTargets.map((target) => (
                            <option key={`labor-bulk-target-${target}`} value={target}>
                              {target}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={handleBulkLaborTargetApply}
                        disabled={busy || selectedLaborMappingKeys.length === 0 || !bulkLaborTarget.trim()}
                      >
                        Apply labor target
                      </button>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Select</th>
                          <th>Raw value</th>
                          <th>Target classification</th>
                          <th>Notes</th>
                          <th>Source</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {laborMappings.length === 0 ? (
                          <tr>
                            <td colSpan={6}>
                              <p className="empty-state">No labor mappings are saved yet. Add a row to start building this domain.</p>
                            </td>
                          </tr>
                        ) : (
                          laborMappingEntries.map(({ row, index, rowKey }) => (
                            <tr
                              key={`labor-mapping-${rowKey}`}
                              className={row.is_required_for_recent_processing ? "mapping-row-required" : undefined}
                            >
                              <td>
                                <input
                                  aria-label={`Select labor mapping ${index + 1}`}
                                  type="checkbox"
                                  checked={selectedLaborMappingKeys.includes(rowKey)}
                                  onChange={(event) => handleLaborMappingSelectionChange(rowKey, event.target.checked)}
                                />
                              </td>
                              <td>
                                <input
                                  aria-label={`Labor raw value ${index + 1}`}
                                  aria-invalid={laborMappingValidation.rowErrors[index] ? "true" : "false"}
                                  className={laborMappingValidation.rowErrors[index] ? "field-invalid" : undefined}
                                  value={row.raw_value}
                                  onChange={(event) =>
                                    setLaborMappings(
                                      laborMappings.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, raw_value: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                                <RowMessages messages={laborMappingValidation.rowErrors[index]} />
                              </td>
                              <td>
                                <select
                                  aria-label={`Labor target classification ${index + 1}`}
                                  value={row.target_classification}
                                  onChange={(event) =>
                                    setLaborMappings(
                                      laborMappings.map((item, itemIndex) =>
                                        itemIndex === index
                                          ? {
                                              ...item,
                                              target_classification: event.target.value,
                                              is_required_for_recent_processing: event.target.value.trim().length > 0 ? false : item.is_required_for_recent_processing,
                                            }
                                          : item,
                                      ),
                                    )
                                  }
                                >
                                  <option value="">Unmapped</option>
                                  {buildTargetOptions(row.target_classification, laborTargets).map((target) => (
                                    <option key={target} value={target}>
                                      {laborTargets.includes(target) ? target : `${target} (inactive or renamed)`}
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
                              <td>
                                <div className="mapping-badge-stack">
                                  {row.is_required_for_recent_processing && !row.target_classification.trim() ? (
                                    <RequiredObservedBadge />
                                  ) : null}
                                  {row.is_observed ? <ObservedBadge /> : <span className="muted">User row</span>}
                                </div>
                              </td>
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
                          ))
                        )}
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
                      <SectionStatusPill
                        dirty={equipmentMappingsDirty}
                        errorCount={equipmentMappingValidation.messages.length}
                      />
                    }
                  />
                  <p className="muted">
                    Required unmapped equipment keys from recent processing appear first. Advisory suggestions can help
                    you map repeated raw keys faster, but nothing auto-applies without your choice.
                  </p>
                  {equipmentMappingValidation.messages.length > 0 ? <RowMessages messages={equipmentMappingValidation.messages} /> : null}
                  <div className="review-bulk-bar settings-bulk-bar">
                    <div>
                      <strong>{selectedEquipmentMappingKeys.length} equipment row{selectedEquipmentMappingKeys.length === 1 ? "" : "s"} selected</strong>
                      <p className="muted">Choose one equipment class to apply it across the current mapping selection.</p>
                    </div>
                    <div className="actions review-bulk-actions">
                      <label className="field bulk-field">
                        <span>Bulk equipment target</span>
                        <select
                          aria-label="Bulk equipment mapping target"
                          value={bulkEquipmentTarget}
                          onChange={(event) => setBulkEquipmentTarget(event.target.value)}
                          disabled={busy || equipmentMappings.length === 0}
                        >
                          <option value="">Choose equipment class</option>
                          {equipmentTargets.map((target) => (
                            <option key={`equipment-bulk-target-${target}`} value={target}>
                              {target}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={handleBulkEquipmentTargetApply}
                        disabled={busy || selectedEquipmentMappingKeys.length === 0 || !bulkEquipmentTarget.trim()}
                      >
                        Apply equipment class
                      </button>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Select</th>
                          <th>Raw description</th>
                          <th>Target category</th>
                          <th>Source</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {equipmentMappings.length === 0 ? (
                          <tr>
                            <td colSpan={5}>
                              <p className="empty-state">No equipment mappings are saved yet. Add a row to start building this domain.</p>
                            </td>
                          </tr>
                        ) : (
                          equipmentMappingEntries.map(({ row, index, rowKey }) => (
                            <tr
                              key={`equipment-mapping-${rowKey}`}
                              className={row.is_required_for_recent_processing ? "mapping-row-required" : undefined}
                            >
                              <td>
                                <input
                                  aria-label={`Select equipment mapping ${index + 1}`}
                                  type="checkbox"
                                  checked={selectedEquipmentMappingKeys.includes(rowKey)}
                                  onChange={(event) => handleEquipmentMappingSelectionChange(rowKey, event.target.checked)}
                                />
                              </td>
                              <td>
                                <input
                                  aria-label={`Equipment raw description ${index + 1}`}
                                  aria-invalid={equipmentMappingValidation.rowErrors[index] ? "true" : "false"}
                                  className={equipmentMappingValidation.rowErrors[index] ? "field-invalid" : undefined}
                                  value={row.raw_description}
                                  onChange={(event) =>
                                    setEquipmentMappings(
                                      equipmentMappings.map((item, itemIndex) =>
                                        itemIndex === index
                                          ? { ...item, raw_description: event.target.value }
                                          : item,
                                      ),
                                    )
                                  }
                                />
                                {row.raw_pattern && row.raw_pattern !== row.raw_description ? (
                                  <div className="cell-secondary">Canonical raw key: {row.raw_pattern}</div>
                                ) : null}
                                <RowMessages messages={equipmentMappingValidation.rowErrors[index]} />
                              </td>
                              <td>
                                <select
                                  aria-label={`Equipment target category ${index + 1}`}
                                  value={row.target_category}
                                  onChange={(event) =>
                                    setEquipmentMappings(
                                      equipmentMappings.map((item, itemIndex) =>
                                        itemIndex === index
                                          ? {
                                              ...item,
                                              target_category: event.target.value,
                                              is_required_for_recent_processing: event.target.value.trim().length > 0 ? false : item.is_required_for_recent_processing,
                                              prediction_target: event.target.value.trim().length > 0 ? null : item.prediction_target,
                                              prediction_confidence_label:
                                                event.target.value.trim().length > 0 ? null : item.prediction_confidence_label,
                                            }
                                          : item,
                                      ),
                                    )
                                  }
                                >
                                  <option value="">Unmapped</option>
                                  {buildTargetOptions(row.target_category, equipmentTargets).map((target) => (
                                    <option key={target} value={target}>
                                      {equipmentTargets.includes(target) ? target : `${target} (inactive or renamed)`}
                                    </option>
                                  ))}
                                </select>
                                {!row.target_category.trim() && row.prediction_target ? (
                                  <div className="cell-secondary prediction-callout">
                                    <span>{row.prediction_confidence_label ?? "Suggested"}: {row.prediction_target}</span>
                                    <button
                                      type="button"
                                      className="tertiary-button inline-button"
                                      onClick={() => handleApplyEquipmentPrediction(index, row.prediction_target ?? "")}
                                      disabled={busy}
                                    >
                                      Use suggestion
                                    </button>
                                  </div>
                                ) : null}
                              </td>
                              <td>
                                <div className="mapping-badge-stack">
                                  {row.is_required_for_recent_processing && !row.target_category.trim() ? (
                                    <RequiredObservedBadge />
                                  ) : null}
                                  {row.is_observed ? <ObservedBadge /> : <span className="muted">User row</span>}
                                </div>
                              </td>
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
                          ))
                        )}
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
                      <SectionStatusPill
                        dirty={Boolean(classificationsDirty)}
                        errorCount={classificationIssueCount}
                      />
                    }
                  />
                  {classificationIssueCount > 0 ? (
                    <RowMessages
                      messages={[
                        ...laborClassificationValidation.messages,
                        ...equipmentClassificationValidation.messages.filter(
                          (message) => !laborClassificationValidation.messages.includes(message),
                        ),
                      ]}
                    />
                  ) : null}
                  <p className="muted">
                    Marking a classification inactive retires its configured rates on save, but mappings still need to
                    be cleared or reassigned manually before that classification can be retired.
                  </p>
                  <div className="workspace-callout">
                    <strong>{templateMetadata?.display_label ?? "Current template"}</strong>
                    <p>
                      Labor active slots: {draftState ? laborActiveCount : (detailToRender?.labor_active_slot_count ?? 0)} / {laborActiveCapacity || 0}. Inactive stored labor classifications: {draftState ? laborInactiveCount : (detailToRender?.labor_inactive_slot_count ?? 0)}.
                    </p>
                    <p>
                      Equipment active slots: {draftState ? equipmentActiveCount : (detailToRender?.equipment_active_slot_count ?? 0)} / {equipmentActiveCapacity || 0}. Inactive stored equipment classifications: {draftState ? equipmentInactiveCount : (detailToRender?.equipment_inactive_slot_count ?? 0)}.
                    </p>
                    <p>
                      Export compacts active classifications into contiguous template rows, so inactive middle slots do not leave blank workbook rows.
                    </p>
                  </div>
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
                                  aria-invalid={laborClassificationValidation.rowErrors[index] ? "true" : "false"}
                                  className={laborClassificationValidation.rowErrors[index] ? "field-invalid" : undefined}
                                  value={row.label}
                                  onChange={(event) =>
                                    setLaborSlots(
                                      laborSlots.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, label: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                                <RowMessages messages={laborClassificationValidation.rowErrors[index]} />
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
                      <div className="actions">
                        <button
                          type="button"
                          className="tertiary-button"
                          onClick={() =>
                            setLaborSlots([
                              ...laborSlots,
                              {
                                slot_id: buildNextSlotId(laborSlots, "labor"),
                                label: "",
                                active: false,
                              },
                            ])
                          }
                          disabled={busy}
                        >
                          Add labor classification row
                        </button>
                      </div>
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
                                  aria-invalid={equipmentClassificationValidation.rowErrors[index] ? "true" : "false"}
                                  className={equipmentClassificationValidation.rowErrors[index] ? "field-invalid" : undefined}
                                  value={row.label}
                                  onChange={(event) =>
                                    setEquipmentSlots(
                                      equipmentSlots.map((item, itemIndex) =>
                                        itemIndex === index ? { ...item, label: event.target.value } : item,
                                      ),
                                    )
                                  }
                                />
                                <RowMessages messages={equipmentClassificationValidation.rowErrors[index]} />
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
                      <div className="actions">
                        <button
                          type="button"
                          className="tertiary-button"
                          onClick={() =>
                            setEquipmentSlots([
                              ...equipmentSlots,
                              {
                                slot_id: buildNextSlotId(equipmentSlots, "equipment"),
                                label: "",
                                active: false,
                              },
                            ])
                          }
                          disabled={busy}
                        >
                          Add equipment classification row
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Export Settings"
                    description="These rules affect workbook shaping only. They do not mutate stored run, review, or mapping data."
                    action={
                      <SectionStatusPill
                        dirty={Boolean(exportSettingsDirty)}
                        errorCount={exportSettingsValidation.messages.length}
                      />
                    }
                  />
                  <p className="muted">
                    Labor minimum-hours applies during export shaping after review is complete. It is snapshot-bound through published profile lineage.
                  </p>
                  {exportSettingsValidation.messages.length > 0 ? (
                    <RowMessages messages={exportSettingsValidation.messages} />
                  ) : null}
                  <div className="settings-two-column">
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Rule</th>
                            <th>Setting</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td className="cell-primary">Labor minimum hours</td>
                            <td>
                              <label className="checkbox-field">
                                <input
                                  type="checkbox"
                                  checked={exportSettings.labor_minimum_hours.enabled}
                                  onChange={(event) =>
                                    setExportSettings({
                                      labor_minimum_hours: {
                                        ...exportSettings.labor_minimum_hours,
                                        enabled: event.target.checked,
                                      },
                                    })
                                  }
                                />
                                <span>
                                  {exportSettings.labor_minimum_hours.enabled ? "Enabled" : "Disabled"}
                                </span>
                              </label>
                            </td>
                          </tr>
                          <tr>
                            <td className="cell-primary">Threshold hours</td>
                            <td>
                              <input
                                aria-label="Labor minimum hours threshold"
                                value={exportSettings.labor_minimum_hours.threshold_hours}
                                onChange={(event) =>
                                  setExportSettings({
                                    labor_minimum_hours: {
                                      ...exportSettings.labor_minimum_hours,
                                      threshold_hours: event.target.value,
                                    },
                                  })
                                }
                              />
                            </td>
                          </tr>
                          <tr>
                            <td className="cell-primary">Minimum export hours</td>
                            <td>
                              <input
                                aria-label="Labor minimum hours value"
                                value={exportSettings.labor_minimum_hours.minimum_hours}
                                onChange={(event) =>
                                  setExportSettings({
                                    labor_minimum_hours: {
                                      ...exportSettings.labor_minimum_hours,
                                      minimum_hours: event.target.value,
                                    },
                                  })
                                }
                              />
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Rates"
                    description="Rates stay backend-validated. Unmapped observed rows do not block editing or saving on their own."
                    action={
                      <SectionStatusPill
                        dirty={Boolean(ratesDirty)}
                        errorCount={ratesValidation.messages.length}
                      />
                    }
                  />
                  <p className="muted">
                    Rates follow active classifications. If you mark a classification inactive, its configured rates are
                    removed from the draft on save.
                  </p>
                  {retiredLaborRateLabels.length > 0 || retiredEquipmentRateLabels.length > 0 ? (
                    <div className="workspace-callout">
                      <strong>Inactive classifications will retire their rates on save.</strong>
                      {retiredLaborRateLabels.length > 0 ? (
                        <p>Labor rates to retire: {retiredLaborRateLabels.join(", ")}.</p>
                      ) : null}
                      {retiredEquipmentRateLabels.length > 0 ? (
                        <p>Equipment rates to retire: {retiredEquipmentRateLabels.join(", ")}.</p>
                      ) : null}
                    </div>
                  ) : null}
                  {ratesValidation.messages.length > 0 ? <RowMessages messages={ratesValidation.messages} /> : null}
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
                          {laborRates.length === 0 ? (
                            <tr>
                              <td colSpan={4}>
                                <p className="empty-state">No labor rate rows are available for the current classifications.</p>
                              </td>
                            </tr>
                          ) : (
                            laborRates.map((row, index) => (
                              <tr key={`labor-rate-${row.classification}`}>
                                <td className="cell-primary">{row.classification}</td>
                                <td>
                                  <input
                                    aria-label={`Labor standard rate ${index + 1}`}
                                    aria-invalid={ratesValidation.rowErrors[index] ? "true" : "false"}
                                    className={ratesValidation.rowErrors[index] ? "field-invalid" : undefined}
                                    value={row.standard_rate}
                                    onChange={(event) =>
                                      setLaborRates(
                                        laborRates.map((item, itemIndex) =>
                                          itemIndex === index ? { ...item, standard_rate: event.target.value } : item,
                                        ),
                                      )
                                    }
                                  />
                                  <RowMessages messages={ratesValidation.rowErrors[index]} />
                                </td>
                                <td>
                                  <input
                                    aria-label={`Labor overtime rate ${index + 1}`}
                                    aria-invalid={ratesValidation.rowErrors[index] ? "true" : "false"}
                                    className={ratesValidation.rowErrors[index] ? "field-invalid" : undefined}
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
                                    aria-invalid={ratesValidation.rowErrors[index] ? "true" : "false"}
                                    className={ratesValidation.rowErrors[index] ? "field-invalid" : undefined}
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
                            ))
                          )}
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
                          {equipmentRates.length === 0 ? (
                            <tr>
                              <td colSpan={2}>
                                <p className="empty-state">No equipment rate rows are available for the current classifications.</p>
                              </td>
                            </tr>
                          ) : (
                            equipmentRates.map((row, index) => {
                              const errorIndex = laborRates.length + index;
                              return (
                                <tr key={`equipment-rate-${row.category}`}>
                                  <td className="cell-primary">{row.category}</td>
                                  <td>
                                    <input
                                      aria-label={`Equipment rate ${index + 1}`}
                                      aria-invalid={ratesValidation.rowErrors[errorIndex] ? "true" : "false"}
                                      className={ratesValidation.rowErrors[errorIndex] ? "field-invalid" : undefined}
                                      value={row.rate}
                                      onChange={(event) =>
                                        setEquipmentRates(
                                          equipmentRates.map((item, itemIndex) =>
                                            itemIndex === index ? { ...item, rate: event.target.value } : item,
                                          ),
                                        )
                                      }
                                    />
                                    <RowMessages messages={ratesValidation.rowErrors[errorIndex]} />
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="workspace-callout">
                <strong>You are viewing the live profile only.</strong>
                <p>
                  Inspect the live version below, then select Edit current profile to change the approved Phase 2A
                  settings slice.
                </p>
              </div>
            )}
              </div>
            </div>
          ) : selectedTrustedProfile ? (
            <div className="panel empty-workspace">
              <p className="empty-state">Loading published profile detail for the selected trusted profile.</p>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
