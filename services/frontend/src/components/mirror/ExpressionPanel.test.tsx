// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ExpressionPanel } from "./ExpressionPanel";

afterEach(cleanup);

describe("ExpressionPanel", () => {
  it("without camera consent: explicit off state, no preview, no expression readings", () => {
    render(<ExpressionPanel cameraConsent={false} visual={null} />);
    expect(screen.getByText(/camera off/i)).toBeTruthy();
    expect(screen.queryByText(/expression sensing on/i)).toBeNull();
    expect(screen.queryByText(/predicted expression/i)).toBeNull();
  });

  it("before the first reply: no numbers yet", () => {
    render(<ExpressionPanel cameraConsent={true} visual={null} />);
    expect(screen.getByText(/no reading yet/i)).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("an ok reading shows the top two with the disclaimer", () => {
    const visual = {
      status: "ok" as const,
      top2: [
        ["sad", 0.46],
        ["neutral", 0.31],
      ] as [string, number][],
    };
    render(<ExpressionPanel cameraConsent={true} visual={visual} />);
    expect(screen.getByText("Sad")).toBeTruthy();
    expect(screen.getByText("46%")).toBeTruthy();
    expect(screen.getByText("31%")).toBeTruthy();
    expect(screen.getByText(/not a measure of how you truly feel/i)).toBeTruthy();
  });

  it.each(["uncertain", "dropped", "camera_off"] as const)(
    "a %s reading shows no labels or numbers",
    (status) => {
      const visual = {
        status,
        top2: [
          ["sad", 0.9],
          ["neutral", 0.05],
        ] as [string, number][],
      };
      render(<ExpressionPanel cameraConsent={true} visual={visual} />);
      expect(screen.queryByText("Sad")).toBeNull();
      expect(screen.queryByText(/%/)).toBeNull();
    },
  );

  it("an unknown label is not shown", () => {
    const visual = { status: "ok" as const, top2: [["contempt", 0.7]] as [string, number][] };
    render(<ExpressionPanel cameraConsent={true} visual={visual} />);
    expect(screen.queryByText(/contempt/i)).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});
