import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

const trustedProfilesPayload = [
  {
    trusted_profile_id: "trusted-profile:org-default:default",
    profile_name: "default",
    display_name: "Default Profile",
    description: "Default trusted profile",
    version_label: "1.0",
    template_filename: "recap_template.xlsx",
    source_kind: "seeded",
    current_published_version_number: 1,
    has_open_draft: false,
    is_active_profile: true,
    archived_at: null,
  },
];

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function buildPublishedDetail(openDraftId: string | null = null, versionNumber = 1, contentHash = "profile-hash-v1") {
  return {
    trusted_profile_id: "trusted-profile:org-default:default",
    profile_name: "default",
    display_name: "Default Profile",
    description: "Default trusted profile",
    version_label: "1.0",
    current_published_version: {
      trusted_profile_version_id: `trusted-profile-version-${versionNumber}`,
      version_number: versionNumber,
      content_hash: contentHash,
      template_artifact_ref: "template-artifact:default",
      template_file_hash: "template-file-hash",
      template_filename: "recap_template.xlsx",
    },
    template_metadata: {
      template_filename: "recap_template.xlsx",
      labor_slots_total: 4,
      equipment_slots_total: 4,
      workbook_title: "Recap Template",
    },
    labor_active_slot_count: 2,
    labor_inactive_slot_count: 0,
    equipment_active_slot_count: 2,
    equipment_inactive_slot_count: 0,
    open_draft_id: openDraftId,
    deferred_domains: {
      vendor_normalization: { aliases: ["National Grid"] },
      phase_mapping: { "29 .999": "labor_non_job_related" },
      input_model: { transaction_codes: ["JC", "AP"] },
      recap_template_map: { labor_section_start: "B12" },
    },
  };
}

function buildDraftState() {
  return {
    trusted_profile_draft_id: "draft-1",
    trusted_profile_id: "trusted-profile:org-default:default",
    profile_name: "default",
    display_name: "Default Profile",
    description: "Default trusted profile",
    version_label: "1.0",
    current_published_version: buildPublishedDetail().current_published_version,
    base_trusted_profile_version_id: "trusted-profile-version-1",
    draft_revision: 1,
    draft_content_hash: "draft-content-hash",
    template_metadata: clone(buildPublishedDetail().template_metadata),
    labor_active_slot_count: 2,
    labor_inactive_slot_count: 0,
    equipment_active_slot_count: 2,
    equipment_inactive_slot_count: 0,
    default_omit_rules: [
      {
        phase_code: "29 .999",
        phase_name: "Labor-Non-Job Related Time",
      },
    ],
    default_omit_phase_options: [
      {
        phase_code: "29 .999",
        phase_name: "Labor-Non-Job Related Time",
      },
      {
        phase_code: "50 .1",
        phase_name: "Permits & Fees",
      },
    ],
    labor_mappings: [
      {
        raw_value: "NEW OBSERVED LABOR",
        target_classification: "",
        notes: "",
        is_observed: true,
        is_required_for_recent_processing: true,
      },
      {
        raw_value: "CARPENTER",
        target_classification: "Journeyman",
        notes: "Baseline row",
        is_observed: false,
      },
      {
        raw_value: "SHIFT DIFFERENTIAL",
        target_classification: "",
        notes: "",
        is_observed: true,
      },
    ],
    equipment_mappings: [
      {
        raw_description: "NEW OBSERVED EQUIPMENT",
        target_category: "",
        is_observed: true,
        is_required_for_recent_processing: true,
        prediction_target: "Excavator",
        prediction_confidence_label: "Likely match",
      },
      {
        raw_description: "MINI EX",
        target_category: "Excavator",
        is_observed: false,
      },
      {
        raw_description: "SMALL EX",
        target_category: "",
        is_observed: true,
        prediction_target: "Excavator",
        prediction_confidence_label: "Likely match",
      },
    ],
    labor_slots: [
      {
        slot_id: "labor_1",
        label: "Journeyman",
        active: true,
      },
      {
        slot_id: "labor_2",
        label: "Foreman",
        active: true,
      },
    ],
    equipment_slots: [
      {
        slot_id: "equipment_1",
        label: "Excavator",
        active: true,
      },
      {
        slot_id: "equipment_2",
        label: "Bucket Truck",
        active: true,
      },
    ],
    labor_rates: [
      {
        classification: "Journeyman",
        standard_rate: "45",
        overtime_rate: "67.5",
        double_time_rate: "90",
      },
      {
        classification: "Foreman",
        standard_rate: "55",
        overtime_rate: "82.5",
        double_time_rate: "110",
      },
    ],
    equipment_rates: [
      {
        category: "Excavator",
        rate: "125",
      },
      {
        category: "Bucket Truck",
        rate: "210",
      },
    ],
    export_settings: {
      labor_minimum_hours: {
        enabled: false,
        threshold_hours: "",
        minimum_hours: "",
      },
    },
    deferred_domains: buildPublishedDetail().deferred_domains,
    validation_errors: [],
  };
}

function normalizeKey(value: string): string {
  return value.trim().toUpperCase();
}

function hasConfiguredLaborRate(row: { standard_rate: string; overtime_rate: string; double_time_rate: string }): boolean {
  return [row.standard_rate, row.overtime_rate, row.double_time_rate].some((value) => value.trim().length > 0);
}

function hasConfiguredEquipmentRate(row: { rate: string }): boolean {
  return row.rate.trim().length > 0;
}

