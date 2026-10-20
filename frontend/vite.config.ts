import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import pkg from "./package.json" with { type: "json" };

// The browser only talks to FastAPI. In development, Vite proxies /api and /health to the
// backend, so the app uses relative URLs and needs no database credentials.
const BACKEND = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": BACKEND,
      "/health": BACKEND,
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": BACKEND,
      "/health": BACKEND,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
