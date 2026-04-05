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
  {
    trusted_profile_id: "trusted-profile:org-default:alternate",
    profile_name: "alternate",
    display_name: "Alternate Profile",
    description: "Alternate trusted profile",
    version_label: "1.1",
    template_filename: "alternate_template.xlsx",
    is_active_profile: false,
  },
];

const uploadPayload = {
  upload_id: "upload-1",
  original_filename: "report.pdf",
  content_type: "application/pdf",
  file_size_bytes: 1024,
  storage_ref: "runtime/uploads/report.pdf",
};

const runPayload = {
  processing_run_id: "processing-run-1",
  source_document_id: "source-1",
  source_document_filename: "report.pdf",
  profile_snapshot_id: "profile-snapshot-1",
  trusted_profile_id: "trusted-profile-1",
  trusted_profile_name: "alternate",
  status: "completed",
  aggregate_blockers: [],
  record_count: 2,
  created_at: "2026-04-05T12:00:00Z",
  historical_export_status: {
    status_code: "reproducible",
    is_reproducible: true,
    detail: "Historical exports are reproducible from captured template artifact lineage.",
  },
};

const runDetailPayload = {
  ...runPayload,
  run_records: [
    {
      run_record_id: "run-record-1",
      record_key: "record-0",
      record_index: 0,
      canonical_record: {
        record_type: "material",
        record_type_normalized: "material",
        phase_code: "50",
        vendor_name_normalized: "Vendor A",
        cost: 100,
      },
      source_page: 1,
      source_line_text: "Material source",
      created_at: "2026-04-05T12:00:00Z",
    },
    {
      run_record_id: "run-record-2",
      record_key: "record-1",
      record_index: 1,
      canonical_record: {
        record_type: "material",
        record_type_normalized: "material",
        phase_code: "50.3",
        vendor_name_normalized: "Concrete Vendor",
        cost: 240,
      },
      source_page: 2,
      source_line_text: "Concrete delivery invoice",
      created_at: "2026-04-05T12:00:00Z",
    },
  ],
};

const reviewSessionRevision0 = {
  review_session_id: "review-session-1",
  processing_run_id: "processing-run-1",
  current_revision: 0,
  session_revision: 0,
  blocking_issues: [],
  historical_export_status: {
    status_code: "reproducible",
    is_reproducible: true,
    detail: "Historical exports are reproducible from captured template artifact lineage.",
  },
  records: [
    {
      record_type: "material",
      phase_code: "50",
      cost: 100,
      hours: null,
      hour_type: null,
      union_code: null,
      labor_class_normalized: null,
      vendor_name: "Vendor A",
      equipment_description: null,
      equipment_category: null,
      confidence: 0.9,
      raw_description: "Material line",
      labor_class_raw: null,
      job_number: "JOB-100",
      job_name: "Sample Project",
      transaction_type: "AP",
      phase_name_raw: null,
      employee_id: null,
      employee_name: null,
      vendor_id_raw: null,
      source_page: 1,
      source_line_text: "Material source",
      warnings: [],
      record_type_normalized: "material",
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      recap_equipment_slot_id: null,
      vendor_name_normalized: "Vendor A",
      equipment_mapping_key: null,
      is_omitted: false,
    },
    {
      record_type: "material",
      phase_code: "50.3",
      cost: 240,
      hours: null,
      hour_type: null,
      union_code: null,
      labor_class_normalized: null,
      vendor_name: "Concrete Vendor",
      equipment_description: null,
      equipment_category: null,
      confidence: 0.82,
      raw_description: "Concrete delivery",
      labor_class_raw: null,
      job_number: "JOB-100",
      job_name: "Sample Project",
      transaction_type: "AP",
      phase_name_raw: null,
      employee_id: null,
      employee_name: null,
      vendor_id_raw: "V-200",
      source_page: 2,
      source_line_text: "Concrete delivery invoice",
      warnings: ["Vendor name should be confirmed"],
      record_type_normalized: "material",
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      recap_equipment_slot_id: null,
      vendor_name_normalized: "Concrete Vendor",
      equipment_mapping_key: null,
      is_omitted: false,
    },
  ],
};

const reviewSessionRevision1 = {
  ...reviewSessionRevision0,
  current_revision: 1,
  session_revision: 1,
  records: [
    reviewSessionRevision0.records[0],
    {
      ...reviewSessionRevision0.records[1],
      vendor_name_normalized: "Vendor Edited",
    },
  ],
};

