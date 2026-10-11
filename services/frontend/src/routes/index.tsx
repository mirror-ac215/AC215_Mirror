import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import * as api from "@/lib/api/client";
import { setRole, useRole, type Role } from "@/lib/role";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Sign in — Mirror" },
      {
        name: "description",
        content:
          "Mirror is a calm, emotion-aware mental-health companion for patients and their clinicians.",
      },
      { property: "og:title", content: "Sign in — Mirror" },
      {
        property: "og:description",
        content:
          "Mirror is a calm, emotion-aware mental-health companion for patients and their clinicians.",
      },
    ],
  }),
  component: Login,
});

function Login() {
  const role = useRole();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const choose = (r: Role) => setRole(r);
  // Log in through the API client: it stores the token that every later request sends.
  // In mock mode any credentials work; against the real gateway they must match a demo user.
  const signIn = async () => {
    setError(null);
    setBusy(true);
    try {
      const result = await api.login(email, password, role);
      setRole(result.role);
      navigate({ to: result.role === "patient" ? "/consent" : "/clinician" });
    } catch {
      setError("Wrong email or password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-16">
      <div className="w-full max-w-[420px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <span className="brand-gradient mb-4 h-11 w-11 rounded-[13px]" />
          <h1 className="font-serif text-3xl tracking-tight">Mirror</h1>
          <p className="mt-1.5 text-sm text-muted-ink">
            A gentle space to check in, between sessions.
          </p>
        </div>

        <div className="rounded-2xl border border-border bg-card p-6 shadow-soft">
          <div className="mb-5 grid grid-cols-2 gap-1 rounded-xl bg-secondary p-1">
            {(["patient", "clinician"] as Role[]).map((r) => (
              <button
                key={r}
                onClick={() => choose(r)}
                className={`rounded-[9px] py-2 text-sm font-medium capitalize ${
                  role === r ? "bg-card text-ink shadow-soft" : "text-muted-ink"
                }`}
              >
                {r}
              </button>
            ))}
          </div>

          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void signIn();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-xs text-muted-ink">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-11 rounded-[11px]"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-xs text-muted-ink">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-11 rounded-[11px]"
              />
            </div>
            {error && <p className="text-sm text-safety">{error}</p>}
            <Button
              type="submit"
              disabled={busy}
              className="brand-gradient h-11 w-full rounded-[11px] text-white shadow-soft hover:opacity-95"
            >
              Continue as {role}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-muted-ink">
          Prototype for demonstration — not medical advice. In mock mode any credentials work.
        </p>
      </div>
    </main>
  );
}
