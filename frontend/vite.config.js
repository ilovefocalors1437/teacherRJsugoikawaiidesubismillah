import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// EVERY backend route the frontend calls must be listed here. If one is
// missing, `npm run dev` serves index.html for it instead, res.json() throws,
// and the UI shows a confusing "is the server running?" error — even though
// Flask is running fine. Keep this in sync with the routes in mentoscope_app.py.
const BACKEND = "http://127.0.0.1:5000";
const API_ROUTES = [
  "/activate",         // Practice — single-shot "Freeze"
  "/classify_upload",  // Clarify  — image upload
  "/stream_detect",    // Practice — live continuous detection (MJPEG)
  "/last_result",      // Practice — live findings poll
  "/camera_status",    // Practice — "awaiting endoscope" state
  "/camera_options",   // Practice — camera picker: available webcams + active source
  "/camera_source",    // Practice — camera picker: switch webcam/phone source
  "/video_feed",       // raw MJPEG preview
  "/static",           // sample images, last_activation_*.jpg
];

export default defineConfig({
  plugins: [react()],
  // base "./" keeps asset paths relative, so the built dist/ works from
  // Flask, `vite preview`, or even a double-clicked index.html.
  base: "./",
  server: {
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: BACKEND, changeOrigin: true }])
    ),
  },
});
