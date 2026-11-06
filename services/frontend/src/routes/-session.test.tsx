// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const {
  navigate,
  startSession,
  sendFrame,
  sendMessage,
  refreshAccessToken,
  accessTokenRefreshDelayMs,
  logout,
  captureJpeg,
} = vi.hoisted(() => ({
  navigate: vi.fn(),
  startSession: vi.fn(),
  sendFrame: vi.fn(),
  sendMessage: vi.fn(),
  refreshAccessToken: vi.fn(),
  accessTokenRefreshDelayMs: vi.fn<() => number | null>(() => null),
  logout: vi.fn(),
  captureJpeg: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: object) => ({ ...options, useSearch: () => ({ camera: true }) }),
  useNavigate: () => navigate,
}));
vi.mock("@/lib/api/client", () => ({
  startSession,
  sendFrame,
  sendMessage,
  logout,
  refreshAccessToken,
  accessTokenRefreshDelayMs,
}));
vi.mock("@/lib/camera", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/camera")>()),
  captureJpeg,
}));
vi.mock("@/lib/config", () => ({ API_BASE_URL: "http://gateway.test", USE_MOCK_API: false }));
vi.mock("@/components/mirror/TopNav", () => ({ TopNav: () => null }));
vi.mock("@/components/mirror/CrisisDialog", () => ({ CrisisDialog: () => null }));
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
  accessTokenRefreshDelayMs.mockReset();
  accessTokenRefreshDelayMs.mockReturnValue(null);
  refreshAccessToken.mockReset();
  sendMessage.mockReset();
  logout.mockReset();
  captureJpeg.mockReset();
  vi.useRealTimers();
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  value: vi.fn(),
  configurable: true,
});

const OK_ACK = {
  visual_status: "ok",
  top2: [
    ["happy", 0.8],
    ["neutral", 0.1],
  ],
};

function fakeStream() {
  const stop = vi.fn();
  return { stop, media: { getTracks: () => [{ stop }] } as unknown as MediaStream };
}

function stubCamera(getUserMedia: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia },
    configurable: true,
  });
}

/** Send one frame now, instead of waiting 1.5 seconds for the capture interval. */
async function sendOneFrame(intervals: { mock: { calls: unknown[][] } }) {
  const tick = intervals.mock.calls
    .filter(([, ms]) => ms === 1500)
    .at(-1)?.[0] as () => Promise<void>;
  await act(async () => {
    await tick();
  });
}

const preview = () => screen.getByLabelText("Your camera preview") as HTMLVideoElement;

function expectHonestTextOnlyState() {
  expect(screen.getByText(/Camera off · expression sensing is not used/)).toBeTruthy();
  expect(screen.queryByText("Predicted expression")).toBeNull();
  expect(screen.queryByText("Happy")).toBeNull();
  expect(screen.getByRole("button", { name: "Turn camera on" })).toBeTruthy();
  expect((screen.getByPlaceholderText("Type a message…") as HTMLInputElement).disabled).toBe(false);
}

