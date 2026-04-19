import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

export default async function handler(request: Request): Promise<Response> {
  const body = (await request.json()) as HandleUploadBody;

  const jsonResponse = await handleUpload({
    body,
    request,
    onBeforeGenerateToken: async () => ({
      allowedContentTypes: ["application/pdf"],
      addRandomSuffix: false,
    }),
    onUploadCompleted: async () => {},
  });

  return Response.json(jsonResponse);
}
