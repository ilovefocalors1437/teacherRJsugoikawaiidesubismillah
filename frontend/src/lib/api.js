// Backend base URL for every fetch()/image src that talks to the Flask
// backend. Empty string = same origin (frontend + backend on the same
// machine — the default, unchanged behavior). Set VITE_BACKEND_URL at
// BUILD time to point this frontend at a backend running on a different
// device — e.g. this frontend served from a Raspberry Pi while the
// Flask/YOLO backend (the heavy part) stays on the PC:
//   VITE_BACKEND_URL=http://<pc-lan-ip>:5000 npm run build
export const API_BASE = import.meta.env.VITE_BACKEND_URL || "";

export const apiUrl = (path) => `${API_BASE}${path}`;