describe("Session camera lifecycle", () => {
  it("starts a real session with the greeting and no demo messages", async () => {
    startSession.mockRejectedValue(new Error("/sessions failed with 503"));

    render(<Session />);

    expect(await screen.findByText(/glad you're here/i)).toBeTruthy();
    expect(screen.queryByText(/overwhelmed/i)).toBeNull();
  });

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

  it("redirects to login with 988 and 911 guidance when messages return 401", async () => {
    startSession.mockResolvedValue({ session_id: "s1" });
    sendMessage.mockRejectedValue(new Error("messages failed with 401"));

    render(<Session />);

    const input = await screen.findByPlaceholderText("Type a message…");
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: "/",
        search: {
          notice: "Your session expired. Call or text 988, or call 911 in an emergency.",
        },
      }),
    );
  });

  it("does not recursively renew immediately at the bounded one-minute token delay", async () => {
    vi.useFakeTimers();
    Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
    startSession.mockResolvedValue({ session_id: "s1" });
    accessTokenRefreshDelayMs.mockReturnValue(1_000);
    refreshAccessToken.mockResolvedValue({ access_token: "renewed" });

    render(<Session />);

    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(refreshAccessToken).toHaveBeenCalledTimes(1);
  });

  it("logs out, cleans up the camera, and shows 988 and 911 guidance when a frame upload returns 401", async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
      configurable: true,
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    startSession.mockResolvedValue({ session_id: "s1" });
    captureJpeg.mockResolvedValue(new Blob(["frame"], { type: "image/jpeg" }));
    sendFrame.mockRejectedValue(new Error("frames failed with 401"));

    render(<Session />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Turn camera off" })).toBeTruthy(),
    );
    await waitFor(
      () =>
        expect(
          screen.getByText("Camera frames are not being sent; messages remain text-only."),
        ).toBeTruthy(),
      { timeout: 2_500 },
    );
    expect(screen.getByRole("button", { name: "Turn camera on" })).toBeTruthy();
    expect(stop).toHaveBeenCalled();
    expect(logout).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith({
      to: "/",
      search: { notice: "Your session expired. Call or text 988, or call 911 in an emergency." },
    });
  });

  it("ends the session safely with crisis guidance when renewal fails without a 401", async () => {
    vi.useFakeTimers();
    Object.defineProperty(navigator, "mediaDevices", { value: undefined, configurable: true });
    startSession.mockResolvedValue({ session_id: "s1" });
    accessTokenRefreshDelayMs.mockReturnValue(1_000);
    refreshAccessToken.mockRejectedValue(new Error("/auth/refresh failed with 503"));

    render(<Session />);

    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(logout).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith({
      to: "/",
      search: {
        notice:
          "Your session ended because the service is unavailable. Call or text 988, or call 911 in an emergency.",
      },
    });
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

  it("stays text-only when permission is denied, and plays the stream after a retry", async () => {
    const stream = fakeStream();
    const denied = new DOMException("Permission denied", "NotAllowedError");
    const getUserMedia = vi.fn().mockRejectedValueOnce(denied).mockResolvedValueOnce(stream.media);
    stubCamera(getUserMedia);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    startSession.mockResolvedValue({ session_id: "s1" });

    render(<Session />);

    expect(await screen.findByText(/messages remain text-only/)).toBeTruthy();
    expectHonestTextOnlyState();
    expect(play).not.toHaveBeenCalled();
    expect(sendFrame).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Turn camera on" }));

    await screen.findByRole("button", { name: "Turn camera off" });
    expect(preview().srcObject).toBe(stream.media);
    expect(play).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/messages remain text-only/)).toBeNull();
  });

  it("clears a live reading when permission is denied on turning the camera back on", async () => {
    const stream = fakeStream();
    const denied = new DOMException("Permission denied", "NotAllowedError");
    stubCamera(vi.fn().mockResolvedValueOnce(stream.media).mockRejectedValueOnce(denied));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const intervals = vi.spyOn(globalThis, "setInterval");
    captureJpeg.mockResolvedValue(new Blob());
    sendFrame.mockResolvedValue(OK_ACK);
    startSession.mockResolvedValue({ session_id: "s1" });

    render(<Session />);
    await screen.findByRole("button", { name: "Turn camera off" });
    await sendOneFrame(intervals);
    expect(screen.getByText("Happy")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
    expect(stream.stop).toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Turn camera on" }));

    expect(await screen.findByText(/messages remain text-only/)).toBeTruthy();
    expectHonestTextOnlyState();
  });

  it("starts clean after a reload: old camera stopped, no old reading, new stream plays", async () => {
    const first = fakeStream();
    const second = fakeStream();
    stubCamera(vi.fn().mockResolvedValueOnce(first.media).mockResolvedValueOnce(second.media));
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const intervals = vi.spyOn(globalThis, "setInterval");
    captureJpeg.mockResolvedValue(new Blob());
    sendFrame.mockResolvedValue(OK_ACK);
    startSession.mockResolvedValue({ session_id: "s1" });

    const { unmount } = render(<Session />);
    await screen.findByRole("button", { name: "Turn camera off" });
    await sendOneFrame(intervals);
    expect(screen.getByText("Happy")).toBeTruthy();

    unmount();
    expect(first.stop).toHaveBeenCalled();

    render(<Session />);
    await screen.findByRole("button", { name: "Turn camera off" });

    expect(startSession).toHaveBeenCalledTimes(2);
    expect(preview().srcObject).toBe(second.media);
    expect(play).toHaveBeenCalledTimes(2);
    expect(screen.getByText("No reading yet.")).toBeTruthy();
    expect(screen.queryByText("Happy")).toBeNull();
  });

  it("stays text-only when permission is denied after a reload", async () => {
    const first = fakeStream();
    const denied = new DOMException("Permission denied", "NotAllowedError");
    stubCamera(vi.fn().mockResolvedValueOnce(first.media).mockRejectedValueOnce(denied));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const intervals = vi.spyOn(globalThis, "setInterval");
    captureJpeg.mockResolvedValue(new Blob());
    sendFrame.mockResolvedValue(OK_ACK);
    startSession.mockResolvedValue({ session_id: "s1" });

    const { unmount } = render(<Session />);
    await screen.findByRole("button", { name: "Turn camera off" });
    await sendOneFrame(intervals);
    unmount();

    render(<Session />);

    expect(await screen.findByText(/messages remain text-only/)).toBeTruthy();
    expectHonestTextOnlyState();
  });

  it("stops a camera that opens only after the patient has left the screen", async () => {
    const stream = fakeStream();
    let grant: (value: MediaStream) => void = () => {};
    stubCamera(
      vi.fn().mockReturnValue(
        new Promise<MediaStream>((resolve) => {
          grant = resolve;
        }),
      ),
    );
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    startSession.mockResolvedValue({ session_id: "s1" });

    const { unmount } = render(<Session />);
    await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled());
    unmount();
    await act(async () => {
      grant(stream.media);
    });

    expect(stream.stop).toHaveBeenCalled();
    expect(play).not.toHaveBeenCalled();
  });

  it("ignores a frame answer that arrives after the camera was turned off and on", async () => {
    const first = fakeStream();
    const second = fakeStream();
    stubCamera(vi.fn().mockResolvedValueOnce(first.media).mockResolvedValueOnce(second.media));
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const intervals = vi.spyOn(globalThis, "setInterval");
    captureJpeg.mockResolvedValue(new Blob());
    let answer: (value: typeof OK_ACK) => void = () => {};
    sendFrame.mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    startSession.mockResolvedValue({ session_id: "s1" });

    render(<Session />);
    await screen.findByRole("button", { name: "Turn camera off" });
    const inFlight = intervals.mock.calls
      .filter(([, ms]) => ms === 1500)
      .at(-1)?.[0] as () => Promise<void>;
    let frame: Promise<void> = Promise.resolve();
    await act(async () => {
      frame = inFlight();
    });
    await waitFor(() => expect(sendFrame).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
    fireEvent.click(await screen.findByRole("button", { name: "Turn camera on" }));
    await screen.findByRole("button", { name: "Turn camera off" });

    await act(async () => {
      answer(OK_ACK);
      await frame;
    });

    expect(screen.queryByText("Happy")).toBeNull();
    expect(screen.getByText("No reading yet.")).toBeTruthy();
  });

  it("does not show a reading from a reply sent while the camera was off", async () => {
    const first = fakeStream();
    const second = fakeStream();
    stubCamera(vi.fn().mockResolvedValueOnce(first.media).mockResolvedValueOnce(second.media));
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    sendMessage.mockImplementation(
      async (_id: string, _text: string, onEvent: (event: unknown) => void) => {
        onEvent({
          type: "done",
          data: { context: { visual: { status: "ok", top2: OK_ACK.top2 } } },
        });
      },
    );
    startSession.mockResolvedValue({ session_id: "s1" });

    render(<Session />);
    await screen.findByRole("button", { name: "Turn camera off" });
    fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
    await screen.findByRole("button", { name: "Turn camera on" });

    fireEvent.change(screen.getByPlaceholderText("Type a message…"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    expect(screen.queryByText("Happy")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Turn camera on" }));
    await screen.findByRole("button", { name: "Turn camera off" });

    expect(screen.queryByText("Happy")).toBeNull();
    expect(screen.getByText("No reading yet.")).toBeTruthy();
  });

  describe("reply that finishes late", () => {
    const SAD_CONTEXT = {
      type: "done",
      data: {
        context: {
          visual: {
            status: "ok",
            top2: [
              ["sad", 0.7],
              ["neutral", 0.1],
            ],
          },
        },
      },
    };

    /** Sends a message and leaves it unfinished until the test calls the returned function. */
    async function sendAndHold() {
      let onEvent: (event: unknown) => void = () => {};
      let finish: () => void = () => {};
      sendMessage.mockImplementation(
        (_id: string, _text: string, listener: (event: unknown) => void) => {
          onEvent = listener;
          return new Promise<void>((resolve) => {
            finish = resolve;
          });
        },
      );
      fireEvent.change(screen.getByPlaceholderText("Type a message…"), {
        target: { value: "hello" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Send message" }));
      await waitFor(() => expect(sendMessage).toHaveBeenCalled());
      return async () => {
        await act(async () => {
          onEvent(SAD_CONTEXT);
          finish();
        });
      };
    }

    function setUpCamera(getUserMedia: ReturnType<typeof vi.fn>) {
      stubCamera(getUserMedia);
      vi.spyOn(console, "warn").mockImplementation(() => {});
      vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
      captureJpeg.mockResolvedValue(new Blob());
      sendFrame.mockResolvedValue(OK_ACK);
      startSession.mockResolvedValue({ session_id: "s1" });
      return vi.spyOn(globalThis, "setInterval");
    }

    it("updates the panel when the camera run has not changed", async () => {
      const intervals = setUpCamera(vi.fn().mockResolvedValueOnce(fakeStream().media));

      render(<Session />);
      await screen.findByRole("button", { name: "Turn camera off" });
      await sendOneFrame(intervals);
      const finish = await sendAndHold();
      await finish();

      expect(screen.getByText("Sad")).toBeTruthy();
    });

    it("stays clear until the new run's reading after camera off, on, then a late reply", async () => {
      const intervals = setUpCamera(
        vi.fn().mockResolvedValueOnce(fakeStream().media).mockResolvedValueOnce(fakeStream().media),
      );

      render(<Session />);
      await screen.findByRole("button", { name: "Turn camera off" });
      await sendOneFrame(intervals);
      const finish = await sendAndHold();

      fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
      fireEvent.click(await screen.findByRole("button", { name: "Turn camera on" }));
      await screen.findByRole("button", { name: "Turn camera off" });
      await finish();

      expect(screen.queryByText("Sad")).toBeNull();
      expect(screen.getByText("No reading yet.")).toBeTruthy();

      await sendOneFrame(intervals);
      expect(screen.getByText("Happy")).toBeTruthy();
    });

    it("stays clear after a permission failure, a retry, then a late reply", async () => {
      const denied = new DOMException("Permission denied", "NotAllowedError");
      const intervals = setUpCamera(
        vi
          .fn()
          .mockResolvedValueOnce(fakeStream().media)
          .mockRejectedValueOnce(denied)
          .mockResolvedValueOnce(fakeStream().media),
      );

      render(<Session />);
      await screen.findByRole("button", { name: "Turn camera off" });
      await sendOneFrame(intervals);
      const finish = await sendAndHold();

      fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
      fireEvent.click(await screen.findByRole("button", { name: "Turn camera on" }));
      expect(await screen.findByText(/messages remain text-only/)).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Turn camera on" }));
      await screen.findByRole("button", { name: "Turn camera off" });
      await finish();

      expect(screen.queryByText("Sad")).toBeNull();
      expect(screen.getByText("No reading yet.")).toBeTruthy();

      await sendOneFrame(intervals);
      expect(screen.getByText("Happy")).toBeTruthy();
    });

    it("stays clear when a message is sent before the new run's first reading", async () => {
      const intervals = setUpCamera(
        vi.fn().mockResolvedValueOnce(fakeStream().media).mockResolvedValueOnce(fakeStream().media),
      );

      render(<Session />);
      await screen.findByRole("button", { name: "Turn camera off" });
      await sendOneFrame(intervals);
      fireEvent.click(screen.getByRole("button", { name: "Turn camera off" }));
      fireEvent.click(await screen.findByRole("button", { name: "Turn camera on" }));
      await screen.findByRole("button", { name: "Turn camera off" });

      const finish = await sendAndHold();
      await finish();

      expect(screen.queryByText("Sad")).toBeNull();
      expect(screen.getByText("No reading yet.")).toBeTruthy();
    });
  });
});
