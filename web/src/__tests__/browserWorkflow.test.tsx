import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ReviewSessionResponse } from "../api/contracts";
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
  {
    trusted_profile_id: "trusted-profile:org-default:alternate",
    profile_name: "alternate",
    display_name: "Alternate Profile",
    description: "Alternate trusted profile",
    version_label: "1.1",
    template_filename: "alternate_template.xlsx",
    source_kind: "filesystem_bootstrap",
    current_published_version_number: 1,
    has_open_draft: false,
    is_active_profile: false,
    archived_at: null,
  },
];

const reviewOptionSets = {
  default: {
    labor: ["103 Journeyman", "103 Foreman"],
    equipment: ["Pick-up Truck"],
  },
  alternate: {
    labor: ["ALT Journeyman"],
    equipment: ["ALT Truck"],
  },
} as const;

interface MockOptions {
  expireCachedUploadOnSecondRun?: boolean;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function buildRunPayload(profileName: "default" | "alternate", sourceFilename = "report.pdf", recordCount = 3) {
  const trustedProfile =
    trustedProfilesPayload.find((profile) => profile.profile_name === profileName) ?? trustedProfilesPayload[0];
  return {
    processing_run_id: "processing-run-1",
    source_document_id: "source-1",
    source_document_filename: sourceFilename,
    profile_snapshot_id: "profile-snapshot-1",
    trusted_profile_id: trustedProfile.trusted_profile_id,
    trusted_profile_name: trustedProfile.profile_name,
    status: "completed",
    aggregate_blockers: [],
    record_count: recordCount,
    created_at: "2026-04-05T12:00:00Z",
    historical_export_status: {
      status_code: "reproducible",
      is_reproducible: true,
      detail: "Historical exports are reproducible from captured template artifact lineage.",
    },
  };
}

function buildRunDetailPayload(
  profileName: "default" | "alternate",
  sourceFilename = "report.pdf",
  records: ReturnType<typeof buildBaseReviewRecords> = buildBaseReviewRecords(profileName),
) {
  return {
    ...buildRunPayload(profileName, sourceFilename, records.length),
    run_records: records.map((record, index) => ({
      run_record_id: `run-record-${index + 1}`,
      record_key: `record-${index}`,
      record_index: index,
      canonical_record: {
        record_type: record.record_type,
        record_type_normalized: record.record_type_normalized,
        phase_code: record.phase_code,
        vendor_name_normalized: record.vendor_name_normalized,
        labor_class_raw: record.labor_class_raw,
        equipment_description: record.equipment_description,
        cost: record.cost,
      },
      source_page: record.source_page,
      source_line_text: record.source_line_text,
      created_at: "2026-04-05T12:00:00Z",
    })),
  };
}

function buildBaseReviewRecords(profileName: "default" | "alternate"): ReviewSessionResponse["records"] {
  const optionSet = reviewOptionSets[profileName];
  return [
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
    {
      record_type: "labor",
      phase_code: "20",
      cost: 160,
      hours: 8,
      hour_type: "ST",
      union_code: "103",
      labor_class_normalized: "J",
      vendor_name: null,
      equipment_description: optionSet.equipment[0],
      equipment_category: null,
      confidence: 0.94,
      raw_description: "Labor line",
      labor_class_raw: "J",
      job_number: "JOB-100",
      job_name: "Sample Project",
      transaction_type: "PR",
      phase_name_raw: null,
      employee_id: "E-1",
      employee_name: "Labor User",
      vendor_id_raw: null,
      source_page: 3,
      source_line_text: "Labor source",
      warnings: [],
      record_type_normalized: "labor",
      recap_labor_slot_id: null,
      recap_labor_classification: null,
      recap_equipment_slot_id: null,
      vendor_name_normalized: null,
      equipment_mapping_key: null,
      is_omitted: false,
    },
  ];
}

function buildExtraLaborReviewRecord(
  profileName: "default" | "alternate",
  rawDescription: string,
): ReviewSessionResponse["records"][number] {
  const optionSet = reviewOptionSets[profileName];
  return {
    record_type: "labor",
    phase_code: "21",
    cost: 120,
    hours: 6,
    hour_type: "ST",
    union_code: "103",
    labor_class_normalized: "J",
    vendor_name: null,
    equipment_description: optionSet.equipment[0],
    equipment_category: null,
    confidence: 0.88,
    raw_description: rawDescription,
    labor_class_raw: "J",
    job_number: "JOB-100",
    job_name: "Sample Project",
    transaction_type: "PR",
    phase_name_raw: null,
    employee_id: "E-2",
    employee_name: "Labor Helper",
    vendor_id_raw: null,
    source_page: 4,
    source_line_text: `${rawDescription} source`,
    warnings: [],
    record_type_normalized: "labor",
    recap_labor_slot_id: null,
    recap_labor_classification: null,
    recap_equipment_slot_id: null,
    vendor_name_normalized: null,
    equipment_mapping_key: null,
    is_omitted: false,
  };
}

function buildExtraEquipmentReviewRecord(rawDescription: string): ReviewSessionResponse["records"][number] {
  return {
    record_type: "equipment",
    phase_code: "30",
    cost: 210,
    hours: 5,
    hour_type: null,
    union_code: null,
    labor_class_normalized: null,
    vendor_name: null,
    equipment_description: rawDescription,
    equipment_category: null,
    confidence: 0.86,
    raw_description: rawDescription,
    labor_class_raw: null,
    job_number: "JOB-100",
    job_name: "Sample Project",
    transaction_type: "EQ",
    phase_name_raw: null,
    employee_id: null,
    employee_name: null,
    vendor_id_raw: null,
    source_page: 5,
    source_line_text: `${rawDescription} source`,
    warnings: [],
    record_type_normalized: "equipment",
    recap_labor_slot_id: null,
    recap_labor_classification: null,
    recap_equipment_slot_id: null,
    vendor_name_normalized: null,
    equipment_mapping_key: rawDescription.toUpperCase(),
    is_omitted: false,
  };
}

function buildReviewSessionPayload(
  profileName: "default" | "alternate",
  revision: number,
  records: ReturnType<typeof buildBaseReviewRecords>,
) {
  const optionSet = reviewOptionSets[profileName];
  return {
    review_session_id: "review-session-1",
    processing_run_id: "processing-run-1",
    current_revision: revision,
    session_revision: revision,
    blocking_issues: [],
    labor_classification_options: [...optionSet.labor],
    equipment_classification_options: [...optionSet.equipment],
    historical_export_status: {
      status_code: "reproducible",
      is_reproducible: true,
      detail: "Historical exports are reproducible from captured template artifact lineage.",
    },
    records,
  };
}

function applyReviewEdits(
  records: ReturnType<typeof buildBaseReviewRecords>,
  edits: Array<{ record_key: string; changed_fields: Record<string, unknown> }>,
) {
  return records.map((record, index) => {
    const edit = edits.find((candidate) => candidate.record_key === `record-${index}`);
    if (!edit) {
      return { ...record };
    }

    const nextRecord = { ...record };
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "vendor_name_normalized")) {
      (nextRecord as { vendor_name_normalized: string | null }).vendor_name_normalized =
        (edit.changed_fields.vendor_name_normalized as string | null) ?? null;
    }
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "recap_labor_classification")) {
      (nextRecord as { recap_labor_classification: string | null }).recap_labor_classification =
        (edit.changed_fields.recap_labor_classification as string | null) ?? null;
    }
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "equipment_category")) {
      (nextRecord as { equipment_category: string | null }).equipment_category =
        (edit.changed_fields.equipment_category as string | null) ?? null;
    }
    if (Object.prototype.hasOwnProperty.call(edit.changed_fields, "is_omitted")) {
      nextRecord.is_omitted = Boolean(edit.changed_fields.is_omitted);
    }
    return nextRecord;
  });
}

