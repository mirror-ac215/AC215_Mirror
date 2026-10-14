import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Camera, Lock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { TopNav } from "@/components/mirror/TopNav";
import { setRole } from "@/lib/role";

export const Route = createFileRoute("/consent")({
  head: () => ({
    meta: [
      { title: "Before we begin — Mirror" },
      {
        name: "description",
        content:
          "Opt in to camera-based expression sensing before starting a Mirror check-in session.",
      },
      { property: "og:title", content: "Before we begin — Mirror" },
      {
        property: "og:description",
        content:
          "Opt in to camera-based expression sensing before starting a Mirror check-in session.",
      },
    ],
  }),
  component: Consent,
});

function Consent() {
  const navigate = useNavigate();
  const [camera, setCamera] = useState(true);

  useEffect(() => setRole("patient"), []);

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-2xl px-5 py-14">
        <h1 className="font-serif text-3xl tracking-tight">Before we begin</h1>
        <p className="mt-3 max-w-xl text-[15px] text-body">
          This session can use your camera to read your facial expression, so the companion can
          respond with a little more awareness of how you're feeling. It's entirely your choice.
        </p>

        <div className="mt-8 rounded-2xl border border-border bg-card p-6 shadow-soft">
          <div className="flex items-start justify-between gap-6">
            <div className="flex gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-reflective">
                <Camera className="h-4.5 w-4.5 text-lavender" />
              </span>
              <div>
                <p className="text-sm font-medium text-ink">Camera access</p>
                <p className="mt-1 text-sm text-muted-ink">
                  Used only during this session to estimate expression. Nothing is recorded.
                </p>
              </div>
            </div>
            <Switch checked={camera} onCheckedChange={setCamera} className="mt-1" />
          </div>

          <div className="mt-6 space-y-3 border-t border-border pt-6 text-sm text-muted-ink">
            <p className="flex gap-2.5">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-muted-ink" />
              Expression readings stay on this device and are summarised, never stored as video.
            </p>
            <p className="flex gap-2.5">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted-ink" />
              Your clinician sees emotional trends across sessions, not transcripts.
            </p>
          </div>

          <Button
            onClick={() => navigate({ to: "/session", search: { camera } })}
            className="brand-gradient mt-7 h-11 w-full rounded-[11px] text-white shadow-soft hover:opacity-95 sm:w-auto sm:px-8"
          >
            Start session
          </Button>
        </div>

        <p className="mt-6 text-xs text-muted-ink">
          Prototype for demonstration — not medical advice.
        </p>
      </main>
    </div>
  );
}
