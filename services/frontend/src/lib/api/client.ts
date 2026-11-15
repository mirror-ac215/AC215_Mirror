// The ONLY place the frontend talks to the backend. Screens import from here,
// never call fetch() themselves. Endpoints follow docs/contracts/api-gateway.openapi.yaml.

import { API_BASE_URL, USE_MOCK_API } from "@/lib/config";
import * as mock from "./mock";
import { createSseParser } from "./sse";
import { clearAuthenticatedUser, setAuthenticatedUser } from "@/lib/role";
import type {
  ChatEvent,
  FrameAck,
  LoginResponse,
  PatientSummary,
  ReviewFlagSummary,
  Session,
  TrendPoint,
} from "./types";

let accessToken: string | null = null;

function authHeaders(): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

/** A failed API call. `status` lets screens tell "log in again" (401) from "not yours" (403). */
export class ApiError extends Error {
  constructor(
    readonly path: string,
    readonly status: number,
  ) {
    super(`${path} failed with ${status}`);
    this.name = "ApiError";
  }
}

async function requestJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers:
      body === undefined ? authHeaders() : { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? null : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(path, res.status);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>("POST", path, body);
}

/** Forget the current user's token (on logout, and before any new login attempt). */
export function logout(): void {
  accessToken = null;
  clearAuthenticatedUser();
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  logout(); // a failed login must never leave the previous user's identity active
  const result = USE_MOCK_API
    ? await mock.login(email)
    : await postJson<LoginResponse>("/auth/login", { email, password });
  accessToken = result.access_token;
  setAuthenticatedUser({ user_id: result.user_id, role: result.role });
  return result;
}

export function accessTokenRefreshDelayMs(): number | null {
  if (!accessToken) return null;
  try {
    const payload = accessToken.split(".")[1];
    if (!payload) return null;
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as {
      exp?: unknown;
      iat?: unknown;
    };
    if (typeof decoded.exp !== "number") return null;
    const tokenLifetimeMs =
      typeof decoded.iat === "number" ? Math.max(0, (decoded.exp - decoded.iat) * 1000) : 60_000;
    const renewalLeadMs = Math.min(60_000, Math.max(5_000, Math.floor(tokenLifetimeMs / 2)));
    return Math.max(1_000, decoded.exp * 1000 - Date.now() - renewalLeadMs);
  } catch {
    return null;
  }
}

export async function refreshAccessToken(): Promise<LoginResponse> {
  if (USE_MOCK_API) throw new Error("Token renewal is unavailable in mock mode");
  const result = await postJson<LoginResponse>("/auth/refresh", {});
  accessToken = result.access_token;
  setAuthenticatedUser({ user_id: result.user_id, role: result.role });
  return result;
}

export async function startSession(cameraConsent: boolean): Promise<Session> {
  if (USE_MOCK_API) return mock.startSession(cameraConsent);
  return postJson<Session>("/sessions", { camera_consent: cameraConsent });
}

export async function sendFrame(sessionId: string, jpeg: Blob): Promise<FrameAck> {
  if (USE_MOCK_API) return mock.sendFrame();
  const form = new FormData();
  form.append("image", jpeg, "frame.jpg");
  const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/frames`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(`frames failed with ${res.status}`);
  return (await res.json()) as FrameAck;
}

/**
 * Sends the patient's message and calls onEvent for each streamed event:
 * "crisis" (stop, show 988), "token" (next piece of text), "done" (finished).
 */
export async function sendMessage(
  sessionId: string,
  text: string,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  if (USE_MOCK_API) return mock.sendMessage(text, onEvent);

  const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text }),
  });
  if (!res.ok || !res.body) throw new Error(`messages failed with ${res.status}`);

  const parser = createSseParser(onEvent);
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.push(value);
  }
  parser.flush();
}

// --- Clinician dashboard (M4-01). The gateway only returns this clinician's own patients. ---

export async function listPatients(): Promise<PatientSummary[]> {
  if (USE_MOCK_API) return mock.listPatients();
  return requestJson<PatientSummary[]>("GET", "/clinician/patients");
}

export async function getPatientTrend(patientId: string): Promise<TrendPoint[]> {
  if (USE_MOCK_API) return mock.getPatientTrend(patientId);
  return requestJson<TrendPoint[]>(
    "GET",
    `/clinician/patients/${encodeURIComponent(patientId)}/trend`,
  );
}

export async function listReviewFlags(patientId: string): Promise<ReviewFlagSummary[]> {
  if (USE_MOCK_API) return mock.listReviewFlags(patientId);
  return requestJson<ReviewFlagSummary[]>(
    "GET",
    `/clinician/patients/${encodeURIComponent(patientId)}/review-flags`,
  );
}

export async function markFlagReviewed(flagId: string): Promise<void> {
  if (USE_MOCK_API) return mock.markFlagReviewed(flagId);
  await requestJson<{ reviewed: true }>(
    "PATCH",
    `/clinician/review-flags/${encodeURIComponent(flagId)}`,
    { reviewed: true },
  );
}
