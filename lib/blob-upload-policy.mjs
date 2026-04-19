export const MAX_STAGED_SOURCE_PDF_SIZE_BYTES = 25 * 1024 * 1024;

const STAGED_SOURCE_PDF_PATHNAME_PATTERN =
  /^uploads\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/[^/]+\.pdf$/i;

export class InvalidStagedSourcePdfUploadPathError extends Error {
  constructor(pathname) {
    super(
      `Staged source PDF uploads must use the uploads/<uuid>/<filename>.pdf pathname format. Received '${String(pathname ?? "")}'.`,
    );
    this.name = "InvalidStagedSourcePdfUploadPathError";
  }
}

export function buildStagedSourcePdfTokenPolicy(pathname) {
  const normalizedPathname = String(pathname ?? "").trim();
  if (!STAGED_SOURCE_PDF_PATHNAME_PATTERN.test(normalizedPathname)) {
    throw new InvalidStagedSourcePdfUploadPathError(pathname);
  }

  return {
    allowedContentTypes: ["application/pdf"],
    // Cap staged source PDFs at 25 MiB so client-upload tokens stay bounded while still
    // accommodating reports that exceed serverless body limits.
    maximumSizeInBytes: MAX_STAGED_SOURCE_PDF_SIZE_BYTES,
    addRandomSuffix: false,
  };
}