const exportArtifactPayload = {
  export_artifact_id: "export-artifact-1",
  processing_run_id: "processing-run-1",
  review_session_id: "review-session-1",
  session_revision: 1,
  artifact_kind: "recap_workbook",
  template_artifact_id: "template-artifact-1",
  file_hash: "abc123",
  created_at: "2026-04-05T12:00:00Z",
  download_url: "/api/exports/export-artifact-1/download",
};

describe("App", () => {
  const originalCreateObjectUrl = URL.createObjectURL;
  const originalRevokeObjectUrl = URL.revokeObjectURL;

  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:download-url");
    URL.revokeObjectURL = vi.fn();

    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/api/trusted-profiles" && (!init || !init.method || init.method === "GET")) {
        return new Response(JSON.stringify(trustedProfilesPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/source-documents/uploads" && init?.method === "POST") {
        return new Response(JSON.stringify(uploadPayload), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/runs" && init?.method === "POST") {
        return new Response(JSON.stringify(runPayload), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/runs/processing-run-1" && (!init || !init.method || init.method === "GET")) {
        return new Response(JSON.stringify(runDetailPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/runs/processing-run-1/review-session" && (!init || !init.method || init.method === "GET")) {
        return new Response(JSON.stringify(reviewSessionRevision0), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/runs/processing-run-1/review-session/edits" && init?.method === "POST") {
        return new Response(JSON.stringify(reviewSessionRevision1), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/runs/processing-run-1/exports" && init?.method === "POST") {
        return new Response(JSON.stringify(exportArtifactPayload), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/exports/export-artifact-1/download") {
        return new Response(new Blob(["xlsx-bytes"]), {
          status: 200,
          headers: {
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": 'attachment; filename="report-recap-rev-1.xlsx"',
          },
        });
      }
      throw new Error(`Unhandled fetch call for ${url}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    URL.createObjectURL = originalCreateObjectUrl;
    URL.revokeObjectURL = originalRevokeObjectUrl;
  });

  it("opens the review workspace in one flow and lets row selection drive the edit panel", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Trusted profiles loaded.")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");
    await user.upload(screen.getByLabelText(/^source report pdf$/i), new File(["sample"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: /open review workspace/i }));

    expect(await screen.findByRole("heading", { name: "report.pdf" })).toBeInTheDocument();
    expect(screen.getByText("No current blockers.")).toBeInTheDocument();
    const concreteRow = screen.getByText("Concrete delivery").closest("tr");
    expect(concreteRow).not.toBeNull();
    expect(concreteRow).toHaveTextContent("Concrete Vendor");
    await user.click(concreteRow!);

    expect(screen.getByDisplayValue("Concrete Vendor")).toBeInTheDocument();
    expect(screen.getByText("Concrete delivery invoice")).toBeInTheDocument();
    expect(screen.getAllByText(/Page 2/i)[0]).toBeInTheDocument();
    expect(screen.getByText("Vendor name should be confirmed")).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/vendor/i));
    await user.type(screen.getByLabelText(/vendor/i), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply review change/i }));

    expect(await screen.findByDisplayValue("Vendor Edited")).toBeInTheDocument();
    expect(screen.getByText(/advanced the session to revision 1/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    const runRequest = fetchCalls.find(([url]) => url === "/api/runs");

    expect(runRequest).toBeDefined();
    expect(editRequest).toBeDefined();
    expect(JSON.parse(String(runRequest?.[1]?.body)).trusted_profile_name).toBe("alternate");
    expect(JSON.parse(String(editRequest?.[1]?.body)).edits[0].record_key).toBe("record-1");
  });

  it("exports and downloads the current review revision in one click", async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.upload(screen.getByLabelText(/^source report pdf$/i), new File(["sample"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: /open review workspace/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    const concreteRow = screen.getByText("Concrete delivery").closest("tr");
    expect(concreteRow).not.toBeNull();
    await user.click(concreteRow!);
    await user.clear(screen.getByLabelText(/vendor/i));
    await user.type(screen.getByLabelText(/vendor/i), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply review change/i }));

    await user.click(screen.getByRole("button", { name: /export and download workbook/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith("/api/exports/export-artifact-1/download", undefined);
    });

    expect(await screen.findByText("report-recap-rev-1.xlsx")).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const exportRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/exports");
    expect(exportRequest).toBeDefined();
    expect(JSON.parse(String(exportRequest?.[1]?.body)).session_revision).toBe(1);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:download-url");
  });
});
