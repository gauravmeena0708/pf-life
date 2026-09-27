/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// One browser origin: /auth and /api go through this server to the gateway, so the gateway's
// SameSite=Strict session cookie works and tokens never reach the browser (docs/architecture.md §5.2).
const gateway = process.env.VITE_GATEWAY_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: gateway, changeOrigin: false },
      "/auth": { target: gateway, changeOrigin: false },
    },
  },
  test: { environment: "jsdom", globals: true },
});
