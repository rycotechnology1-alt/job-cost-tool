import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";
import {
  InvalidStagedSourcePdfUploadPathError,
  buildStagedSourcePdfTokenPolicy,
} from "./blob-upload-policy.mjs";

export default async function handler(request: Request): Promise<Response> {
  const body = (await request.json()) as HandleUploadBody;

  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => buildStagedSourcePdfTokenPolicy(pathname),
      onUploadCompleted: async () => {},
    });

    return Response.json(jsonResponse);
  } catch (error) {
    if (error instanceof InvalidStagedSourcePdfUploadPathError) {
      return Response.json({ error: error.message }, { status: 400 });
    }
    throw error;
  }
}
