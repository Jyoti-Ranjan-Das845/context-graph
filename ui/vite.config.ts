import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build goes into the Python package, so installing `cg` ships the web app with it.
// In development the API runs separately (`cg ui`); Vite proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  build: {
    outDir: "../backend/src/context_graph/web",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
});
