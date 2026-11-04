import { describe, expect, it } from "vitest";
import { captureJpeg } from "./camera";

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
