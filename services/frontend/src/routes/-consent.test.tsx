// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: object) => options,
  redirect: vi.fn(),
  useNavigate: () => vi.fn(),
}));
vi.mock("@/components/mirror/TopNav", () => ({ TopNav: () => null }));

import { Route } from "./consent";

const Consent = (Route as unknown as { component: () => React.ReactElement }).component;

afterEach(cleanup);

// Patients consent based on this screen, so it must match what the app does (M4-28):
// frames go to the server and are not kept; expression readings are stored and the
// clinician sees trends from them; the clinician never sees the messages.
describe("Consent screen wording (M4-28)", () => {
  it("says frames go to the server, are not kept, and only readings are saved", () => {
    render(<Consent />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/No video is recorded\./);
    expect(text).toMatch(/Camera frames go to Mirror's server .* are not kept\./);
    expect(text).toMatch(/Only the readings are saved, never video or images\./);
    expect(screen.getByText(/emotional trends across sessions, not transcripts/)).toBeTruthy();
  });

  it("makes none of the earlier claims the app does not keep", () => {
    render(<Consent />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/Nothing is recorded/);
    expect(text).not.toMatch(/stay on this device/);
  });
});
