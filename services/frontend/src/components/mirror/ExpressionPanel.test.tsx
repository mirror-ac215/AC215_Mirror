// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ExpressionPanel } from "./ExpressionPanel";

const expr = { calm: 38, anxious: 44, sad: 18 };

afterEach(cleanup);

describe("ExpressionPanel", () => {
  it("without camera consent: explicit off state, no preview, no expression readings", () => {
    render(<ExpressionPanel cameraConsent={false} expr={expr} />);
    expect(screen.getByText(/camera off/i)).toBeTruthy();
    expect(screen.queryByText(/expression sensing on/i)).toBeNull();
    expect(screen.queryByText(/predicted expression/i)).toBeNull();
  });

  it("with camera consent: shows the preview and the readings", () => {
    render(<ExpressionPanel cameraConsent={true} expr={expr} />);
    expect(screen.getByText(/expression sensing on/i)).toBeTruthy();
    expect(screen.getByText(/predicted expression/i)).toBeTruthy();
  });
});