function installFetchMock(
  options: MockOptions & { initialReviewRecords?: ReturnType<typeof buildBaseReviewRecords> } = {},
) {
  const state = {
    currentRunProfileName: "default" as "default" | "alternate",
    currentRunSourceFilename: "report.pdf",
    currentReviewRevision: 0,
    currentReviewRecords: JSON.parse(
      JSON.stringify(options.initialReviewRecords ?? buildBaseReviewRecords("default")),
    ) as ReturnType<typeof buildBaseReviewRecords>,
    uploadCounter: 0,
    uploadFilenamesById: new Map<string, string>(),
    runAttemptsByUploadId: new Map<string, number>(),
  };

  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url === "/api/trusted-profiles" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(trustedProfilesPayload);
    }

    if (url === "/api/source-documents/uploads" && init?.method === "POST") {
      const formData = init.body as FormData;
      const uploadedFile = formData.get("file");
      const filename = uploadedFile instanceof File ? uploadedFile.name : `report-${state.uploadCounter + 1}.pdf`;
      const uploadId = `upload-${state.uploadCounter + 1}`;
      state.uploadCounter += 1;
      state.uploadFilenamesById.set(uploadId, filename);
      return jsonResponse(
        {
          upload_id: uploadId,
          original_filename: filename,
          content_type: "application/pdf",
          file_size_bytes: 1024,
          storage_ref: `runtime/uploads/${filename}`,
        },
        201,
      );
    }

    if (url === "/api/runs" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as { trusted_profile_name?: string; upload_id?: string };
      const uploadId = payload.upload_id ?? "";
      const priorAttemptCount = state.runAttemptsByUploadId.get(uploadId) ?? 0;
      const nextAttemptCount = priorAttemptCount + 1;
      state.runAttemptsByUploadId.set(uploadId, nextAttemptCount);

      if (options.expireCachedUploadOnSecondRun && nextAttemptCount === 2) {
        return jsonResponse(
          {
            detail: "The uploaded PDF expired from temporary storage. Reselect and upload the PDF again before processing.",
          },
          410,
        );
      }

      state.currentRunProfileName = payload.trusted_profile_name === "alternate" ? "alternate" : "default";
      state.currentRunSourceFilename = state.uploadFilenamesById.get(uploadId) ?? "report.pdf";
      state.currentReviewRevision = 0;
      state.currentReviewRecords = JSON.parse(
        JSON.stringify(options.initialReviewRecords ?? buildBaseReviewRecords(state.currentRunProfileName)),
      ) as ReturnType<typeof buildBaseReviewRecords>;
      return jsonResponse(
        buildRunPayload(state.currentRunProfileName, state.currentRunSourceFilename, state.currentReviewRecords.length),
        201,
      );
    }

    if (url === "/api/runs/processing-run-1" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(
        buildRunDetailPayload(
          state.currentRunProfileName,
          state.currentRunSourceFilename,
          state.currentReviewRecords,
        ),
      );
    }

    if (url === "/api/runs/processing-run-1/review-session" && (!init || !init.method || init.method === "GET")) {
      return jsonResponse(
        buildReviewSessionPayload(
          state.currentRunProfileName,
          state.currentReviewRevision,
          state.currentReviewRecords,
        ),
      );
    }

    if (url === "/api/runs/processing-run-1/review-session/edits" && init?.method === "POST") {
      const payload = JSON.parse(String(init.body ?? "{}")) as {
        edits: Array<{ record_key: string; changed_fields: Record<string, unknown> }>;
      };
      state.currentReviewRevision += 1;
      state.currentReviewRecords = applyReviewEdits(state.currentReviewRecords, payload.edits);
      return jsonResponse(
        buildReviewSessionPayload(
          state.currentRunProfileName,
          state.currentReviewRevision,
          state.currentReviewRecords,
        ),
      );
    }

    if (url === "/api/runs/processing-run-1/exports" && init?.method === "POST") {
      return jsonResponse(
        {
          export_artifact_id: "export-artifact-1",
          processing_run_id: "processing-run-1",
          review_session_id: "review-session-1",
          session_revision: state.currentReviewRevision,
          artifact_kind: "recap_workbook",
          template_artifact_id: "template-artifact-1",
          file_hash: "abc123",
          created_at: "2026-04-05T12:00:00Z",
          download_url: "/api/exports/export-artifact-1/download",
        },
        201,
      );
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
}

