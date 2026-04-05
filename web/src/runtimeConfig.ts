export interface RuntimeEnv {
  [key: string]: string | boolean | undefined;
  VITE_API_BASE_URL?: string;
  VITE_BACKEND_ORIGIN?: string;
}

export function resolveApiBaseUrl(env: RuntimeEnv): string {
  return (env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
}

export function resolveBackendOrigin(env: RuntimeEnv): string {
  return (env.VITE_BACKEND_ORIGIN ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}
