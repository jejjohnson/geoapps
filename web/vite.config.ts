import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on :8000 and Vite proxies /api to it, so the
// browser sees one origin. In compose, GEOAPPS_API_PROXY points at the api service.
export default defineConfig({
  plugins: [react()],
  build: {
    // MapLibre is most of the bundle; keep it in its own long-cached chunk
    rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } },
    chunkSizeWarningLimit: 1000,
  },
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": process.env.GEOAPPS_API_PROXY ?? "http://localhost:8000" },
  },
});
