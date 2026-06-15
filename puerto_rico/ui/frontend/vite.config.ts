import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server on 5173. Proxy REST (/games, /catalog) and the WebSocket (/ws) to
// the FastAPI backend on http://localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/games": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/catalog": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "http://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
