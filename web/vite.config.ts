import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

import { resolveBackendOrigin } from "./src/runtimeConfig";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendOrigin = resolveBackendOrigin(env);

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: backendOrigin,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
    },
  };
});
