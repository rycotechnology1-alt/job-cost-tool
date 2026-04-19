import test from "node:test";
import assert from "node:assert/strict";

import {
  InvalidStagedSourcePdfUploadPathError,
  MAX_STAGED_SOURCE_PDF_SIZE_BYTES,
  buildStagedSourcePdfTokenPolicy,
} from "./blob-upload-policy.mjs";

test("buildStagedSourcePdfTokenPolicy returns the staged PDF token policy for valid upload paths", () => {
  const policy = buildStagedSourcePdfTokenPolicy("uploads/550e8400-e29b-41d4-a716-446655440000/report.pdf");

  assert.deepEqual(policy, {
    allowedContentTypes: ["application/pdf"],
    maximumSizeInBytes: MAX_STAGED_SOURCE_PDF_SIZE_BYTES,
    addRandomSuffix: false,
  });
});

test("buildStagedSourcePdfTokenPolicy rejects paths outside the staged PDF namespace", () => {
  assert.throws(
    () => buildStagedSourcePdfTokenPolicy("exports/550e8400-e29b-41d4-a716-446655440000/report.pdf"),
    InvalidStagedSourcePdfUploadPathError,
  );
  assert.throws(
    () => buildStagedSourcePdfTokenPolicy("uploads/not-a-uuid/report.pdf"),
    InvalidStagedSourcePdfUploadPathError,
  );
  assert.throws(
    () => buildStagedSourcePdfTokenPolicy("uploads/550e8400-e29b-41d4-a716-446655440000/report.txt"),
    InvalidStagedSourcePdfUploadPathError,
  );
});
