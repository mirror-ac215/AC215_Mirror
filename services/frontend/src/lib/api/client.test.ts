import { afterEach, describe, expect, it, vi } from "vitest";

// Test the REAL gateway path, not the mock.
vi.mock("@/lib/config", () => ({ API_BASE_URL: "http://gateway.test", USE_MOCK_API: false }));

import * as api from "./client";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("api client (real mode)", () => {
  it("logs in, then sends the token and the patient's camera choice", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ access_token: "tok-alex", role: "patient", user_id: "u-201" }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          session_id: "s1",
          started_at: "2026-10-11T00:00:00Z",
          camera_consent: false,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await api.login("patient.alex@example.test", "pw", "patient");
    await api.startSession(false);

    const [loginUrl, loginInit] = fetchMock.mock.calls[0]!;
    expect(loginUrl).toBe("http://gateway.test/auth/login");
    expect(JSON.parse(loginInit.body)).toEqual({
      email: "patient.alex@example.test",
      password: "pw",
    });

    const [sessionUrl, sessionInit] = fetchMock.mock.calls[1]!;
    expect(sessionUrl).toBe("http://gateway.test/sessions");
    expect(sessionInit.headers.Authorization).toBe("Bearer tok-alex");
    expect(JSON.parse(sessionInit.body)).toEqual({ camera_consent: false });
  });

  it("throws on a failed login so the page can show an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    await expect(api.login("x@example.test", "wrong", "patient")).rejects.toThrow("401");
  });
});