async function stageReports(user: ReturnType<typeof userEvent.setup>, filenames: string[]) {
  await user.upload(
    screen.getByLabelText(/^source report pdf$/i),
    filenames.map((filename) => new File(["sample"], filename, { type: "application/pdf" })),
  );
}

async function expandFamily(user: ReturnType<typeof userEvent.setup>, familyLabel: string) {
  const normalizedFamilyLabel = familyLabel.replace(/^(show|hide)\s+/i, "").trim();
  const toggle = screen.getByRole("button", {
    name: new RegExp(`(?:show|hide)\\s+${normalizedFamilyLabel}`, "i"),
  });
  if (toggle.getAttribute("aria-expanded") === "true") {
    return;
  }
  await user.click(toggle);
}

async function clickRowByText(user: ReturnType<typeof userEvent.setup>, text: string) {
  const row = screen.getByText(text).closest("tr");
  expect(row).not.toBeNull();
  await user.click(row!);
}

describe("App", () => {
  const originalCreateObjectUrl = URL.createObjectURL;
  const originalRevokeObjectUrl = URL.revokeObjectURL;

  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:download-url");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    URL.createObjectURL = originalCreateObjectUrl;
    URL.revokeObjectURL = originalRevokeObjectUrl;
  });

  it("stages multiple PDFs, keeps review grouped by family, and lets row selection drive the review sidebar", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Trusted profiles loaded.")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");
    await stageReports(user, ["report-a.pdf", "report-b.pdf"]);

    expect(screen.getByRole("button", { name: /report-a\.pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /report-b\.pdf/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /report-b\.pdf/i }));
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));

    expect(await screen.findByRole("heading", { name: "report-b.pdf" })).toBeInTheDocument();
    expect(screen.getByText("No current blockers.")).toBeInTheDocument();
    expect(screen.queryByText(/profile key/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export and download workbook/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /export and download workbook/i })).toBeEnabled();
    expect(screen.getByText(/select a row to inspect its source context and apply edits/i)).toBeInTheDocument();
    expect(screen.getAllByText("$500.00").length).toBeGreaterThan(0);
    expect(screen.queryByText("Concrete delivery")).not.toBeInTheDocument();

    await expandFamily(user, "Show Material");
    await clickRowByText(user, "Concrete delivery");

    expect(screen.getAllByText("Concrete Vendor").length).toBeGreaterThan(0);
    expect(screen.queryByText(/select a row to inspect its source context and apply edits/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Page 2/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Vendor name should be confirmed")).toBeInTheDocument();
    expect(screen.queryByText(/edit selected row/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply vendor name/i }));

    expect(await screen.findByText(/applied vendor name vendor edited to 1 selected row/i)).toBeInTheDocument();
    expect(screen.getAllByText("Vendor Edited").length).toBeGreaterThan(0);
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
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Vendor Edited");
    await user.click(screen.getByRole("button", { name: /apply vendor name/i }));
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

  it("invalidates export immediately when the selected trusted profile changes until processing is rerun", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await clickRowByText(user, "Concrete delivery");

    const exportButton = screen.getByRole("button", { name: /export and download workbook/i });
    expect(exportButton).toBeEnabled();

    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");

    expect(await screen.findByText(/review context is stale for export/i)).toBeInTheDocument();
    expect(screen.getByText(/must be reprocessed before export is allowed/i)).toBeInTheDocument();
    expect(exportButton).toBeDisabled();

    const fetchCallsBeforeRerun = vi.mocked(globalThis.fetch).mock.calls.length;
    await user.click(exportButton);
    expect(vi.mocked(globalThis.fetch).mock.calls).toHaveLength(fetchCallsBeforeRerun);

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByText("No current blockers.");
    expect(screen.queryByText(/review context is stale for export/i)).not.toBeInTheDocument();
    await expandFamily(user, "Show Material");
    await clickRowByText(user, "Concrete delivery");
    expect(screen.getByRole("button", { name: /export and download workbook/i })).toBeEnabled();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const runRequests = fetchCalls.filter(([url]) => url === "/api/runs");
    expect(runRequests).toHaveLength(2);
    expect(JSON.parse(String(runRequests[1]?.[1]?.body)).trusted_profile_name).toBe("alternate");
  });

  it("uses run-bound classification dropdowns in the top action bar instead of sidebar review inputs", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await user.click(screen.getByRole("checkbox", { name: /select labor line/i }));

    const laborSelect = screen.getByRole("combobox", { name: /bulk labor classification/i });
    expect(screen.queryByText(/edit selected row/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/recap labor class/i)).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "103 Journeyman" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "103 Foreman" })).toBeInTheDocument();

    await user.selectOptions(laborSelect, "103 Foreman");
    await user.click(screen.getByRole("button", { name: /apply labor class/i }));

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequest = fetchCalls.find(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequest).toBeDefined();
    expect(JSON.parse(String(editRequest?.[1]?.body)).edits[0].changed_fields.recap_labor_classification).toBe(
      "103 Foreman",
    );
  });

  it("loads profile-specific classification option sets from the active review run", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await user.selectOptions(screen.getByRole("combobox", { name: /trusted profile/i }), "alternate");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await user.click(screen.getByRole("checkbox", { name: /select labor line/i }));

    expect(screen.getByRole("option", { name: "ALT Journeyman" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "103 Journeyman" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "ALT Truck" })).toBeInTheDocument();
  });

  it("bulk applies one vendor name across selected vendor rows", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.type(screen.getByRole("textbox", { name: /bulk vendor name/i }), "Shared Vendor");
    await user.click(screen.getByRole("button", { name: /apply vendor name/i }));

    expect(await screen.findByText(/applied vendor name shared vendor to 2 selected rows/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests.length).toBeGreaterThan(0);
    const edits = JSON.parse(String(editRequests[editRequests.length - 1]?.[1]?.body)).edits;
    expect(edits).toHaveLength(2);
    expect(edits[0].changed_fields.vendor_name_normalized).toBe("Shared Vendor");
    expect(edits[1].changed_fields.vendor_name_normalized).toBe("Shared Vendor");
  });

  it("bulk applies one labor classification across selected labor rows", async () => {
    installFetchMock({
      initialReviewRecords: [
        ...buildBaseReviewRecords("default"),
        buildExtraLaborReviewRecord("default", "Helper labor line"),
      ],
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Labor");
    await user.click(screen.getByRole("checkbox", { name: /select labor line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select helper labor line/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /bulk labor classification/i }), "103 Foreman");
    await user.click(screen.getByRole("button", { name: /apply labor class/i }));

    expect(await screen.findByText(/applied labor classification 103 foreman to 2 selected rows/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests.length).toBeGreaterThan(0);
    const edits = JSON.parse(String(editRequests[editRequests.length - 1]?.[1]?.body)).edits;
    expect(edits).toHaveLength(2);
    expect(edits[0].changed_fields.recap_labor_classification).toBe("103 Foreman");
    expect(edits[1].changed_fields.recap_labor_classification).toBe("103 Foreman");
  });

  it("bulk applies one equipment category across selected equipment rows", async () => {
    installFetchMock({
      initialReviewRecords: [
        ...buildBaseReviewRecords("default"),
        buildExtraEquipmentReviewRecord("Truck 1"),
        buildExtraEquipmentReviewRecord("Truck 2"),
      ],
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Equipment");
    await user.click(screen.getByRole("checkbox", { name: /select truck 1/i }));
    await user.click(screen.getByRole("checkbox", { name: /select truck 2/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /bulk equipment category/i }), "Pick-up Truck");
    await user.click(screen.getByRole("button", { name: /apply equipment class/i }));

    expect(await screen.findByText(/applied equipment category pick-up truck to 2 selected rows/i)).toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests.length).toBeGreaterThan(0);
    const edits = JSON.parse(String(editRequests[editRequests.length - 1]?.[1]?.body)).edits;
    expect(edits).toHaveLength(2);
    expect(edits[0].changed_fields.equipment_category).toBe("Pick-up Truck");
    expect(edits[1].changed_fields.equipment_category).toBe("Pick-up Truck");
  });

  it("re-uploads a queued PDF automatically when the cached upload expires before rerun", async () => {
    installFetchMock({ expireCachedUploadOnSecondRun: true });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await user.click(screen.getByRole("button", { name: /process source pdf/i }));

    expect(
      await screen.findByText(/cached upload for report\.pdf expired from temporary storage/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const uploadRequests = fetchCalls.filter(([url]) => url === "/api/source-documents/uploads");
    const runRequests = fetchCalls.filter(([url]) => url === "/api/runs");
    expect(uploadRequests).toHaveLength(2);
    expect(runRequests).toHaveLength(3);
  });

  it("bulk omits and re-includes selected rows while keeping totals in sync", async () => {
    installFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Trusted profiles loaded.");
    await stageReports(user, ["report.pdf"]);
    await user.click(screen.getByRole("button", { name: /process source pdf/i }));
    await screen.findByRole("heading", { name: "report.pdf" });

    await expandFamily(user, "Show Material");
    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.click(screen.getByRole("button", { name: /bulk omit selected/i }));

    expect(await screen.findByText(/bulk omit change to 2 rows/i)).toBeInTheDocument();
    expect(screen.getAllByText("$160.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$340.00").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("checkbox", { name: /select material line/i }));
    await user.click(screen.getByRole("checkbox", { name: /select concrete delivery/i }));
    await user.click(screen.getByRole("button", { name: /bulk include selected/i }));

    expect(await screen.findByText(/bulk include change to 2 rows/i)).toBeInTheDocument();
    expect(screen.getAllByText("$500.00").length).toBeGreaterThan(0);

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    const editRequests = fetchCalls.filter(([url]) => url === "/api/runs/processing-run-1/review-session/edits");
    expect(editRequests).toHaveLength(2);
    expect(JSON.parse(String(editRequests[0]?.[1]?.body)).edits).toHaveLength(2);
    expect(JSON.parse(String(editRequests[1]?.[1]?.body)).edits).toHaveLength(2);
  });
});
