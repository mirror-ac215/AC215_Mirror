import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import * as api from "@/lib/api/client";
import { USE_MOCK_API } from "@/lib/config";

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): { notice?: string } =>
    typeof search["notice"] === "string" ? { notice: search["notice"] } : {},
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
  const { notice } = Route.useSearch();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The gateway derives the role from verified credentials, never from the browser.
  const signIn = async () => {
    setError(null);
    setBusy(true);
    try {
      const result = await api.login(email, password);
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
              Continue
            </Button>
          </form>
          {notice && <p className="mt-4 text-sm text-safety">{notice}</p>}
        </div>

        <p className="mt-6 text-center text-xs text-muted-ink">
          Prototype for demonstration — not medical advice.
          {USE_MOCK_API && " In mock mode any credentials work."}
        </p>
      </div>
    </main>
  );
}
