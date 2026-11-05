// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { navigate, startSession, sendFrame } = vi.hoisted(() => ({
  navigate: vi.fn(),
  startSession: vi.fn(),
  sendFrame: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: object) => ({ ...options, useSearch: () => ({ camera: true }) }),
  useNavigate: () => navigate,
}));
vi.mock("@/lib/api/client", () => ({
  startSession,
  sendFrame,
  sendMessage: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("@/components/mirror/TopNav", () => ({ TopNav: () => null }));
vi.mock("@/components/mirror/CrisisDialog", () => ({ CrisisDialog: () => null }));
vi.mock("@/components/mirror/ExpressionPanel", () => ({ ExpressionPanel: () => null }));
vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { Session } from "./session";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  value: vi.fn(),
  configurable: true,
});

describe("Session camera lifecycle", () => {
  it("redirects to login with 988 and 911 guidance when session creation returns 401", async () => {
    startSession.mockRejectedValue(new Error("/sessions failed with 401"));

    render(<Session />);

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: "/",
        search: {
          notice: "Your session expired. Call or text 988, or call 911 in an emergency.",
        },
      }),
    );
  });

  it("plays a replacement stream after camera off then on", async () => {
    const first = { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
    const second = { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
    const getUserMedia = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia },
      configurable: true,
    });
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    startSession.mockResolvedValue({ session_id: "s1" });

    render(<Session />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Turn camera off" })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
    fireEvent.click(await screen.findByRole("button", { name: "Turn camera on" }));

    await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(2));
    expect(play).toHaveBeenCalledTimes(2);
  });
});
