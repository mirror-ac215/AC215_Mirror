// The ONLY place the frontend talks to the backend. Screens import from here,
// never call fetch() themselves. Endpoints follow docs/contracts/api-gateway.openapi.yaml.

import { API_BASE_URL, USE_MOCK_API } from "@/lib/config";
import * as mock from "./mock";
import { createSseParser } from "./sse";
import type { ChatEvent, FrameAck, LoginResponse, Role, Session } from "./types";

let accessToken: string | null = null;

function authHeaders(): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed with ${res.status}`);
  return (await res.json()) as T;
}

export async function login(email: string, password: string, role: Role): Promise<LoginResponse> {
  const result = USE_MOCK_API
    ? await mock.login(role)
    : await postJson<LoginResponse>("/auth/login", { email, password });
  accessToken = result.access_token;
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
