// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { login, navigate } = vi.hoisted(() => ({ login: vi.fn(), navigate: vi.fn() }));

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: object) => ({ ...options, useSearch: () => ({}) }),
  useNavigate: () => navigate,
}));
vi.mock("@/lib/api/client", () => ({ login }));
vi.mock("@/lib/config", () => ({ API_BASE_URL: "http://gateway.test", USE_MOCK_API: false }));

import { Route } from "./index";

const Login = (Route as unknown as { component: () => React.ReactElement }).component;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function submit() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button"));
}

describe("Sign-in screen states (M4-24)", () => {
  it("shows that it is signing in while the request is in flight", async () => {
    let resolve: (value: { role: string }) => void = () => {};
    login.mockReturnValue(new Promise((r) => (resolve = r)));

    render(<Login />);
    submit();

    const button = screen.getByRole("button") as HTMLButtonElement;
    expect(button.textContent).toBe("Signing in…");
    expect(button.disabled).toBe(true);
    await act(async () => resolve({ role: "patient" }));
    expect(navigate).toHaveBeenCalledWith({ to: "/consent" });
  });

  it("explains the lockout instead of blaming the password after too many attempts", async () => {
    login.mockRejectedValue(new Error("/auth/login failed with 429"));

    render(<Login />);
    submit();

    expect((await screen.findByRole("alert")).textContent).toMatch(/Too many attempts/);
  });

  it("says the server can't be reached when the network fails", async () => {
    login.mockRejectedValue(new TypeError("Failed to fetch"));

    render(<Login />);
    submit();

    expect((await screen.findByRole("alert")).textContent).toMatch(/can't reach Mirror/);
  });
});
