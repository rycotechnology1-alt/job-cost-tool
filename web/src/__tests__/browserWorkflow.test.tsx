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
  profile_snapshot_id: "profile-snapshot-1",
  trusted_profile_id: "trusted-profile-1",
  trusted_profile_name: "default",
  status: "completed",
  aggregate_blockers: [],
  record_count: 1,
  created_at: "2026-04-05T12:00:00Z",
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
  ],
};

const reviewSessionRevision0 = {
  review_session_id: "review-session-1",
  processing_run_id: "processing-run-1",
  current_revision: 0,
  session_revision: 0,
  blocking_issues: [],
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
  ],
};

const reviewSessionRevision1 = {
  ...reviewSessionRevision0,
  current_revision: 1,
  session_revision: 1,
  records: [
    {
      ...reviewSessionRevision0.records[0],
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
            "Content-Disposition": 'attachment; filename="recap-export.xlsx"',
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

  it("runs the minimal browser workflow against the accepted API surface", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Trusted profiles loaded.")).toBeInTheDocument();
    expect(screen.getByText("Default trusted profile")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/trusted profile/i), "alternate");
    expect(screen.getByText("Alternate trusted profile")).toBeInTheDocument();

    const fileInput = screen.getByLabelText(/source report pdf/i);
    await user.upload(fileInput, new File(["sample pdf bytes"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: /upload report/i }));

    expect(await screen.findByText("upload-1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /start processing run/i }));

    expect(await screen.findByText("processing-run-1")).toBeInTheDocument();
    expect(screen.getByText("record-0")).toBeInTheDocument();
    expect(screen.getAllByText("No aggregate blockers.")[0]).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /open review session/i }));

    expect(await screen.findByText("review-session-1")).toBeInTheDocument();
    expect(screen.getByText("No blocking issues.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("0")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/vendor name/i), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /submit edit batch/i }));

    expect(await screen.findByDisplayValue("1")).toBeInTheDocument();
    expect(screen.getByText("Vendor Edited")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /request export/i }));

    expect(await screen.findByText("export-artifact-1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /download artifact/i }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith("/api/exports/export-artifact-1/download", undefined);
    });

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    const exportRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/exports");

    expect(editRequest).toBeDefined();
    expect(exportRequest).toBeDefined();

    const editPayload = JSON.parse(String(editRequest?.[1]?.body));
    const exportPayload = JSON.parse(String(exportRequest?.[1]?.body));
    const runRequest = fetchCalls.find(([url]) => url === "/api/runs");

    expect(runRequest).toBeDefined();
    expect(JSON.parse(String(runRequest?.[1]?.body)).trusted_profile_name).toBe("alternate");
    expect(editPayload.edits[0].record_key).toBe("record-0");
    expect(editPayload.edits[0].changed_fields.vendor_name_normalized).toBe("Vendor Edited");
    expect(exportPayload.session_revision).toBe(1);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:download-url");
  });
});