function validateClassificationReferences(
  draftState: ReturnType<typeof buildDraftState>,
  laborSlots: Array<{ label: string; active: boolean }>,
  equipmentSlots: Array<{ label: string; active: boolean }>,
): string | null {
  function buildRenameMap(
    previousSlots: Array<{ label: string; active: boolean }>,
    nextSlots: Array<{ label: string; active: boolean }>,
  ): Map<string, string> {
    const renameMap = new Map<string, string>();
    for (let index = 0; index < Math.min(previousSlots.length, nextSlots.length); index += 1) {
      const previousLabel = previousSlots[index]?.label.trim() ?? "";
      const nextLabel = nextSlots[index]?.label.trim() ?? "";
      if (previousLabel && nextLabel && normalizeKey(previousLabel) !== normalizeKey(nextLabel)) {
        renameMap.set(previousLabel, nextLabel);
      }
    }
    return renameMap;
  }

  function renameValue(value: string, renameMap: Map<string, string>): string {
    return renameMap.get(value.trim()) ?? value.trim();
  }

  const laborRenameMap = buildRenameMap(draftState.labor_slots, laborSlots);
  const equipmentRenameMap = buildRenameMap(draftState.equipment_slots, equipmentSlots);
  const activeLaborLabels = new Set(
    laborSlots.map((slot) => (slot.active ? normalizeKey(slot.label) : "")).filter(Boolean),
  );
  const activeEquipmentLabels = new Set(
    equipmentSlots.map((slot) => (slot.active ? normalizeKey(slot.label) : "")).filter(Boolean),
  );

  for (const row of draftState.labor_mappings) {
    const target = renameValue(row.target_classification, laborRenameMap);
    if (target && !activeLaborLabels.has(normalizeKey(target))) {
      return `Labor classification '${target}' is still referenced by labor mapping '${row.raw_value}'. Update mappings first.`;
    }
  }

  for (const row of draftState.labor_rates) {
    const classification = renameValue(row.classification, laborRenameMap);
    if (classification && !activeLaborLabels.has(normalizeKey(classification)) && hasConfiguredLaborRate(row)) {
      return `Labor classification '${classification}' is still referenced by configured labor rates. Update rates first.`;
    }
  }

  for (const row of draftState.equipment_mappings) {
    const target = renameValue(row.target_category, equipmentRenameMap);
    if (target && !activeEquipmentLabels.has(normalizeKey(target))) {
      return `Equipment classification '${target}' is still referenced by equipment mapping '${row.raw_description}'. Update mappings first.`;
    }
  }

  for (const row of draftState.equipment_rates) {
    const category = renameValue(row.category, equipmentRenameMap);
    if (category && !activeEquipmentLabels.has(normalizeKey(category)) && hasConfiguredEquipmentRate(row)) {
      return `Equipment classification '${category}' is still referenced by configured equipment rates. Update rates first.`;
    }
  }

  return null;
}

function applyAtomicDraftSave(
  draftState: ReturnType<typeof buildDraftState>,
  payload: {
    default_omit_rules: ReturnType<typeof buildDraftState>["default_omit_rules"];
    labor_mappings: ReturnType<typeof buildDraftState>["labor_mappings"];
    equipment_mappings: ReturnType<typeof buildDraftState>["equipment_mappings"];
    labor_slots: ReturnType<typeof buildDraftState>["labor_slots"];
    equipment_slots: ReturnType<typeof buildDraftState>["equipment_slots"];
    labor_rates: ReturnType<typeof buildDraftState>["labor_rates"];
    equipment_rates: ReturnType<typeof buildDraftState>["equipment_rates"];
    export_settings: ReturnType<typeof buildDraftState>["export_settings"];
  },
) {
  draftState.default_omit_rules = payload.default_omit_rules;
  draftState.labor_mappings = payload.labor_mappings;
  draftState.equipment_mappings = payload.equipment_mappings;
  draftState.labor_slots = payload.labor_slots;
  draftState.equipment_slots = payload.equipment_slots;
  draftState.labor_rates = payload.labor_rates;
  draftState.equipment_rates = payload.equipment_rates;
  draftState.export_settings = payload.export_settings;
}

