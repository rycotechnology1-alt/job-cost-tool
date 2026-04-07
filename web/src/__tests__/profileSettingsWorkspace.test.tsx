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
    is_active_profile: true,
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
      },
      {
        raw_value: "CARPENTER",
        target_classification: "Journeyman",
        notes: "Baseline row",
        is_observed: false,
      },
    ],
    equipment_mappings: [
      {
        raw_description: "NEW OBSERVED EQUIPMENT",
        target_category: "",
        is_observed: true,
      },
      {
        raw_description: "MINI EX",
        target_category: "Excavator",
        is_observed: false,
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

function installSettingsFetchMock(options?: { openDraftId?: string | null; publishFails?: boolean }) {
  const state = {
    publishedDetail: buildPublishedDetail(options?.openDraftId ?? null),
    draftState: buildDraftState(),
    publishFails: options?.publishFails ?? false,
  };

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    if (url === "/api/trusted-profiles" && method === "GET") {
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
      return new Response(JSON.stringify(state.draftState), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
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

describe("Profile settings workspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("inspects the published profile, edits the five Phase 2A domains, marks observed rows, and publishes", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    expect(await screen.findByText("Published Profile Summary")).toBeInTheDocument();
    expect(screen.getByText("Read only in Phase 2A. Template identity is still part of the published version.")).toBeInTheDocument();
    expect(screen.getByText("Vendor Normalization")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /create draft from published version/i }));

    expect(await screen.findByText("Default Omit Rules")).toBeInTheDocument();
    expect(screen.getByText("Labor Mappings")).toBeInTheDocument();
    expect(screen.getByText("Equipment Mappings")).toBeInTheDocument();
    expect(screen.getByText("Classifications")).toBeInTheDocument();
    expect(screen.getByText("Rates")).toBeInTheDocument();
    expect(screen.getAllByText("Observed").length).toBeGreaterThanOrEqual(2);

    await user.click(screen.getByRole("button", { name: /save default omit rules/i }));

    await user.selectOptions(screen.getByLabelText(/labor target classification 1/i), "Journeyman");
    await user.click(screen.getByRole("button", { name: /save labor mappings/i }));

    await user.selectOptions(screen.getByLabelText(/equipment target category 1/i), "Excavator");
    await user.click(screen.getByRole("button", { name: /save equipment mappings/i }));

    await user.clear(screen.getByLabelText(/labor classification label 1/i));
    await user.type(screen.getByLabelText(/labor classification label 1/i), "Lead Labor");
    await user.click(screen.getByRole("button", { name: /save classifications/i }));

    await user.clear(screen.getByLabelText(/equipment rate 1/i));
    await user.type(screen.getByLabelText(/equipment rate 1/i), "130");
    await user.click(screen.getByRole("button", { name: /save rates/i }));

    await user.click(screen.getByRole("button", { name: /publish draft/i }));

    await waitFor(() => {
      expect(screen.getByText("No draft is open for this profile.")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /create draft from published version/i })).toBeInTheDocument();
    expect(screen.getByText("profile-hash-v2")).toBeInTheDocument();
    expect(screen.getByText(/published version v2 for default profile/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default" && (!init || !init.method || init.method === "GET"))).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default/draft" && init?.method === "POST")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/default-omit" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/labor-mappings" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/equipment-mappings" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/classifications" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/rates" && init?.method === "PATCH")).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1/publish" && init?.method === "POST")).toBe(true);
  });

  it("loads an existing open draft and shows publish failure clearly", async () => {
    const user = userEvent.setup();
    installSettingsFetchMock({ openDraftId: "draft-1", publishFails: true });
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.click(screen.getByRole("button", { name: /profile settings/i }));

    expect(await screen.findByRole("button", { name: /open current draft/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /open current draft/i }));
    expect(await screen.findByText("Observed placeholders remain in this draft.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /publish draft/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Draft validation failed before publish.");

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(fetchCalls.some(([url, init]) => url === "/api/profile-drafts/draft-1" && (!init || !init.method || init.method === "GET"))).toBe(true);
    expect(fetchCalls.some(([url, init]) => url === "/api/profiles/trusted-profile:org-default:default/draft" && init?.method === "POST")).toBe(false);
  });

  it("creates and downloads a manual desktop-sync archive from the published version summary", async () => {
    const originalCreateObjectUrl = URL.createObjectURL;
    const originalRevokeObjectUrl = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:sync-download");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    try {
      const user = userEvent.setup();
      installSettingsFetchMock();
      render(<App />);

      await screen.findByText("Trusted profiles loaded.");
      await user.click(screen.getByRole("button", { name: /profile settings/i }));
      expect(await screen.findByText("Published Profile Summary")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /create desktop sync archive/i }));

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith("/api/profile-sync-exports/sync-export-1/download", undefined);
      });
      expect(await screen.findByText("default__v1.zip")).toBeInTheDocument();

      const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
      expect(
        fetchCalls.some(
          ([url, init]) => url === "/api/profile-versions/trusted-profile-version-1/desktop-sync-export" && init?.method === "POST",
        ),
      ).toBe(true);
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:sync-download");
    } finally {
      URL.createObjectURL = originalCreateObjectUrl;
      URL.revokeObjectURL = originalRevokeObjectUrl;
    }
  });
});
