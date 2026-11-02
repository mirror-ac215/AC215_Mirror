// Values are baked in at build time by Vite. Never put secrets here:
// everything in a VITE_ variable ends up in the user's browser.

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Local source runs default to mock mode; the Docker build supplies false so
// the MS2 Compose stack exercises the real API-gateway boundary.
export const USE_MOCK_API: boolean = (import.meta.env.VITE_USE_MOCK_API ?? "true") === "true";
