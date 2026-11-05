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

  it("clears an old visual reading while camera is off and identifies the on-screen restart control", () => {
    render(
      <ExpressionPanel
        cameraConsent={false}
        visual={{ status: "ok", top2: [["happy", 0.9]] as [string, number][] }}
      />,
    );
    expect(screen.queryByText("Happy")).toBeNull();
    expect(
      screen.getByText(/turn the camera on above to restart expression sensing/i),
    ).toBeTruthy();
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

  it("an ok reading whose top label is below 0.40 shows no numbers, like the prompt", () => {
    const visual = {
      status: "ok" as const,
      top2: [
        ["sad", 0.39],
        ["neutral", 0.3],
      ] as [string, number][],
    };
    render(<ExpressionPanel cameraConsent={true} visual={visual} />);
    expect(screen.queryByText("Sad")).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
    expect(screen.getByText(/unclear/i)).toBeTruthy();
  });

  it("an ok reading at exactly 0.40 is shown", () => {
    const visual = {
      status: "ok" as const,
      top2: [
        ["happy", 0.4],
        ["neutral", 0.35],
      ] as [string, number][],
    };
    render(<ExpressionPanel cameraConsent={true} visual={visual} />);
    expect(screen.getByText("Happy")).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
  });
});
