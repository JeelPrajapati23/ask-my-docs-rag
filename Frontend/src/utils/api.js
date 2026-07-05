// Backend base URL. Set VITE_API_URL at build time for staging/production
// (e.g. VITE_API_URL=https://api.askmydocs.example); defaults to the local
// dev API for `npm run dev`.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
