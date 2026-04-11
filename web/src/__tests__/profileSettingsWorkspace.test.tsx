import { render, screen, waitFor } from "@testing-library/react";
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
    draft_content_hash: "draft-content-hash",
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
    ],
    labor_rates: [
      {
        classification: "Journeyman",
        standard_rate: "45",
        overtime_rate: "67.5",
        double_time_rate: "90",
      },
    ],
    equipment_rates: [
      {
        category: "Excavator",
        rate: "125",
      },
    ],
    deferred_domains: buildPublishedDetail().deferred_domains,
    validation_errors: [],
  };
}

function installSettingsFetchMock(options?: {
  openDraftId?: string | null;
  publishFails?: boolean;
  draftGetNotFoundOnce?: boolean;
}) {
  const state = {
    publishedDetail: buildPublishedDetail(options?.openDraftId ?? null),
    draftState: buildDraftState(),
    publishFails: options?.publishFails ?? false,
    draftGetNotFoundOnce: options?.draftGetNotFoundOnce ?? false,
  };

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

    if (url === "/api/profile-drafts/draft-1/default-omit" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.draftState.default_omit_rules = payload.default_omit_rules;
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/labor-mappings" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.draftState.labor_mappings = payload.labor_mappings;
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/equipment-mappings" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.draftState.equipment_mappings = payload.equipment_mappings;
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/classifications" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.draftState.labor_slots = payload.labor_slots;
      state.draftState.equipment_slots = payload.equipment_slots;
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/rates" && method === "PATCH") {
      const payload = JSON.parse(String(init?.body));
      state.draftState.labor_rates = payload.labor_rates;
      state.draftState.equipment_rates = payload.equipment_rates;
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-drafts/draft-1/publish" && method === "POST") {
      if (state.publishFails) {
        return new Response(JSON.stringify({ detail: "Draft validation failed before publish." }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        });
      }
      state.publishedDetail = buildPublishedDetail(null, 2, "profile-hash-v2");
      return new Response(JSON.stringify(state.publishedDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url === "/api/profile-versions/trusted-profile-version-1/desktop-sync-export" && method === "POST") {
      return new Response(
        JSON.stringify({
          trusted_profile_sync_export_id: "sync-export-1",
          trusted_profile_version_id: "trusted-profile-version-1",
          trusted_profile_id: "trusted-profile:org-default:default",
          profile_name: "default",
          display_name: "Default Profile",
          version_number: 1,
          archive_filename: "default__v1.zip",
          artifact_file_hash: "sync-hash-1",
          created_at: "2026-04-06T12:00:00Z",
          download_url: "/api/profile-sync-exports/sync-export-1/download",
        }),
        {
          status: 201,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    if (url === "/api/profile-sync-exports/sync-export-1/download" && method === "GET") {
      return new Response(new Blob(["sync archive bytes"]), {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="default__v1.zip"',
        },
      });
    }

    throw new Error(`Unhandled fetch call for ${method} ${url}`);
  });

  return state;
}

function installSecondProfileCreationFetchMock() {
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
    activeTrustedProfiles: [defaultProfile],
    archivedTrustedProfiles: [] as Array<typeof defaultProfile | typeof archivedSecondProfile>,
    defaultDetail,
    defaultDraft,
    secondDetail,
    secondDraft,
  };

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

  return state;
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
    expect(screen.getByRole("button", { name: /save profile settings/i })).toBeDisabled();

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
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/default-omit" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/equipment-mappings" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/classifications" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/rates" && init?.method === "PATCH")).toBe(true);
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

    expect(await screen.findByRole("dialog", { name: /leave profile settings with unsaved sections/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /stay here/i }));

    expect(screen.getByRole("heading", { name: "Default Profile" })).toBeInTheDocument();
    expect(screen.getByLabelText(/labor raw value 2/i)).toHaveValue("CHANGED-LABOR");
    expect(screen.queryByRole("dialog", { name: /leave profile settings with unsaved sections/i })).not.toBeInTheDocument();
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
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH")).toBe(true);
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

  it("creates a second profile and saves its settings through the simplified current-profile flow", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    expect(await screen.findByText(/live version v1 remains the web-processing source/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/new profile key/i), "field-team");
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
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team/default-omit" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team/publish" && init?.method === "POST")).toBe(true);
  });

  it("blocks duplicate local profile creation input and protects profile switching when the user stays on unsaved edits", async () => {
    const user = userEvent.setup();
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    await user.type(screen.getByLabelText(/new profile key/i), "default");
    await user.type(screen.getByLabelText(/new profile display name/i), "Default Profile");
    expect(await screen.findAllByText(/already in use/i)).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: /create profile from published version/i })).toBeDisabled();

    await user.clear(screen.getByLabelText(/new profile key/i));
    await user.type(screen.getByLabelText(/new profile key/i), "field-team");
    await user.clear(screen.getByLabelText(/new profile display name/i));
    await user.type(screen.getByLabelText(/new profile display name/i), "Field Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));
    await screen.findByRole("heading", { name: "Field Team" });

    await user.click(screen.getByRole("button", { name: /edit current profile/i }));
    await screen.findByText("Default Omit Rules");
    await user.click(screen.getByRole("button", { name: /add default omit rule/i }));
    await user.type(await screen.findByLabelText(/default omit phase code 1/i), "50");

    await user.click(screen.getByRole("button", { name: "Default Profile" }));

    expect(await screen.findByRole("dialog", { name: /leave profile settings with unsaved sections/i })).toBeInTheDocument();
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
    await user.type(screen.getByLabelText(/new profile key/i), "field-team");
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
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team/labor-mappings" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-field-team/publish" && init?.method === "POST")).toBe(true);
  });

  it("archives a published user-created profile and removes it from the active selector list", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    installSecondProfileCreationFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));
    await user.type(screen.getByLabelText(/new profile key/i), "field-team");
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
    await user.type(screen.getByLabelText(/new profile key/i), "field-team");
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

    await user.type(screen.getByLabelText(/new profile key/i), "future-team");
    await user.type(screen.getByLabelText(/new profile display name/i), "Future Team");
    await user.click(screen.getByRole("button", { name: /create profile from published version/i }));

    expect(await screen.findByText(/trusted profile key 'future-team' already exists/i)).toBeInTheDocument();
    expect(screen.getByText(/display name 'future team' is already in use/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/new profile key/i)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/new profile display name/i)).toHaveAttribute("aria-invalid", "true");
  });
});
