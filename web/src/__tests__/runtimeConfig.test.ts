import { describe, expect, it } from "vitest";

import { resolveApiBaseUrl, resolveBackendOrigin } from "../runtimeConfig";

describe("runtimeConfig", () => {
  it("uses conservative local defaults when env vars are absent", () => {
    expect(resolveApiBaseUrl({})).toBe("");
    expect(resolveBackendOrigin({})).toBe("http://127.0.0.1:8000");
  });

  it("normalizes configured URLs without trailing slashes", () => {
    expect(resolveApiBaseUrl({ VITE_API_BASE_URL: "http://localhost:8000/" })).toBe("http://localhost:8000");
    expect(resolveBackendOrigin({ VITE_BACKEND_ORIGIN: "http://localhost:9000/" })).toBe("http://localhost:9000");
  });
});
