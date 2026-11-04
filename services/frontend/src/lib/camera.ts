export type CameraCaptureDependencies = {
  createImageBitmap: (source: ImageBitmapSource) => Promise<ImageBitmap>;
  createCanvas: () => HTMLCanvasElement;
  maxWidth: number;
};

function browserDependencies(): CameraCaptureDependencies {
  return {
    createImageBitmap: window.createImageBitmap.bind(window),
    createCanvas: () => document.createElement("canvas"),
    maxWidth: 320,
  };
}

/** Turn the current camera frame into a bounded JPEG without retaining it. */
export async function captureJpeg(
  source: ImageBitmapSource,
  dependencies?: CameraCaptureDependencies,
): Promise<Blob> {
  const runtime = dependencies ?? browserDependencies();
  const bitmap = await runtime.createImageBitmap(source);
  try {
    const scale = Math.min(1, runtime.maxWidth / bitmap.width);
    const canvas = runtime.createCanvas();
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Camera frame could not be drawn");
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("JPEG encoding failed"))),
        "image/jpeg",
        0.75,
      ),
    );
  } finally {
    bitmap.close();
  }
}

export function stopCamera(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}
