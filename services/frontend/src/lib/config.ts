// Values are baked in at build time by Vite. Never put secrets here:
// everything in a VITE_ variable ends up in the user's browser.

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Default to mock mode until the api-gateway exists.
export const USE_MOCK_API: boolean = (import.meta.env.VITE_USE_MOCK_API ?? "true") === "true";
