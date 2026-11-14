// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listPatients: vi.fn(),
  getPatientTrend: vi.fn(),
  listReviewFlags: vi.fn(),
  markFlagReviewed: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: object) => ({
    ...options,
    useParams: () => ({ patientId: "p-bri" }),
  }),
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
  redirect: vi.fn(),
}));
vi.mock("@/lib/api/client", async () => {
  class ApiError extends Error {
    constructor(
      readonly path: string,
      readonly status: number,
    ) {
      super(`${path} failed with ${status}`);
    }
  }
  return { ...api, ApiError };
});
vi.mock("@/components/mirror/TopNav", () => ({ TopNav: () => null }));
// Recharts needs real layout; the chart's numbers are covered by lib/clinician.test.ts.
vi.mock("recharts", () => {
  const Stub = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    Bar: Stub,
    BarChart: Stub,
    CartesianGrid: Stub,
    ResponsiveContainer: Stub,
    Tooltip: Stub,
    XAxis: Stub,
    YAxis: Stub,
  };
});

import { ApiError } from "@/lib/api/client";
import { PatientDashboard } from "./clinician.$patientId";
import { PatientList } from "./clinician.index";

function renderWithQueries(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const bri = {
  patient_id: "p-bri",
  display_name: "Bri Santos",
  last_session_at: new Date().toISOString(),
  needs_review: true,
};

beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(cleanup);

describe("patient list", () => {
  it("shows a loading state, then each patient with the needs-review marker", async () => {
    api.listPatients.mockResolvedValue([
      bri,
      { ...bri, patient_id: "p-casey", display_name: "Casey Park", needs_review: false },
    ]);
    renderWithQueries(<PatientList />);
    expect(screen.getByRole("status", { name: /loading your patients/i })).toBeTruthy();

    expect(await screen.findByText("Bri Santos")).toBeTruthy();
    expect(screen.getByText("Casey Park")).toBeTruthy();
    expect(screen.getAllByText("needs review")).toHaveLength(1);
    expect(screen.getByText(/2 patients · 1 needs review/)).toBeTruthy();
  });

  it("shows an empty state when no patients are assigned", async () => {
    api.listPatients.mockResolvedValue([]);
    renderWithQueries(<PatientList />);
    expect(await screen.findByText(/no patients are assigned to you yet/i)).toBeTruthy();
  });

  it("asks to log in again when the token has expired", async () => {
    api.listPatients.mockRejectedValue(new ApiError("/clinician/patients", 401));
    renderWithQueries(<PatientList />);
    expect(await screen.findByText(/your login has expired/i)).toBeTruthy();
    expect(screen.getByText(/log in again/i)).toBeTruthy();
  });
});

describe("patient dashboard", () => {
  beforeEach(() => {
    api.listPatients.mockResolvedValue([bri]);
    api.getPatientTrend.mockResolvedValue([
      {
        ts: "2026-11-10T15:00:00",
        visual_status: "ok",
        visual_top2: [["angry", 0.62]],
        text_top2: [["sadness", 0.7]],
        tone_mode: "supportive",
      },
    ]);
    api.listReviewFlags.mockResolvedValue([
      { flag_id: "flag-1", created_at: "2026-11-11T14:30:00Z", reviewed_at: null },
    ]);
    api.markFlagReviewed.mockResolvedValue(undefined);
  });

  it("shows estimates in soft words with their confidence, never clinical labels", async () => {
    renderWithQueries(<PatientDashboard />);
    expect(await screen.findByText(/tense-looking · low confidence · 1 steady of 1/)).toBeTruthy();
    expect(screen.getAllByText(/an estimate, not a feeling/i).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/anxious|low mood|depress|angry/i);
  });

  it("marks an open flag as reviewed and reloads the queue", async () => {
    renderWithQueries(<PatientDashboard />);
    fireEvent.click(await screen.findByRole("button", { name: /mark as reviewed/i }));
    await waitFor(() => expect(api.markFlagReviewed).toHaveBeenCalled());
    expect(api.markFlagReviewed.mock.calls[0]![0]).toBe("flag-1");
    await waitFor(() => expect(api.listReviewFlags).toHaveBeenCalledTimes(2));
  });

  it("explains a 403 instead of showing another clinician's patient", async () => {
    api.getPatientTrend.mockRejectedValue(new ApiError("/clinician/patients/p-bri/trend", 403));
    renderWithQueries(<PatientDashboard />);
    expect(await screen.findByText(/only for the patient's own clinician/i)).toBeTruthy();
  });

  it("shows an empty state for a patient with no sessions", async () => {
    api.getPatientTrend.mockResolvedValue([]);
    api.listReviewFlags.mockResolvedValue([]);
    renderWithQueries(<PatientDashboard />);
    expect(await screen.findByText(/no sessions yet/i)).toBeTruthy();
    expect(screen.getByText(/nothing to review/i)).toBeTruthy();
  });
});
