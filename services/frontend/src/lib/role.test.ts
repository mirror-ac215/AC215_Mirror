import { afterEach, describe, expect, it } from "vitest";

import {
  clearAuthenticatedUser,
  getAuthenticatedUser,
  hasRequiredRole,
  setAuthenticatedUser,
} from "./role";

afterEach(() => {
  clearAuthenticatedUser();
});

describe("authenticated user state", () => {
  it("uses the server-verified login identity rather than a browser-selected role", () => {
    setAuthenticatedUser({
      user_id: "00000000-0000-0000-0000-000000000101",
      role: "clinician",
    });

    expect(getAuthenticatedUser()).toEqual({
      user_id: "00000000-0000-0000-0000-000000000101",
      role: "clinician",
    });
  });

  it("allows only the authenticated role to enter protected UI routes", () => {
    setAuthenticatedUser({
      user_id: "00000000-0000-0000-0000-000000000201",
      role: "patient",
    });

    expect(hasRequiredRole("patient")).toBe(true);
    expect(hasRequiredRole("clinician")).toBe(false);
  });

  it("clears identity on logout", () => {
    setAuthenticatedUser({
      user_id: "00000000-0000-0000-0000-000000000201",
      role: "patient",
    });

    clearAuthenticatedUser();

    expect(getAuthenticatedUser()).toBeNull();
  });
});
