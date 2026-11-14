import { describe, expect, it } from "vitest";
import {
  LOGIN_TOO_MANY,
  LOGIN_UNREACHABLE,
  LOGIN_WRONG,
  loginErrorMessage,
  statusOf,
} from "./screen-states";

describe("statusOf", () => {
  it("reads the status from a failed API call", () => {
    expect(statusOf(new Error("/auth/login failed with 429"))).toBe(429);
  });

  it("is null for a network failure or a non-error", () => {
    expect(statusOf(new TypeError("Failed to fetch"))).toBeNull();
    expect(statusOf("nope")).toBeNull();
  });
});

describe("loginErrorMessage", () => {
  it("says wrong email or password only for a rejected login", () => {
    expect(loginErrorMessage(new Error("/auth/login failed with 401"))).toBe(LOGIN_WRONG);
    expect(loginErrorMessage(new Error("/auth/login failed with 422"))).toBe(LOGIN_WRONG);
  });

  it("explains the 5-minute lockout after too many attempts", () => {
    expect(loginErrorMessage(new Error("/auth/login failed with 429"))).toBe(LOGIN_TOO_MANY);
  });

  it("does not blame the password when the server is down or unreachable", () => {
    expect(loginErrorMessage(new Error("/auth/login failed with 503"))).toBe(LOGIN_UNREACHABLE);
    expect(loginErrorMessage(new TypeError("Failed to fetch"))).toBe(LOGIN_UNREACHABLE);
  });
});
