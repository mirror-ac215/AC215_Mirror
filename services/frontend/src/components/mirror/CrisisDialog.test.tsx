// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CrisisPayload } from "@/lib/api/types";
import { CrisisDialog } from "./CrisisDialog";

const crisis: CrisisPayload = {
  message: "You don't have to face this alone.",
  resources: [
    { name: "988 Suicide & Crisis Lifeline", contact: "call or text 988" },
    { name: "Emergency services", contact: "call 911" },
  ],
  review_flag_created: true,
};

afterEach(cleanup);

describe("CrisisDialog", () => {
  it("is closed without a crisis event", () => {
    render(<CrisisDialog crisis={null} onClose={() => {}} />);
    expect(screen.queryByText(/988/)).toBeNull();
  });

  it("shows the gateway's message and every resource", () => {
    render(<CrisisDialog crisis={crisis} onClose={() => {}} />);
    expect(screen.getByText(crisis.message)).toBeTruthy();
    expect(screen.getByText("988 Suicide & Crisis Lifeline")).toBeTruthy();
    expect(screen.getByText(/call 911/)).toBeTruthy();
    expect(screen.getByText(/clinician has been gently notified/i)).toBeTruthy();
  });

  it("does not say the clinician was notified when no flag was created", () => {
    render(<CrisisDialog crisis={{ ...crisis, review_flag_created: false }} onClose={() => {}} />);
    expect(screen.queryByText(/clinician has been gently notified/i)).toBeNull();
  });
});
