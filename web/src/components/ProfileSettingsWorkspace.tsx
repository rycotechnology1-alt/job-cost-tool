import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError } from "../api/client";

import type {
  ClassificationSlotRow,
  CreateTrustedProfileRequest,
  DefaultOmitRuleRow,
  DraftEditorStateResponse,
  EquipmentMappingRow,
  EquipmentRateRow,
  LaborMappingRow,
  LaborRateRow,
  PublishedProfileDetailResponse,
  TrustedProfileResponse,
} from "../api/contracts";

type DraftSyncReason =
  | "reset"
  | "profileSwitch"
  | "open"
  | "defaultOmit"
  | "laborMappings"
  | "equipmentMappings"
  | "classifications"
  | "rates";

interface DraftSyncToken {
  reason: DraftSyncReason;
  sequence: number;
}

interface ProfileSettingsWorkspaceProps {
  trustedProfiles: TrustedProfileResponse[];
  archivedTrustedProfiles: TrustedProfileResponse[];
  selectedTrustedProfileName: string;
  selectedTrustedProfile: TrustedProfileResponse | null;
  profileDetail: PublishedProfileDetailResponse | null;
  draftState: DraftEditorStateResponse | null;
  draftSyncToken: DraftSyncToken;
  busy: boolean;
  settingsErrorMessage: string;
  onTrustedProfileNameChange: (value: string) => void;
  onReloadProfileDetail: () => Promise<void> | void;
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
  onCreateTrustedProfile: (request: CreateTrustedProfileRequest) => Promise<void> | void;
  onArchiveTrustedProfile: () => Promise<void> | void;
  onUnarchiveTrustedProfile: (trustedProfileId: string, displayName: string) => Promise<void> | void;
  onCreateDesktopSyncExport: () => Promise<void> | void;
  lastDownloadedProfileSyncFilename: string;
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
  };
}

