import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import pkg from "./package.json" with { type: "json" };

// The browser only talks to FastAPI. In development, Vite proxies /api and /health to the
// backend, so the app uses relative URLs and needs no database credentials.
const BACKEND = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

// `xfwd` appends the real client address to X-Forwarded-For and `changeOrigin: false` keeps the
// browser's Host header, so the backend can refuse the local-only pipeline trigger for clients
// on other machines even though the proxy itself connects from 127.0.0.1 (D-39).
const proxyTarget = { target: BACKEND, xfwd: true, changeOrigin: false };
const proxy = { "/api": proxyTarget, "/health": proxyTarget };

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    host: "127.0.0.1", // loopback only unless started with --host
    port: 5173,
    proxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
