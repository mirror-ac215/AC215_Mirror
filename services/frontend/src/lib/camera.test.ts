import { describe, expect, it, vi } from "vitest";
import {
  attachCameraStream,
  captureJpeg,
  reportCameraCaptureFailure,
  visualFromFrameAck,
} from "./camera";

describe("visualFromFrameAck", () => {
  it("keeps the smoothed reading when the gateway trusts it", () => {
    expect(visualFromFrameAck({ visual_status: "ok", top2: [["happy", 0.8]] })).toEqual({
      status: "ok",
      top2: [["happy", 0.8]],
    });
  });

  it("has no numbers when the gateway does not trust the reading", () => {
    expect(visualFromFrameAck({ visual_status: "uncertain" })).toEqual({ status: "uncertain" });
  });
});

describe("captureJpeg", () => {
  it("captures a downscaled JPEG and releases the source bitmap", async () => {
    let closed = false;
    const context = { drawImage: () => undefined } as unknown as CanvasRenderingContext2D;
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => context,
      toBlob: (callback: BlobCallback, type?: string) =>
        callback(new Blob(["jpeg"], { type: type ?? "" })),
    } as unknown as HTMLCanvasElement;
    const bitmap = {
      width: 1280,
      height: 720,
      close: () => (closed = true),
    } as unknown as ImageBitmap;

    const jpeg = await captureJpeg({} as ImageBitmapSource, {
      createImageBitmap: async () => bitmap,
      createCanvas: () => canvas,
      maxWidth: 320,
    });

    expect(jpeg.type).toBe("image/jpeg");
    expect(canvas.width).toBe(320);
    expect(canvas.height).toBe(180);
    expect(closed).toBe(true);
  });
});

describe("attachCameraStream", () => {
  it("assigns each stream and immediately starts playback for recovery after an off/on cycle", async () => {
    const assigned: MediaStream[] = [];
    const video = {
      set srcObject(stream: MediaStream | null) {
        if (stream) assigned.push(stream);
      },
      play: async () => undefined,
    } as unknown as HTMLVideoElement;
    const first = {} as MediaStream;
    const second = {} as MediaStream;
    const play = vi.spyOn(video, "play");

    await attachCameraStream(video, first);
    await attachCameraStream(video, second);

    expect(assigned).toEqual([first, second]);
    expect(play).toHaveBeenCalledTimes(2);
  });
});

describe("reportCameraCaptureFailure", () => {
  it("logs only a safe error type and never an error message", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = new Error("private camera or network details");

    reportCameraCaptureFailure(error);

    expect(warn).toHaveBeenCalledWith("camera_capture_failed", { error_type: "Error" });
    expect(JSON.stringify(warn.mock.calls)).not.toContain(error.message);
    warn.mockRestore();
  });
});