function emptyEquipmentMappingRow(): EquipmentMappingRow {
  return {
    raw_description: "",
    raw_pattern: "",
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

function compareRows<T>(left: T[], right: T[]): boolean {
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

function buildClassificationValidation(rows: ClassificationSlotRow[], label: string): ValidationResult {
  const result = createValidationResult();
  const seen = new Map<string, number>();

  rows.forEach((row, index) => {
    const normalizedLabel = normalizeKey(row.label);
    if (row.active && !normalizedLabel) {
      appendRowError(result, index, `Active ${label} classification slots need labels.`);
      return;
    }
    if (!row.active || !normalizedLabel) {
      return;
    }
    const existingIndex = seen.get(normalizedLabel);
    if (existingIndex !== undefined) {
      appendRowError(result, existingIndex, `Active ${label} classification labels must be unique.`);
      appendRowError(result, index, `Active ${label} classification labels must be unique.`);
      return;
    }
    seen.set(normalizedLabel, index);
  });

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

function buildTargetOptions(currentValue: string, validTargets: string[]) {
  const trimmedCurrentValue = currentValue.trim();
  if (!trimmedCurrentValue || validTargets.includes(trimmedCurrentValue)) {
    return validTargets;
  }
  return [trimmedCurrentValue, ...validTargets];
}

function buildCreateProfileValidation(
  profileName: string,
  displayName: string,
  trustedProfiles: TrustedProfileResponse[],
): ValidationResult {
  const result = createValidationResult();
  const trimmedProfileName = profileName.trim();
  const trimmedDisplayName = displayName.trim();

  if (!trimmedProfileName) {
    appendRowError(result, 0, "A stable profile key is required.");
  } else if (!/^[A-Za-z0-9_-]+$/.test(trimmedProfileName)) {
    appendRowError(result, 0, "Profile keys may only use letters, numbers, underscores, and hyphens.");
  }
  if (
    trimmedProfileName &&
    trustedProfiles.some((profile) => profile.profile_name.trim().toUpperCase() === trimmedProfileName.toUpperCase())
  ) {
    appendRowError(result, 0, "That profile key is already in use.");
  }

  if (!trimmedDisplayName) {
    appendRowError(result, 1, "A display name is required.");
  }
  if (
    trimmedDisplayName &&
    trustedProfiles.some((profile) => profile.display_name.trim().toUpperCase() === trimmedDisplayName.toUpperCase())
  ) {
    appendRowError(result, 1, "That display name is already in use by another active trusted profile.");
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

function SectionActionGroup({
  dirty,
  errorCount,
  saveLabel,
  saveDisabled,
  onSave,
}: {
  dirty: boolean;
  errorCount: number;
  saveLabel: string;
  saveDisabled: boolean;
  onSave: () => void;
}) {
  return (
    <div className="settings-section-actions">
      <StatusPill tone={errorCount > 0 ? "error" : dirty ? "warning" : "success"}>
        {errorCount > 0 ? `${errorCount} issue${errorCount === 1 ? "" : "s"}` : dirty ? "Unsaved" : "Saved"}
      </StatusPill>
      <button type="button" onClick={onSave} disabled={saveDisabled}>
        {saveLabel}
      </button>
    </div>
  );
}

export function ProfileSettingsWorkspace({
  trustedProfiles,
  archivedTrustedProfiles,
  selectedTrustedProfileName,
  selectedTrustedProfile,
  profileDetail,
  draftState,
  draftSyncToken,
  busy,
  settingsErrorMessage,
  onTrustedProfileNameChange,
  onReloadProfileDetail,
  onOpenDraft,
  onSaveDefaultOmit,
  onSaveLaborMappings,
  onSaveEquipmentMappings,
  onSaveClassifications,
  onSaveRates,
  onPublishDraft,
  onCreateTrustedProfile,
  onArchiveTrustedProfile,
  onUnarchiveTrustedProfile,
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
  const [newProfileName, setNewProfileName] = useState("");
  const [newProfileDisplayName, setNewProfileDisplayName] = useState("");
  const [newProfileDescription, setNewProfileDescription] = useState("");
  const [createServerFieldErrors, setCreateServerFieldErrors] = useState<Record<string, string[]>>({});
  const [createServerMessage, setCreateServerMessage] = useState("");
  const [retainedDraftStates, setRetainedDraftStates] = useState<Record<string, RetainedDraftWorkspaceState>>({});
  const [restoredDraftNotice, setRestoredDraftNotice] = useState("");
  const lastDraftIdRef = useRef<string | null>(null);

  function clearLocalEditorState() {
    setDefaultOmitRules([]);
    setLaborMappings([]);
    setEquipmentMappings([]);
    setLaborSlots([]);
    setEquipmentSlots([]);
    setLaborRates([]);
    setEquipmentRates([]);
  }

  function syncAllFromDraft(nextDraftState: DraftEditorStateResponse) {
    setDefaultOmitRules(cloneRows(nextDraftState.default_omit_rules));
    setLaborMappings(cloneRows(nextDraftState.labor_mappings));
    setEquipmentMappings(cloneRows(nextDraftState.equipment_mappings));
    setLaborSlots(cloneRows(nextDraftState.labor_slots));
    setEquipmentSlots(cloneRows(nextDraftState.equipment_slots));
    setLaborRates(cloneRows(nextDraftState.labor_rates));
    setEquipmentRates(cloneRows(nextDraftState.equipment_rates));
  }

  function syncAllFromRetainedDraft(nextDraftState: RetainedDraftWorkspaceState) {
    setDefaultOmitRules(cloneRows(nextDraftState.default_omit_rules));
    setLaborMappings(cloneRows(nextDraftState.labor_mappings));
    setEquipmentMappings(cloneRows(nextDraftState.equipment_mappings));
    setLaborSlots(cloneRows(nextDraftState.labor_slots));
    setEquipmentSlots(cloneRows(nextDraftState.equipment_slots));
    setLaborRates(cloneRows(nextDraftState.labor_rates));
    setEquipmentRates(cloneRows(nextDraftState.equipment_rates));
  }

  const selectedTrustedProfileId = selectedTrustedProfile?.trusted_profile_id ?? "";

  useEffect(() => {
    if (!selectedTrustedProfileId || !draftState || draftState.trusted_profile_id !== selectedTrustedProfileId) {
      clearLocalEditorState();
      lastDraftIdRef.current = null;
      if (draftSyncToken.reason === "reset" || draftSyncToken.reason === "profileSwitch") {
        setRestoredDraftNotice("");
      }
      return;
    }

    const isNewDraft = lastDraftIdRef.current !== draftState.trusted_profile_draft_id;
    lastDraftIdRef.current = draftState.trusted_profile_draft_id;
    const retainedDraftState = retainedDraftStates[selectedTrustedProfileId];

    if (
      isNewDraft &&
      retainedDraftState &&
      retainedDraftState.trusted_profile_draft_id === draftState.trusted_profile_draft_id &&
      retainedDraftState.draft_content_hash === draftState.draft_content_hash &&
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
      syncAllFromDraft(draftState);
      return;
    }

    switch (draftSyncToken.reason) {
      case "open":
      case "profileSwitch":
        break;
      case "defaultOmit":
        setDefaultOmitRules(cloneRows(draftState.default_omit_rules));
        break;
      case "laborMappings":
        setLaborMappings(cloneRows(draftState.labor_mappings));
        break;
      case "equipmentMappings":
        setEquipmentMappings(cloneRows(draftState.equipment_mappings));
        break;
      case "classifications":
        setLaborSlots(cloneRows(draftState.labor_slots));
        setEquipmentSlots(cloneRows(draftState.equipment_slots));
        setLaborMappings(cloneRows(draftState.labor_mappings));
        setEquipmentMappings(cloneRows(draftState.equipment_mappings));
        setLaborRates(cloneRows(draftState.labor_rates));
        setEquipmentRates(cloneRows(draftState.equipment_rates));
        break;
      case "rates":
        setLaborRates(cloneRows(draftState.labor_rates));
        setEquipmentRates(cloneRows(draftState.equipment_rates));
        break;
      default:
        syncAllFromDraft(draftState);
        break;
    }
  }, [draftState, draftSyncToken, selectedTrustedProfileId]);

  useEffect(() => {
    setNewProfileName("");
    setNewProfileDisplayName("");
    setNewProfileDescription("");
    setCreateServerFieldErrors({});
    setCreateServerMessage("");
  }, [selectedTrustedProfileName]);

  useEffect(() => {
    setCreateServerFieldErrors({});
    setCreateServerMessage("");
  }, [newProfileName, newProfileDisplayName, newProfileDescription]);

  useEffect(() => {
    if (draftSyncToken.reason !== "reset" || !selectedTrustedProfileId || draftState) {
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
  }, [draftState, draftSyncToken.reason, selectedTrustedProfileId]);

  const detailToRender = draftState ?? profileDetail;
  const deferredDomains = detailToRender?.deferred_domains ?? null;
  const openDraftId = draftState?.trusted_profile_draft_id ?? profileDetail?.open_draft_id ?? null;
  const laborTargets = laborSlots.filter((row) => row.active && row.label.trim()).map((row) => row.label.trim());
  const equipmentTargets = equipmentSlots.filter((row) => row.active && row.label.trim()).map((row) => row.label.trim());
  const observedDraftNote = hasObservedUnmappedRows(laborMappings, equipmentMappings);

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
    () => buildClassificationValidation(laborSlots, "labor"),
    [laborSlots],
  );
  const equipmentClassificationValidation = useMemo(
    () => buildClassificationValidation(equipmentSlots, "equipment"),
    [equipmentSlots],
  );
  const classificationIssueCount =
    laborClassificationValidation.messages.length + equipmentClassificationValidation.messages.length;
  const ratesValidation = useMemo(() => buildRatesValidation(laborRates, equipmentRates), [equipmentRates, laborRates]);

  const defaultOmitDirty = draftState ? !compareRows(defaultOmitRules, draftState.default_omit_rules) : false;
  const laborMappingsDirty = draftState ? !compareRows(laborMappings, draftState.labor_mappings) : false;
  const equipmentMappingsDirty = draftState ? !compareRows(equipmentMappings, draftState.equipment_mappings) : false;
  const classificationsDirty =
    draftState &&
    (!compareRows(laborSlots, draftState.labor_slots) || !compareRows(equipmentSlots, draftState.equipment_slots));
  const ratesDirty =
    draftState &&
    (!compareRows(laborRates, draftState.labor_rates) || !compareRows(equipmentRates, draftState.equipment_rates));

  const dirtySections = [
    defaultOmitDirty ? "default omit rules" : "",
    laborMappingsDirty ? "labor mappings" : "",
    equipmentMappingsDirty ? "equipment mappings" : "",
    classificationsDirty ? "classifications" : "",
    ratesDirty ? "rates" : "",
  ].filter(Boolean);

  const hasLocalValidationIssues =
    (defaultOmitDirty && defaultOmitValidation.messages.length > 0) ||
    (laborMappingsDirty && laborMappingValidation.messages.length > 0) ||
    (equipmentMappingsDirty && equipmentMappingValidation.messages.length > 0) ||
    (classificationsDirty && classificationIssueCount > 0) ||
    (ratesDirty && ratesValidation.messages.length > 0);

  const publishDisabled =
    busy ||
    !draftState ||
    dirtySections.length > 0 ||
    hasLocalValidationIssues ||
    draftState.validation_errors.length > 0;

  const publishReadinessLabel = !draftState
    ? "No draft open"
    : draftState.validation_errors.length > 0 || hasLocalValidationIssues
      ? "Fix validation issues"
      : dirtySections.length > 0
        ? "Save unsaved sections"
        : "Ready to publish";

  const publishReadinessTone =
    !draftState || draftState.validation_errors.length > 0 || hasLocalValidationIssues
      ? "error"
      : dirtySections.length > 0
        ? "warning"
        : "success";
  const createProfileValidation = useMemo(
    () => buildCreateProfileValidation(newProfileName, newProfileDisplayName, trustedProfiles),
    [newProfileDisplayName, newProfileName, trustedProfiles],
  );
  const createProfileNameMessages = mergeMessages(
    createProfileValidation.rowErrors[0],
    createServerFieldErrors.profile_name,
  );
  const createProfileDisplayMessages = mergeMessages(
    createProfileValidation.rowErrors[1],
    createServerFieldErrors.display_name,
  );
  const currentPublishedVersionNumber =
    profileDetail?.current_published_version.version_number ??
    draftState?.current_published_version.version_number ??
    selectedTrustedProfile?.current_published_version_number ??
    null;
  const selectedProfileSourceLabel = selectedTrustedProfile ? profileSourceLabel(selectedTrustedProfile.source_kind) : "";
  const canArchiveSelectedProfile =
    selectedTrustedProfile?.source_kind === "published_clone" &&
    !openDraftId &&
    !draftState;
  const createProfileDisabled =
    busy ||
    !selectedTrustedProfile ||
    createProfileValidation.messages.length > 0;
  const selectedRetainedDraftState = selectedTrustedProfileId
    ? retainedDraftStates[selectedTrustedProfileId] ?? null
    : null;
  const workspaceViewLabel = draftState
    ? `Viewing draft ${draftState.trusted_profile_draft_id}`
    : "Viewing published profile";
  const workspaceViewTone = draftState ? "warning" : "neutral";

  useEffect(() => {
    if (!selectedTrustedProfileId || !draftState || draftState.trusted_profile_id !== selectedTrustedProfileId) {
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
        trusted_profile_id: draftState.trusted_profile_id,
        trusted_profile_draft_id: draftState.trusted_profile_draft_id,
        draft_content_hash: draftState.draft_content_hash,
        published_version_number: draftState.current_published_version.version_number,
        default_omit_rules: cloneRows(defaultOmitRules),
        labor_mappings: cloneRows(laborMappings),
        equipment_mappings: cloneRows(equipmentMappings),
        labor_slots: cloneRows(laborSlots),
        equipment_slots: cloneRows(equipmentSlots),
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
    draftState,
    equipmentMappings,
    equipmentRates,
    equipmentSlots,
    laborMappings,
    laborRates,
    laborSlots,
    selectedTrustedProfileId,
  ]);

  function handleResetUnsavedChanges() {
    if (!draftState) {
      return;
    }
    setRestoredDraftNotice("");
    syncAllFromDraft(draftState);
  }

  async function handleCreateProfile() {
    setCreateServerFieldErrors({});
    setCreateServerMessage("");
    try {
      await onCreateTrustedProfile({
        profile_name: newProfileName.trim(),
        display_name: newProfileDisplayName.trim(),
        description: newProfileDescription.trim(),
      });
      setNewProfileName("");
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
    if (
      dirtySections.length > 0 &&
      !window.confirm(
        `Switching trusted profiles will keep the current unsaved browser edits attached only to ${selectedTrustedProfile?.display_name ?? "this profile"} in this tab. Reopen that profile's current draft to continue them later. Continue?`,
      )
    ) {
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
            <button type="button" onClick={onOpenDraft} disabled={busy || !selectedTrustedProfile}>
              {openDraftId ? "Open current draft" : "Create draft from published version"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={onPublishDraft}
              disabled={publishDisabled}
            >
              Publish draft
            </button>
          </div>
          <p className="muted">
            Published versions are processable. Drafts remain non-processable until publish creates a new immutable
            version.
          </p>
          {selectedTrustedProfile ? (
            <div className="workspace-callout">
              <strong>Selected profile state</strong>
              <div className="settings-inline-status">
                <StatusPill tone="neutral">{selectedTrustedProfile.display_name}</StatusPill>
                <StatusPill tone={profileSourceTone(selectedTrustedProfile.source_kind)}>
                  {selectedProfileSourceLabel}
                </StatusPill>
                <StatusPill tone={selectedTrustedProfile.has_open_draft ? "warning" : "success"}>
                  {selectedTrustedProfile.has_open_draft ? "Open draft" : "No open draft"}
                </StatusPill>
                <StatusPill tone="neutral">Published v{selectedTrustedProfile.current_published_version_number}</StatusPill>
                <StatusPill tone={workspaceViewTone}>{workspaceViewLabel}</StatusPill>
                {selectedRetainedDraftState ? <StatusPill tone="warning">Local unsaved edits retained</StatusPill> : null}
                {selectedTrustedProfile.is_active_profile ? <StatusPill tone="neutral">Desktop active</StatusPill> : null}
              </div>
              <p className="muted">
                The selected profile controls both the seed for new profile creation and the draft you open below.
                Local unsaved browser edits stay scoped to one profile and one draft in this tab.
              </p>
            </div>
          ) : null}
          {trustedProfiles.length > 0 ? (
            <div className="workspace-callout">
              <strong>Profiles in this organization</strong>
              <div className="profile-list">
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
                    <div>
                      <strong>{profile.display_name}</strong>
                      <p className="muted">{profile.profile_name}</p>
                    </div>
                    <div className="settings-inline-status">
                      <StatusPill tone={profileSourceTone(profile.source_kind)}>{profileSourceLabel(profile.source_kind)}</StatusPill>
                      <StatusPill tone="neutral">v{profile.current_published_version_number}</StatusPill>
                      {profile.has_open_draft ? <StatusPill tone="warning">Open draft</StatusPill> : null}
                      {retainedDraftStates[profile.trusted_profile_id] ? <StatusPill tone="warning">Local unsaved edits</StatusPill> : null}
                      {profile.profile_name === selectedTrustedProfileName ? <StatusPill tone="success">Selected</StatusPill> : null}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="workspace-callout">
            <strong>Create another trusted profile</strong>
            <p>
              New profiles start from the currently selected profile&apos;s published version only. Open drafts and
              unsaved browser edits are not copied.
            </p>
            {createServerMessage ? (
              <div className="banner warning" role="status">
                <strong>Create profile could not be completed.</strong>
                <p>{createServerMessage}</p>
              </div>
            ) : null}
            {selectedTrustedProfile ? (
              <p className="muted">
                Seed source: {selectedTrustedProfile.display_name} ({selectedProfileSourceLabel}), published version v
                {currentPublishedVersionNumber ?? selectedTrustedProfile.current_published_version_number}.
              </p>
            ) : null}
            <div className="settings-create-grid">
              <label className="field">
                <span>New profile key</span>
                <input
                  aria-label="New profile key"
                  aria-invalid={createProfileNameMessages.length > 0 ? "true" : "false"}
                  className={createProfileNameMessages.length > 0 ? "field-invalid" : undefined}
                  value={newProfileName}
                  onChange={(event) => setNewProfileName(event.target.value)}
                  placeholder="alternate-profile"
                  disabled={busy || !selectedTrustedProfile}
                />
                <RowMessages messages={createProfileNameMessages} />
              </label>
              <label className="field">
                <span>Display name</span>
                <input
                  aria-label="New profile display name"
                  aria-invalid={createProfileDisplayMessages.length > 0 ? "true" : "false"}
                  className={createProfileDisplayMessages.length > 0 ? "field-invalid" : undefined}
                  value={newProfileDisplayName}
                  onChange={(event) => setNewProfileDisplayName(event.target.value)}
                  placeholder="Alternate Profile"
                  disabled={busy || !selectedTrustedProfile}
                />
                <RowMessages messages={createProfileDisplayMessages} />
              </label>
            </div>
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
                !createProfileNameMessages.includes(message) && !createProfileDisplayMessages.includes(message),
            ) ? (
              <RowMessages
                messages={createProfileValidation.messages.filter(
                  (message) =>
                    !createProfileNameMessages.includes(message) && !createProfileDisplayMessages.includes(message),
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
                ? "Default and filesystem-backed profiles stay managed through the existing desktop/filesystem path."
                : openDraftId
                  ? "Publish the open draft before archiving this profile."
                  : "Archiving hides the profile from active selectors but preserves its versions, runs, and sync-export audit history."}
            </p>
          </div>
          <div className="workspace-callout">
            <strong>Archived profiles</strong>
            <p className="muted">
              Archived profiles remain in lineage history, stay out of active review/profile selectors, and cannot open
              drafts until they are restored.
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
      </div>

      {!selectedTrustedProfile ? (
        <div className="panel empty-workspace">
          <p className="empty-state">Choose a trusted profile to inspect the published configuration and open a draft.</p>
        </div>
      ) : null}

      {settingsErrorMessage ? (
        <div className="banner error" role="alert">
          <strong>Settings workflow needs attention</strong>
          <p>{settingsErrorMessage}</p>
          {draftState ? (
            <p className="muted">Unsaved browser edits remain on screen while you retry or continue adjusting the draft.</p>
          ) : null}
          <div className="actions">
            {!profileDetail ? (
              <button type="button" className="secondary-button" onClick={() => void onReloadProfileDetail()} disabled={busy}>
                Retry loading published profile
              </button>
            ) : !draftState ? (
              <button type="button" className="secondary-button" onClick={() => void onOpenDraft()} disabled={busy}>
                {openDraftId ? "Retry opening current draft" : "Retry creating draft"}
              </button>
            ) : (
              <button type="button" className="secondary-button" onClick={() => void onReloadProfileDetail()} disabled={busy}>
                Reload published summary
              </button>
            )}
          </div>
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
                <dt>Profile source</dt>
                <dd>{selectedTrustedProfile ? profileSourceLabel(selectedTrustedProfile.source_kind) : "-"}</dd>
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

            <div className="settings-status-strip">
              <div className="status-block settings-status-card">
                <strong>Published state</strong>
                <p>Published version v{profileDetail.current_published_version.version_number} remains the live web-processing source.</p>
              </div>
              <div className="status-block settings-status-card">
                <strong>Workspace view</strong>
                <p>{draftState ? `Editing draft ${draftState.trusted_profile_draft_id}.` : "Viewing published profile data only."}</p>
              </div>
              <div className="status-block settings-status-card">
                <strong>Unsaved browser changes</strong>
                <p>
                  {draftState
                    ? dirtySections.length > 0
                      ? `${dirtySections.length} section(s) still need saving.`
                      : "All browser edits match the saved draft."
                    : selectedRetainedDraftState
                      ? `Retained for draft ${selectedRetainedDraftState.trusted_profile_draft_id}. Reopen the current draft to continue them.`
                      : "No local draft edits are currently retained in this tab."}
                </p>
              </div>
              <div className="status-block settings-status-card">
                <strong>Publish readiness</strong>
                <p>{publishReadinessLabel}</p>
              </div>
            </div>

            {!draftState && selectedRetainedDraftState ? (
              <div className="workspace-callout">
                <strong>Unsaved browser edits are retained for this profile.</strong>
                <p>
                  This tab kept {selectedRetainedDraftState.dirty_sections.join(", ")} for draft{" "}
                  {selectedRetainedDraftState.trusted_profile_draft_id}. Use <em>Open current draft</em> to keep working
                  with those profile-scoped browser edits.
                </p>
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
                  <div className="settings-inline-status">
                    <StatusPill tone="neutral">Published v{draftState.current_published_version.version_number}</StatusPill>
                    <StatusPill tone={dirtySections.length > 0 ? "warning" : "success"}>
                      {dirtySections.length > 0 ? `${dirtySections.length} unsaved section(s)` : "No unsaved browser changes"}
                    </StatusPill>
                    <StatusPill tone={publishReadinessTone}>{publishReadinessLabel}</StatusPill>
                  </div>
                  {restoredDraftNotice ? (
                    <p className="muted">{restoredDraftNotice}</p>
                  ) : null}
                  {dirtySections.length > 0 ? (
                    <div className="actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={handleResetUnsavedChanges}
                        disabled={busy}
                      >
                        Discard unsaved browser changes
                      </button>
                    </div>
                  ) : null}
                </div>

                {dirtySections.length > 0 ? (
                  <div className="workspace-callout">
                    <strong>Publish is waiting on unsaved sections.</strong>
                    <p>Save {dirtySections.join(", ")} before publishing this draft.</p>
                  </div>
                ) : null}

                {hasLocalValidationIssues ? (
                  <div className="banner warning" role="status">
                    <strong>Fix inline issues before saving or publishing.</strong>
                    <p>The affected fields are marked directly in the editable Phase 2A sections below.</p>
                  </div>
                ) : null}

                <div className="settings-section">
                  <SectionHeader
                    title="Default Omit Rules"
                    description="Edit the phase codes that start omitted by default for future runs."
                    action={
                      <SectionActionGroup
                        dirty={defaultOmitDirty}
                        errorCount={defaultOmitValidation.messages.length}
                        saveLabel="Save default omit rules"
                        saveDisabled={busy || !defaultOmitDirty || defaultOmitValidation.messages.length > 0}
                        onSave={() => void onSaveDefaultOmit(defaultOmitRules)}
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
                      <SectionActionGroup
                        dirty={laborMappingsDirty}
                        errorCount={laborMappingValidation.messages.length}
                        saveLabel="Save labor mappings"
                        saveDisabled={busy || !laborMappingsDirty || laborMappingValidation.messages.length > 0}
                        onSave={() => void onSaveLaborMappings(laborMappings)}
                      />
                    }
                  />
                  <p className="muted">
                    Observed rows were auto-added from unmapped labor values seen during processing. Leave them blank or
                    map them when ready.
                  </p>
                  {laborMappingValidation.messages.length > 0 ? <RowMessages messages={laborMappingValidation.messages} /> : null}
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
                        {laborMappings.length === 0 ? (
                          <tr>
                            <td colSpan={5}>
                              <p className="empty-state">No labor mappings are saved yet. Add a row to start building this domain.</p>
                            </td>
                          </tr>
                        ) : (
                          laborMappings.map((row, index) => (
                            <tr key={`labor-mapping-${index}`}>
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
                                          ? { ...item, target_classification: event.target.value }
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
                      <SectionActionGroup
                        dirty={equipmentMappingsDirty}
                        errorCount={equipmentMappingValidation.messages.length}
                        saveLabel="Save equipment mappings"
                        saveDisabled={busy || !equipmentMappingsDirty || equipmentMappingValidation.messages.length > 0}
                        onSave={() => void onSaveEquipmentMappings(equipmentMappings)}
                      />
                    }
                  />
                  <p className="muted">
                    Observed equipment rows were auto-added from unmapped keys seen during processing and can remain
                    unresolved.
                  </p>
                  {equipmentMappingValidation.messages.length > 0 ? <RowMessages messages={equipmentMappingValidation.messages} /> : null}
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
                        {equipmentMappings.length === 0 ? (
                          <tr>
                            <td colSpan={4}>
                              <p className="empty-state">No equipment mappings are saved yet. Add a row to start building this domain.</p>
                            </td>
                          </tr>
                        ) : (
                          equipmentMappings.map((row, index) => (
                            <tr key={`equipment-mapping-${index}`}>
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
                                          ? { ...item, target_category: event.target.value }
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
                      <SectionActionGroup
                        dirty={Boolean(classificationsDirty)}
                        errorCount={classificationIssueCount}
                        saveLabel="Save classifications"
                        saveDisabled={busy || !classificationsDirty || classificationIssueCount > 0}
                        onSave={() => void onSaveClassifications(laborSlots, equipmentSlots)}
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
                    </div>
                  </div>
                </div>

                <div className="settings-section">
                  <SectionHeader
                    title="Rates"
                    description="Rates stay backend-validated. Unmapped observed rows do not block editing or publish on their own."
                    action={
                      <SectionActionGroup
                        dirty={Boolean(ratesDirty)}
                        errorCount={ratesValidation.messages.length}
                        saveLabel="Save rates"
                        saveDisabled={busy || !ratesDirty || ratesValidation.messages.length > 0}
                        onSave={() => void onSaveRates(laborRates, equipmentRates)}
                      />
                    }
                  />
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