function installSettingsFetchMock(options?: {
  openDraftId?: string | null;
  publishFails?: boolean;
  draftGetNotFoundOnce?: boolean;
  enforceClassificationReferenceValidation?: boolean;
}) {
  const baselineDraftState = buildDraftState();
  const state = {
    publishedDetail: buildPublishedDetail(options?.openDraftId ?? null),
    draftState: clone(baselineDraftState),
    baselineDraftState: clone(baselineDraftState),
    publishFails: options?.publishFails ?? false,
    draftGetNotFoundOnce: options?.draftGetNotFoundOnce ?? false,
  };

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    function parseJsonBody<T extends Record<string, unknown>>(): T {
      return JSON.parse(String(init?.body ?? "{}")) as T;
    }

    function staleDraftResponse(): Response {
      return new Response(
        JSON.stringify({
          detail: {
            message: "Refresh the draft and retry with the latest revision before saving.",
            error_code: "profile_authoring_persistence_conflict",
            field_errors: {
              expected_draft_revision: ["Refresh the draft and retry with the latest revision before saving."],
            },
          },
        }),
        {
          status: 409,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    function requireExpectedDraftRevision(payload: Record<string, unknown>): Response | null {
      if (typeof payload.expected_draft_revision !== "number") {
        return new Response(
          JSON.stringify({
            detail: [
              {
                type: "missing",
                loc: ["body", "expected_draft_revision"],
                msg: "Field required",
                input: payload,
              },
            ],
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (payload.expected_draft_revision !== state.draftState.draft_revision) {
        return staleDraftResponse();
      }
      return null;
    }

    function advanceDraftRevision() {
      state.draftState.draft_revision += 1;
      state.draftState.draft_content_hash = `draft-content-hash-v${state.draftState.draft_revision}`;
    }

    if ((url === "/api/trusted-profiles" || url === "/api/trusted-profiles?include_archived=true") && method === "GET") {
      return new Response(JSON.stringify(trustedProfilesPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:default" && method === "GET") {
      return new Response(JSON.stringify(state.publishedDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:default/draft" && method === "POST") {
      state.publishedDetail.open_draft_id = state.draftState.trusted_profile_draft_id;
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1" && method === "GET") {
      if (state.draftGetNotFoundOnce) {
        state.draftGetNotFoundOnce = false;
        return new Response(JSON.stringify({ detail: "Draft not found." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1" && method === "DELETE") {
      state.publishedDetail.open_draft_id = null;
      return new Response(null, { status: 204 });
    }

    if (url === "/api/profile-drafts/draft-1" && method === "PATCH") {
      const payload = parseJsonBody<{
        expected_draft_revision?: number;
        default_omit_rules: ReturnType<typeof buildDraftState>["default_omit_rules"];
        labor_mappings: ReturnType<typeof buildDraftState>["labor_mappings"];
        equipment_mappings: ReturnType<typeof buildDraftState>["equipment_mappings"];
        labor_slots: ReturnType<typeof buildDraftState>["labor_slots"];
        equipment_slots: ReturnType<typeof buildDraftState>["equipment_slots"];
        labor_rates: ReturnType<typeof buildDraftState>["labor_rates"];
        equipment_rates: ReturnType<typeof buildDraftState>["equipment_rates"];
        export_settings: ReturnType<typeof buildDraftState>["export_settings"];
      }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      const nextDraftState = {
        ...clone(state.draftState),
        default_omit_rules: payload.default_omit_rules,
        labor_mappings: payload.labor_mappings,
        equipment_mappings: payload.equipment_mappings,
        labor_rates: payload.labor_rates,
        equipment_rates: payload.equipment_rates,
        export_settings: payload.export_settings,
      };
      if (options?.enforceClassificationReferenceValidation) {
        const validationError = validateClassificationReferences(
          nextDraftState,
          payload.labor_slots,
          payload.equipment_slots,
        );
        if (validationError) {
          return new Response(JSON.stringify({ detail: validationError }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
      applyAtomicDraftSave(state.draftState, payload);
      advanceDraftRevision();
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/default-omit" && method === "PATCH") {
      const payload = parseJsonBody<{
        expected_draft_revision?: number;
        default_omit_rules: ReturnType<typeof buildDraftState>["default_omit_rules"];
      }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      state.draftState.default_omit_rules = payload.default_omit_rules;
      advanceDraftRevision();
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/labor-mappings" && method === "PATCH") {
      const payload = parseJsonBody<{
        expected_draft_revision?: number;
        labor_mappings: ReturnType<typeof buildDraftState>["labor_mappings"];
      }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      state.draftState.labor_mappings = payload.labor_mappings;
      advanceDraftRevision();
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/equipment-mappings" && method === "PATCH") {
      const payload = parseJsonBody<{
        expected_draft_revision?: number;
        equipment_mappings: ReturnType<typeof buildDraftState>["equipment_mappings"];
      }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      state.draftState.equipment_mappings = payload.equipment_mappings;
      advanceDraftRevision();
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/classifications" && method === "PATCH") {
      const payload = parseJsonBody<{
        expected_draft_revision?: number;
        labor_slots: ReturnType<typeof buildDraftState>["labor_slots"];
        equipment_slots: ReturnType<typeof buildDraftState>["equipment_slots"];
      }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      if (options?.enforceClassificationReferenceValidation) {
        const validationError = validateClassificationReferences(
          state.draftState,
          payload.labor_slots,
          payload.equipment_slots,
        );
        if (validationError) {
          return new Response(JSON.stringify({ detail: validationError }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
      state.draftState.labor_slots = payload.labor_slots;
      state.draftState.equipment_slots = payload.equipment_slots;
      advanceDraftRevision();
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/rates" && method === "PATCH") {
      const payload = parseJsonBody<{
        expected_draft_revision?: number;
        labor_rates: ReturnType<typeof buildDraftState>["labor_rates"];
        equipment_rates: ReturnType<typeof buildDraftState>["equipment_rates"];
      }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      state.draftState.labor_rates = payload.labor_rates;
      state.draftState.equipment_rates = payload.equipment_rates;
      advanceDraftRevision();
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/publish" && method === "POST") {
      const payload = parseJsonBody<{ expected_draft_revision?: number }>();
      const revisionError = requireExpectedDraftRevision(payload);
      if (revisionError) {
        return revisionError;
      }
      if (state.publishFails) {
        return new Response(JSON.stringify({ detail: "Draft validation failed before publish." }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      }
      const isEquivalentPublish = JSON.stringify(state.draftState) === JSON.stringify(state.baselineDraftState);
      state.publishedDetail = isEquivalentPublish
        ? buildPublishedDetail(null, 1, "profile-hash-v1")
        : buildPublishedDetail(null, 2, "profile-hash-v2");
      return new Response(JSON.stringify(state.publishedDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    throw new Error(`Unhandled fetch call for ${method} ${url}`);
  });

  return state;
}

function installSecondProfileCreationFetchMock(options?: {
  deferFieldTeamDetailOnce?: boolean;
  failFieldTeamDetailOnce?: boolean;
  includeSecondProfileInitially?: boolean;
}) {
  const defaultProfile = clone(trustedProfilesPayload[0]);
  const secondProfile = {
    trusted_profile_id: "trusted-profile:org-default:field-team",
    profile_name: "field-team",
    display_name: "Field Team",
    description: "Second trusted profile",
    version_label: "1.0",
    template_filename: "recap_template.xlsx",
    source_kind: "published_clone",
    current_published_version_number: 1,
    has_open_draft: false,
    is_active_profile: false,
    archived_at: null,
  };
  const archivedSecondProfile = {
    ...secondProfile,
    archived_at: "2026-04-07T12:00:00Z",
  };
  const defaultDetail = buildPublishedDetail();
  const defaultDraft = {
    ...clone(buildDraftState()),
    trusted_profile_draft_id: "draft-default",
    trusted_profile_id: defaultProfile.trusted_profile_id,
    profile_name: defaultProfile.profile_name,
    display_name: defaultProfile.display_name,
    description: defaultProfile.description,
    draft_content_hash: "draft-default-hash",
  };
  const secondDetail = {
    ...clone(buildPublishedDetail(null, 1, "field-profile-hash-v1")),
    trusted_profile_id: secondProfile.trusted_profile_id,
    profile_name: secondProfile.profile_name,
    display_name: secondProfile.display_name,
    description: secondProfile.description,
    current_published_version: {
      trusted_profile_version_id: "trusted-profile-version-field-team-1",
      version_number: 1,
      content_hash: "field-profile-hash-v1",
      template_artifact_ref: "template-artifact:default",
      template_file_hash: "template-file-hash",
      template_filename: "recap_template.xlsx",
    },
  };
  const secondDraft = {
    ...clone(buildDraftState()),
    trusted_profile_draft_id: "draft-field-team",
    trusted_profile_id: secondProfile.trusted_profile_id,
    profile_name: secondProfile.profile_name,
    display_name: secondProfile.display_name,
    description: secondProfile.description,
    current_published_version: clone(secondDetail.current_published_version),
    base_trusted_profile_version_id: secondDetail.current_published_version.trusted_profile_version_id,
    draft_content_hash: "draft-field-team-hash",
    default_omit_rules: [],
    labor_mappings: [
      {
        raw_value: "CARPENTER",
        target_classification: "Journeyman",
        notes: "Seeded from published profile",
        is_observed: false,
      },
    ],
    equipment_mappings: [
      {
        raw_description: "MINI EX",
        target_category: "Excavator",
        is_observed: false,
      },
    ],
    validation_errors: [],
  };
  const state = {
    activeTrustedProfiles: options?.includeSecondProfileInitially ? [defaultProfile, secondProfile] : [defaultProfile],
    archivedTrustedProfiles: [] as Array<typeof defaultProfile | typeof archivedSecondProfile>,
    defaultDetail,
    defaultDraft,
    secondDetail,
    secondDraft,
  };
  let deferredFieldTeamDetailResolve: (() => void) | null = null;
  let deferredFieldTeamDetailUsed = false;
  let failedFieldTeamDetailUsed = false;

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    if (url === "/api/trusted-profiles" && method === "GET") {
      return new Response(JSON.stringify(state.activeTrustedProfiles), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/trusted-profiles?include_archived=true" && method === "GET") {
      return new Response(JSON.stringify([...state.activeTrustedProfiles, ...state.archivedTrustedProfiles]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles" && method === "POST") {
      state.activeTrustedProfiles = [defaultProfile, secondProfile];
      return new Response(JSON.stringify(state.secondDetail), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:default" && method === "GET") {
      return new Response(JSON.stringify(state.defaultDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:default/draft" && method === "POST") {
      state.defaultDetail.open_draft_id = state.defaultDraft.trusted_profile_draft_id;
      return new Response(JSON.stringify(state.defaultDraft), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-default" && method === "GET") {
      return new Response(JSON.stringify(state.defaultDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-default" && method === "DELETE") {
      state.defaultDetail.open_draft_id = null;
      return new Response(null, { status: 204 });
    }

    if (url === "/api/profile-drafts/draft-default" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      applyAtomicDraftSave(state.defaultDraft, payload);
      state.defaultDraft.draft_revision += 1;
      state.defaultDraft.draft_content_hash = `draft-default-hash-v${state.defaultDraft.draft_revision}`;
      return new Response(JSON.stringify(state.defaultDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-default/default-omit" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.defaultDraft.default_omit_rules = payload.default_omit_rules;
      return new Response(JSON.stringify(state.defaultDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-default/labor-mappings" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.defaultDraft.labor_mappings = payload.labor_mappings;
      return new Response(JSON.stringify(state.defaultDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:field-team" && method === "GET") {
      if (options?.failFieldTeamDetailOnce && !failedFieldTeamDetailUsed) {
        failedFieldTeamDetailUsed = true;
        return new Response(JSON.stringify({ detail: "Internal Server Error" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (options?.deferFieldTeamDetailOnce && !deferredFieldTeamDetailUsed) {
        deferredFieldTeamDetailUsed = true;
        return new Promise<Response>((resolve) => {
          deferredFieldTeamDetailResolve = () =>
            resolve(
              new Response(JSON.stringify(state.secondDetail), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              }),
            );
        });
      }
      return new Response(JSON.stringify(state.secondDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:field-team/draft" && method === "POST") {
      state.secondDetail.open_draft_id = state.secondDraft.trusted_profile_draft_id;
      return new Response(JSON.stringify(state.secondDraft), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-field-team" && method === "GET") {
      return new Response(JSON.stringify(state.secondDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-field-team" && method === "DELETE") {
      state.secondDetail.open_draft_id = null;
      return new Response(null, { status: 204 });
    }

    if (url === "/api/profile-drafts/draft-field-team" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      applyAtomicDraftSave(state.secondDraft, payload);
      state.secondDraft.draft_revision += 1;
      state.secondDraft.draft_content_hash = `draft-field-team-hash-v${state.secondDraft.draft_revision}`;
      return new Response(JSON.stringify(state.secondDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-field-team/default-omit" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.secondDraft.default_omit_rules = payload.default_omit_rules;
      return new Response(JSON.stringify(state.secondDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-field-team/labor-mappings" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.secondDraft.labor_mappings = payload.labor_mappings;
      return new Response(JSON.stringify(state.secondDraft), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-field-team/publish" && method === "POST") {
      state.secondDetail.current_published_version = {
        trusted_profile_version_id: "trusted-profile-version-field-team-2",
        version_number: 2,
        content_hash: "field-profile-hash-v2",
        template_artifact_ref: "template-artifact:default",
        template_file_hash: "template-file-hash",
        template_filename: "recap_template.xlsx",
      };
      state.secondDetail.open_draft_id = null;
      return new Response(JSON.stringify(state.secondDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:field-team/archive" && method === "POST") {
      state.activeTrustedProfiles = [defaultProfile];
      state.archivedTrustedProfiles = [archivedSecondProfile];
      return new Response(null, {
        status: 204,
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:field-team/unarchive" && method === "POST") {
      state.activeTrustedProfiles = [defaultProfile, secondProfile];
      state.archivedTrustedProfiles = [];
      return new Response(null, {
        status: 204,
      });
    }

    throw new Error(`Unhandled fetch call for ${method} ${url}`);
  });

  return {
    state,
    resolveDeferredFieldTeamDetail() {
      deferredFieldTeamDetailResolve?.();
      deferredFieldTeamDetailResolve = null;
    },
  };
}

function installCreateConflictFetchMock() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    if ((url === "/api/trusted-profiles" || url === "/api/trusted-profiles?include_archived=true") && method === "GET") {
      return new Response(JSON.stringify(trustedProfilesPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles/trusted-profile:org-default:default" && method === "GET") {
      return new Response(JSON.stringify(buildPublishedDetail()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profiles" && method === "POST") {
      return new Response(
        JSON.stringify({
          detail: {
            message: "Choose a unique profile key and display name before creating this trusted profile.",
            error_code: "trusted_profile_identity_conflict",
            field_errors: {
              profile_name: ["Trusted profile key 'future-team' already exists. Choose a different stable profile key."],
              display_name: ["Display name 'Future Team' is already in use by another active trusted profile."],
            },
          },
        }),
        {
          status: 409,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    throw new Error(`Unhandled fetch call for ${method} ${url}`);
  });
}

describe("Profile settings workspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("inspects the live profile, edits the five Phase 2A domains, and saves profile settings in one action", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();
    expect(screen.queryByText("Read only in Phase 2A. Template identity is still part of the live version.")).not.toBeInTheDocument();
    expect(screen.queryByText("Vendor Normalization")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit current profile/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create draft from published version/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open current draft/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /publish draft/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    expect(await screen.findByText("Default Omit Rules")).toBeInTheDocument();
    expect(screen.getByText("Labor Mappings")).toBeInTheDocument();
    expect(screen.getByText("Equipment Mappings")).toBeInTheDocument();
    expect(screen.getByText("Classifications")).toBeInTheDocument();
    expect(screen.getByText("Rates")).toBeInTheDocument();
    expect(screen.getAllByText("Observed").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: /save profile settings/i })).toBeEnabled();
    expect(screen.getAllByText("Save to clear unpublished changes").length).toBeGreaterThanOrEqual(1);

    await user.click(screen.getByRole("button", { name: /add default omit rule/i }));
    await user.type(screen.getByLabelText(/default omit phase code 2/i), "50 .1");

    await user.selectOptions(screen.getByLabelText(/labor target classification 1/i), "Journeyman");
    await user.clear(screen.getByLabelText(/equipment rate 1/i));
    await user.type(screen.getByLabelText(/equipment rate 1/i), "130");
    expect(screen.getByDisplayValue("130")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/equipment target category 1/i), "Excavator");

    await user.clear(screen.getByLabelText(/labor classification label 2/i));
    await user.type(screen.getByLabelText(/labor classification label 2/i), "Lead Labor");

    await user.clear(screen.getByLabelText(/equipment rate 1/i));
    await user.type(screen.getByLabelText(/equipment rate 1/i), "130");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save profile settings/i })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for default profile/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /edit current profile/i })).toBeInTheDocument();
    expect(screen.getByText(/viewing live profile settings only/i)).toBeInTheDocument();
    expect(screen.queryByText("profile-hash-v2")).not.toBeInTheDocument();
    expect(screen.queryByText("draft-1")).not.toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default" && (!init || !init.method || init.method === "GET"))).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default/draft" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/default-omit" && init?.method === "PATCH")).toBe(false);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH")).toBe(false);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/equipment-mappings" && init?.method === "PATCH")).toBe(false);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/classifications" && init?.method === "PATCH")).toBe(false);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/rates" && init?.method === "PATCH")).toBe(false);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/publish" && init?.method === "POST")).toBe(true);
    expect(
      fetchCalls.filter(
        ([url, init]) => url === "/api/profiles/trusted-profile:org-default:default" && (!init || !init.method || init.method === "GET"),
      ).length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("prioritizes required mapping rows and applies bulk labor and equipment targets in settings", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    expect(await screen.findAllByText("Required now")).toHaveLength(2);

    await user.click(screen.getByRole("checkbox", { name: /select labor mapping 1/i }));
    await user.click(screen.getByRole("checkbox", { name: /select labor mapping 3/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /bulk labor mapping target/i }), "Journeyman");
    await user.click(screen.getByRole("button", { name: /apply labor target/i }));

    expect(screen.getByLabelText(/labor target classification 1/i)).toHaveValue("Journeyman");
    expect(screen.getByLabelText(/labor target classification 3/i)).toHaveValue("Journeyman");

    await user.click(screen.getByRole("checkbox", { name: /select equipment mapping 1/i }));
    await user.click(screen.getByRole("checkbox", { name: /select equipment mapping 3/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /bulk equipment mapping target/i }), "Excavator");
    await user.click(screen.getByRole("button", { name: /apply equipment class/i }));

    expect(screen.getByLabelText(/equipment target category 1/i)).toHaveValue("Excavator");
    expect(screen.getByLabelText(/equipment target category 3/i)).toHaveValue("Excavator");
  });

  it("shows advisory equipment suggestions and only applies them when the user chooses them", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    expect(await screen.findAllByText(/likely match: excavator/i)).toHaveLength(2);
    expect(screen.getByLabelText(/equipment target category 1/i)).toHaveValue("");

    await user.click(screen.getAllByRole("button", { name: /use suggestion/i })[0]);

    expect(screen.getByLabelText(/equipment target category 1/i)).toHaveValue("Excavator");
  });

  it("keeps save available after a local edit is reverted back to the live unpublished baseline", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    const laborInput = await screen.findByLabelText(/labor raw value 2/i);
    await user.clear(laborInput);
    await user.type(laborInput, "TEMP-LABOR");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save profile settings/i })).toBeEnabled();
      expect(screen.getAllByText("Ready to save profile settings").length).toBeGreaterThanOrEqual(1);
    });

    await user.clear(laborInput);
    await user.type(laborInput, "CARPENTER");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save profile settings/i })).toBeEnabled();
      expect(screen.getAllByText("Save to clear unpublished changes").length).toBeGreaterThanOrEqual(1);
    });

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v1 for default profile/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /edit current profile/i })).toBeInTheDocument();
    expect(screen.queryByText("Unpublished changes")).not.toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/publish" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH")).toBe(false);
  });

  it("retires labor rates before classifications when a labor slot is marked inactive", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ enforceClassificationReferenceValidation: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Classifications");

    const foremanRow = screen.getByLabelText(/labor classification label 2/i).closest("tr");
    expect(foremanRow).not.toBeNull();
    await user.click(within(foremanRow as HTMLTableRowElement).getByRole("checkbox"));

    expect(await screen.findByText(/labor rates to retire: foreman\./i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for default profile/i)).toBeInTheDocument();
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const saveCallIndex = fetchCalls.findIndex(
      ([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH",
    );

    expect(saveCallIndex).toBeGreaterThanOrEqual(0);

    const savePayload = JSON.parse(String(fetchCalls[saveCallIndex]?.[1]?.body));
    expect(savePayload.labor_rates).toEqual([
      {
        classification: "Journeyman",
        standard_rate: "45",
        overtime_rate: "67.5",
        double_time_rate: "90",
      },
    ]);
  });

  it("retires equipment rates before classifications when an equipment slot is marked inactive", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ enforceClassificationReferenceValidation: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Classifications");

    const bucketTruckRow = screen.getByLabelText(/equipment classification label 2/i).closest("tr");
    expect(bucketTruckRow).not.toBeNull();
    await user.click(within(bucketTruckRow as HTMLTableRowElement).getByRole("checkbox"));

    expect(await screen.findByText(/equipment rates to retire: bucket truck\./i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for default profile/i)).toBeInTheDocument();
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const saveCallIndex = fetchCalls.findIndex(
      ([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH",
    );

    expect(saveCallIndex).toBeGreaterThanOrEqual(0);

    const savePayload = JSON.parse(String(fetchCalls[saveCallIndex]?.[1]?.body));
    expect(savePayload.equipment_rates).toEqual([
      {
        category: "Excavator",
        rate: "125",
      },
    ]);
  });

  it("keeps mapping cleanup explicit when a deactivated classification is still referenced by a mapping", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ enforceClassificationReferenceValidation: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Classifications");

    const journeymanRow = screen.getByLabelText(/labor classification label 1/i).closest("tr");
    expect(journeymanRow).not.toBeNull();
    await user.click(within(journeymanRow as HTMLTableRowElement).getByRole("checkbox"));

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    const alerts = await screen.findAllByRole("alert");
    expect(
      alerts.some((alert) =>
        new RegExp("labor classification 'journeyman' is still referenced by labor mapping 'carpenter'", "i").test(
          alert.textContent ?? "",
        ),
      ),
    ).toBe(true);

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH")).toBe(false);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/publish" && init?.method === "POST")).toBe(
      false,
    );
  });

  it("saves renamed labor classifications before dependent labor mappings", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ enforceClassificationReferenceValidation: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");

    await user.selectOptions(screen.getByLabelText(/labor target classification 2/i), "Foreman");
    await user.clear(screen.getByLabelText(/labor classification label 2/i));
    await user.type(screen.getByLabelText(/labor classification label 2/i), "Big Boy");
    await user.selectOptions(screen.getByLabelText(/labor target classification 2/i), "Big Boy");

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for default profile/i)).toBeInTheDocument();
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const saveCallIndex = fetchCalls.findIndex(
      ([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH",
    );

    expect(saveCallIndex).toBeGreaterThanOrEqual(0);
    expect(
      fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/classifications" && init?.method === "PATCH"),
    ).toBe(false);
    expect(
      fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH"),
    ).toBe(false);
    expect(screen.queryByText(/references unknown target classification 'big boy'/i)).not.toBeInTheDocument();
  });

  it("saves labor deactivation and remap in one atomic draft save", async () => {
    const user = userEvent.setup();
    const state = installSettingsFetchMock({ enforceClassificationReferenceValidation: true });
    state.draftState.labor_mappings = [
      {
        raw_value: "103/J",
        target_classification: "Journeyman",
        notes: "Baseline row",
        is_observed: false,
      },
    ];
    state.draftState.labor_rates = [
      {
        classification: "Journeyman",
        standard_rate: "45",
        overtime_rate: "67.5",
        double_time_rate: "90",
      },
      {
        classification: "Foreman",
        standard_rate: "55",
        overtime_rate: "82.5",
        double_time_rate: "110",
      },
    ];
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");

    await user.selectOptions(screen.getByLabelText(/labor target classification 1/i), "Foreman");

    const journeymanRow = screen.getByLabelText(/labor classification label 1/i).closest("tr");
    expect(journeymanRow).not.toBeNull();
    await user.click(within(journeymanRow as HTMLTableRowElement).getByRole("checkbox"));

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for default profile/i)).toBeInTheDocument();
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH")).toBe(true);
    expect(
      fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/classifications" && init?.method === "PATCH"),
    ).toBe(false);
    expect(screen.queryByText(/still referenced by labor mapping/i)).not.toBeInTheDocument();
  });

  it("saves equipment deactivation and remap in one atomic draft save", async () => {
    const user = userEvent.setup();
    const state = installSettingsFetchMock({ enforceClassificationReferenceValidation: true });
    state.draftState.equipment_mappings = [
      {
        raw_description: "CHEVROLET 6500 26FT BOX TRUCK (LOOPS)",
        target_category: "Bucket Truck",
        is_observed: false,
      },
    ];
    state.draftState.equipment_rates = [
      {
        category: "Excavator",
        rate: "125",
      },
      {
        category: "Bucket Truck",
        rate: "210",
      },
    ];
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Equipment Mappings");

    await user.selectOptions(screen.getByLabelText(/equipment target category 1/i), "Excavator");

    const bucketTruckRow = screen.getByLabelText(/equipment classification label 2/i).closest("tr");
    expect(bucketTruckRow).not.toBeNull();
    await user.click(within(bucketTruckRow as HTMLTableRowElement).getByRole("checkbox"));

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for default profile/i)).toBeInTheDocument();
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH")).toBe(true);
    expect(
      fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/classifications" && init?.method === "PATCH"),
    ).toBe(false);
    expect(screen.queryByText(/still referenced by equipment mapping/i)).not.toBeInTheDocument();
  });

  it("loads existing unpublished profile changes and shows save failure clearly", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ openDraftId: "draft-1", publishFails: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    expect(await screen.findByRole("button", { name: /edit current profile/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    expect(await screen.findByText("Observed placeholders remain in these profile changes.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/labor raw value 2/i));
    await user.type(screen.getByLabelText(/labor raw value 2/i), "UPDATED-LABOR");

    await user.click(screen.getByRole("button", { name: /save profile settings/i }));

    expect((await screen.findAllByText("Draft validation failed before publish.")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("alert").length).toBeGreaterThanOrEqual(1);

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && (!init || !init.method || init.method === "GET"))).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default/draft" && init?.method === "POST")).toBe(false);
  });

  it("recovers when the published detail points at a stale open draft id", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ openDraftId: "draft-1", draftGetNotFoundOnce: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    expect(await screen.findByText("Default Omit Rules")).toBeInTheDocument();
    expect(screen.getByText(/recovered a missing unpublished-change link/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && (!init || !init.method || init.method === "GET"))).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default/draft" && init?.method === "POST")).toBe(true);
  });

  it("does not restore a false empty retained draft after leaving settings and reopening current profile editing", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ openDraftId: "draft-1" });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(await screen.findByRole("button", { name: /edit current profile/i }));
    expect(await screen.findByText("Labor Mappings")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    await user.click(await screen.findByRole("button", { name: /don't save/i }));
    expect(screen.getByText("Open a report in the review workspace to inspect rows and apply corrections.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();
    expect(screen.queryByText(/restored .* from unsaved browser edits/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    expect(await screen.findByDisplayValue("CARPENTER")).toBeInTheDocument();
    expect(screen.getByDisplayValue("125")).toBeInTheDocument();
    expect(screen.queryByText(/restored .* from unsaved browser edits/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no labor mappings are saved yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no equipment mappings are saved yet/i)).not.toBeInTheDocument();
  });

  it("prompts before leaving settings and stays put when the user chooses to keep editing", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");
    await user.clear(screen.getByLabelText(/labor raw value 2/i));
    await user.type(screen.getByLabelText(/labor raw value 2/i), "CHANGED-LABOR");

    await user.click(screen.getByRole("button", { name: /review workspace/i }));

    expect(await screen.findByRole("dialog", { name: /leave profile settings with unpublished changes/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /stay here/i }));

    expect(screen.getByRole("heading", { name: "Default Profile" })).toBeInTheDocument();
    expect(screen.getByLabelText(/labor raw value 2/i)).toHaveValue("CHANGED-LABOR");
    expect(screen.queryByRole("dialog", { name: /leave profile settings with unpublished changes/i })).not.toBeInTheDocument();
  });

  it("prompts before leaving settings even when the draft only has unpublished changes and no local dirty sections", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");

    await user.click(screen.getByRole("button", { name: /review workspace/i }));

    expect(await screen.findByRole("dialog", { name: /leave profile settings with unpublished changes/i })).toBeInTheDocument();
    expect(screen.getByText(/still has unpublished profile changes open/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /don't save/i }));
    expect(await screen.findByText("Open a report in the review workspace to inspect rows and apply corrections.")).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "DELETE")).toBe(true);
  });

  it("saves and publishes profile changes before leaving settings when the user chooses save and leave", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");
    await user.clear(screen.getByLabelText(/labor raw value 2/i));
    await user.type(screen.getByLabelText(/labor raw value 2/i), "SAVED-LABOR");

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    await user.click(await screen.findByRole("button", { name: /save and leave/i }));

    expect(await screen.findByText("Open a report in the review workspace to inspect rows and apply corrections.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    expect(await screen.findByRole("button", { name: /edit current profile/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));

    expect(await screen.findByLabelText(/labor raw value 2/i)).toHaveValue("SAVED-LABOR");

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/publish" && init?.method === "POST")).toBe(true);
  });

  it("discards unpublished profile changes when the user leaves settings without saving", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");
    await user.clear(screen.getByLabelText(/labor raw value 2/i));
    await user.type(screen.getByLabelText(/labor raw value 2/i), "DISCARDED-LABOR");

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    await user.click(await screen.findByRole("button", { name: /don't save/i }));

    expect(await screen.findByText("Open a report in the review workspace to inspect rows and apply corrections.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    expect(await screen.findByRole("button", { name: /edit current profile/i })).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && init?.method === "DELETE")).toBe(true);
  });

  it("does not show the removed live profile metadata summary or desktop sync action", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();
    expect(screen.queryByText("Live Profile Summary")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create desktop sync archive/i })).not.toBeInTheDocument();
    expect(screen.queryByText("default__v1.zip")).not.toBeInTheDocument();
  });

  it("uses hosted-only guidance for seeded profiles and does not surface desktop sync affordances", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();
    expect(
      screen.getByText(/bundled default profiles stay read-only in hosted settings/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/desktop\/filesystem path/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /desktop sync/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/manual desktop sync/i)).not.toBeInTheDocument();
  });

  it("creates a second profile and saves its settings through the simplified current-profile flow", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.type(screen.getByLabelText(/new profile description/i), "Second trusted profile");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));

    expect(await screen.findByRole("heading", { name: "Field Team" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit current profile/i })).toBeInTheDocument();
    expect(screen.queryByText("field-profile-hash-v1")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    expect(await screen.findByText("Default Omit Rules")).toBeInTheDocument();
    expect(screen.getAllByText(/editing current profile/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /add default omit rule/i }));
    await user.type(screen.getByLabelText(/default omit phase code 1/i), "50");
    await user.click(screen.getByRole("button", { name: /save profile settings/i }));
    await waitFor(() => {
      expect(screen.getByText(/saved profile settings and published live version v2 for field team/i)).toBeInTheDocument();
    });
    expect(screen.queryByText("field-profile-hash-v2")).not.toBeInTheDocument();
    expect(screen.getByText(/viewing live profile settings only/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team/draft" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team/publish" && init?.method === "POST")).toBe(true);
  });

  it("renders active profiles as compact selector rows with minimal inline status while preserving switching behavior", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));

    const defaultRow = await screen.findByRole("button", { name: "Default Profile" });
    const fieldTeamRow = await screen.findByRole("button", { name: "Field Team" });
    expect(defaultRow).toHaveAttribute("aria-pressed", "false");
    expect(fieldTeamRow).toHaveAttribute("aria-pressed", "true");
    expect(within(fieldTeamRow).getByText("v1")).toBeInTheDocument();
    expect(within(fieldTeamRow).queryByText("Selected")).not.toBeInTheDocument();
    expect(within(fieldTeamRow).queryByText("Local unsaved edits")).not.toBeInTheDocument();
    expect(within(fieldTeamRow).queryByText("Web-created")).not.toBeInTheDocument();

    await user.click(defaultRow);
    expect(await screen.findByRole("heading", { name: "Default Profile" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Field Team" }));
    expect(await screen.findByRole("heading", { name: "Field Team" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Default Omit Rules");
    expect(within(screen.getByRole("button", { name: "Field Team" })).getByText("Unpublished changes")).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/labor raw value 1/i));
    await user.type(screen.getByLabelText(/labor raw value 1/i), "FIELD-LABOR");
    expect(screen.getByText("Local unsaved edits retained")).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Field Team" })).queryByText("Local unsaved edits")).not.toBeInTheDocument();
  });

  it("blocks duplicate local profile creation input and protects profile switching when the user stays on unsaved edits", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    await user.type(screen.getByLabelText(/new profile display name/i), "Default Profile");
    expect(await screen.findAllByText(/already in use/i)).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: /create profile from published version/i })).toBeDisabled();

    await user.clear(screen.getByLabelText(/new profile display name/i));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Default Omit Rules");
    await user.click(screen.getByRole("button", { name: /add default omit rule/i }));
    await user.type(await screen.findByLabelText(/default omit phase code 1/i), "50");

    await user.click(screen.getByRole("button", { name: "Default Profile" }));

    expect(await screen.findByRole("dialog", { name: /leave profile settings with unpublished changes/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /stay here/i }));
    expect(screen.getByRole("heading", { name: "Field Team" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("50")).toBeInTheDocument();
  });

  it("saves and publishes profile changes before switching trusted profiles when the user chooses save and leave", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Default Omit Rules");
    await user.clear(screen.getByLabelText(/labor raw value 1/i));
    await user.type(screen.getByLabelText(/labor raw value 1/i), "FIELD-LABOR");

    await user.click(screen.getByRole("button", { name: "Default Profile" }));
    await user.click(await screen.findByRole("button", { name: /save and leave/i }));

    await screen.findByRole("heading", { name: "Default Profile" });
    await user.click(screen.getByRole("button", { name: "Field Team" }));
    await screen.findByRole("heading", { name: "Field Team" });
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    expect(await screen.findByLabelText(/labor raw value 1/i)).toHaveValue("FIELD-LABOR");

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team/publish" && init?.method === "POST")).toBe(true);
  });

  it("re-enters profile settings under the newly selected review profile instead of reusing the prior profile editor context", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: "Default Profile" }));
    await screen.findByRole("heading", { name: "Default Profile" });

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    const reviewTrustedProfileSelect = screen.getByRole("combobox", { name: /trusted profile/i });
    await user.selectOptions(reviewTrustedProfileSelect, "field-team");
    await waitFor(() => {
      expect(reviewTrustedProfileSelect).toHaveValue("field-team");
    });
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await screen.findByRole("heading", { name: "Field Team" });
    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^edit current profile$/i }));
    await screen.findByText("Default Omit Rules");

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team/draft" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-default" && (!init || !init.method || init.method === "GET"))).toBe(false);
  });

  it("re-enters profile settings cleanly after switching trusted profiles inside settings and leaving through review", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: "Default Profile" }));
    await screen.findByRole("heading", { name: "Default Profile" });
    await user.click(screen.getByRole("button", { name: "Field Team" }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: /review workspace/i }));
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await screen.findByRole("heading", { name: "Field Team" });
    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^edit current profile$/i }));
    await screen.findByText("Default Omit Rules");

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(
      fetchCalls.filter(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team" && (!init || !init.method || init.method === "GET")),
    ).not.toHaveLength(0);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team/draft" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-default" && (!init || !init.method || init.method === "GET"))).toBe(false);
  });

  it("recovers automatically when the first settings load for a newly selected startup profile hits a transient server error", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock({ failFieldTeamDetailOnce: true, includeSecondProfileInitially: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    const reviewTrustedProfileSelect = screen.getByRole("combobox", { name: /trusted profile/i });
    await user.selectOptions(reviewTrustedProfileSelect, "field-team");
    await waitFor(() => {
      expect(reviewTrustedProfileSelect).toHaveValue("field-team");
    });

    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await screen.findByRole("heading", { name: "Field Team" });
    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();
    expect(screen.queryByText(/internal server error/i)).not.toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(
      fetchCalls.filter(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team" && (!init || !init.method || init.method === "GET")),
    ).toHaveLength(2);
  });

  it("archives a published user-created profile and removes it from the active selector list", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: /archive selected profile/i }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Default Profile" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Field Team" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore to active profiles/i })).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team/archive" && init?.method === "POST")).toBe(true);
  });

  it("restores an archived user-created profile back into the active selector list", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: /archive selected profile/i }));
    await screen.findByRole("button", { name: /restore to active profiles/i });

    await user.click(screen.getByRole("button", { name: /restore to active profiles/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Field Team" })).toBeInTheDocument();
    });
    expect(screen.getByText(/restored field team to the active trusted profile lists/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Field Team" }));
    expect(await screen.findByRole("heading", { name: "Field Team" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /edit current profile/i })).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:field-team/unarchive" && init?.method === "POST")).toBe(true);
  });

  it("surfaces server-side create conflicts inline on the matching profile fields", async () => {
    const user = userEvent.setup();
    installCreateConflictFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    await user.type(screen.getByLabelText(/new profile display name/i), "Future Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));

    expect(await screen.findByText(/trusted profile key 'future-team' already exists/i)).toBeInTheDocument();
    expect(screen.getByText(/display name 'future team' is already in use/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/new profile display name/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("best-effort discards an open profile draft on page exit so unpublished changes do not survive browser navigation", async () => {
    const user = userEvent.setup();
    const state = installSettingsFetchMock();
    const view = render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Labor Mappings");

    window.dispatchEvent(new Event("pagehide"));

    await waitFor(() => {
      expect(
        vi
          .mocked(globalThis.fetch)
          .mock.calls.some(
            ([url, init]) =>
              url === "/api/profile-drafts/draft-1" &&
              init?.method === "DELETE" &&
              init?.keepalive === true,
          ),
      ).toBe(true);
    });
    expect(state.publishedDetail.open_draft_id).toBeNull();

    view.unmount();
    render(<App />);

    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();
    expect(screen.queryByText("Unpublished changes")).not.toBeInTheDocument();
  });
});
