import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Heart, LifeBuoy, Mic, Send, User, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TopNav } from "@/components/mirror/TopNav";
import { seededChat } from "@/lib/mirror-data";
import * as api from "@/lib/api/client";
import { setRole } from "@/lib/role";

export const Route = createFileRoute("/session")({
  // The camera choice from /consent arrives as ?camera=true. Anything else, including
  // opening /session directly, means no camera: consent is never assumed.
  validateSearch: (search: Record<string, unknown>): { camera?: boolean } =>
    search["camera"] === true ? { camera: true } : {},
  head: () => ({
    meta: [
      { title: "Your session — Mirror" },
      {
        name: "description",
        content:
          "A calm, emotion-aware chat companion that reflects back how your week has been feeling.",
      },
      { property: "og:title", content: "Your session — Mirror" },
      {
        property: "og:description",
        content:
          "A calm, emotion-aware chat companion that reflects back how your week has been feeling.",
      },
    ],
  }),
  component: Session,
});

type Msg = { from: "bot" | "user"; text: string };

function Session() {
  const [messages, setMessages] = useState<Msg[]>(seededChat);
  const [draft, setDraft] = useState("");
  const [crisis, setCrisis] = useState(false);
  const [expr, setExpr] = useState({ calm: 38, anxious: 44, sad: 18 });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => setRole("patient"), []);
  // Start a session with the gateway (or the mock) when the screen opens.
  const cameraConsent = Route.useSearch().camera === true;
  useEffect(() => {
    api
      .startSession(cameraConsent)
      .then((s) => setSessionId(s.session_id))
      .catch(() => setSessionId(null));
  }, [cameraConsent]);

  useEffect(() => {
    const t = setInterval(() => {
      setExpr((p) => {
        const jitter = () => Math.round((Math.random() - 0.5) * 8);
        const next = {
          calm: Math.min(80, Math.max(8, p.calm + jitter())),
          anxious: Math.min(80, Math.max(8, p.anxious + jitter())),
          sad: Math.min(80, Math.max(5, p.sad + jitter())),
        };
        return next;
      });
    }, 3200);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !sessionId || sending) return;
    setDraft("");
    setSending(true);
    // Show the patient's message, plus an empty bot bubble that fills up as tokens arrive.
    setMessages((m) => [...m, { from: "user", text }, { from: "bot", text: "" }]);
    try {
      await api.sendMessage(sessionId, text, (event) => {
        if (event.type === "crisis") {
          setMessages((m) => m.slice(0, -1)); // no persona reply on a crisis turn
          setCrisis(true);
        } else if (event.type === "token") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (!last) return m;
            return [...m.slice(0, -1), { ...last, text: last.text + event.data }];
          });
        }
      });
    } catch {
      setMessages((m) => [
        ...m.slice(0, -1),
        { from: "bot", text: "Sorry, I couldn't reach the server. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="min-h-screen">
      <TopNav />

      <main className="mx-auto max-w-6xl px-5 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-2xl tracking-tight">Today's check-in</h1>
            <p className="mt-1 text-sm text-muted-ink">
              Take your time. There's no right way to do this.
            </p>
          </div>
          <div className="flex items-center gap-5">
            {[
              { label: "Voice mode", icon: Mic },
              { label: "Avatar", icon: User },
            ].map(({ label, icon: Icon }) => (
              <Tooltip key={label}>
                <TooltipTrigger asChild>
                  <span className="flex cursor-not-allowed items-center gap-2 text-sm text-muted-ink opacity-70">
                    <Icon className="h-4 w-4" />
                    {label}
                    <Switch disabled />
                  </span>
                </TooltipTrigger>
                <TooltipContent>Coming soon</TooltipContent>
              </Tooltip>
            ))}
          </div>
        </div>

        <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_300px]">
          {/* chat */}
          <section className="flex h-[560px] flex-col rounded-2xl border border-border bg-card shadow-soft">
            <div className="flex-1 space-y-4 overflow-y-auto p-6">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={
                      m.from === "user"
                        ? "brand-gradient max-w-[78%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm text-white shadow-soft"
                        : `max-w-[78%] rounded-2xl rounded-bl-md border border-border bg-card px-4 py-2.5 text-body shadow-soft ${
                            i === 0 ? "font-serif text-[17px] leading-relaxed" : "text-sm"
                          }`
                    }
                  >
                    {m.text}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>

            <div className="border-t border-border p-4">
              <div className="flex gap-2">
                <Input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder="Type a message…"
                  className="h-11 rounded-[11px]"
                />
                <Button
                  onClick={send}
                  className="brand-gradient h-11 w-11 shrink-0 rounded-[11px] p-0 text-white hover:opacity-95"
                  aria-label="Send message"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
              <button
                onClick={() => setCrisis(true)}
                className="mt-3 text-xs text-muted-ink underline underline-offset-4 hover:text-body"
              >
                Simulate concerning message
              </button>
            </div>
          </section>

          {/* side panel */}
          <aside className="space-y-5">
            <div className="rounded-2xl border border-border bg-card p-3 shadow-soft">
              <div className="flex aspect-[4/3] items-center justify-center rounded-xl bg-neutral">
                <Video className="h-6 w-6 text-muted-ink" />
              </div>
              <p className="mt-2.5 px-1 text-xs text-muted-ink">
                Camera preview · expression sensing on
              </p>
            </div>

            <div className="rounded-2xl bg-reflective p-5">
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-ink">
                Predicted expression
              </p>
              <div className="mt-4 space-y-3.5">
                {(
                  [
                    ["Calm", expr.calm],
                    ["Anxious", expr.anxious],
                    ["Sad", expr.sad],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label}>
                    <div className="mb-1.5 flex justify-between text-xs text-body">
                      <span>{label}</span>
                      <span className="text-muted-ink">{value}%</span>
                    </div>
                    <Progress
                      value={value}
                      className="h-1.5 bg-card/70 [&>div]:bg-lavender [&>div]:transition-all [&>div]:duration-700"
                    />
                  </div>
                ))}
              </div>
              <p className="mt-4 text-[11px] leading-relaxed text-muted-ink">
                An estimate of expression, not a measure of how you truly feel.
              </p>
            </div>
          </aside>
        </div>

        <p className="mt-8 text-center text-xs text-muted-ink">
          Prototype for demonstration · not medical advice · in crisis, call or text 988.
        </p>
      </main>

      <Dialog open={crisis} onOpenChange={setCrisis}>
        <DialogContent className="max-w-md rounded-2xl border-none bg-lowmood p-7 shadow-lift">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-card/70">
            <Heart className="h-4.5 w-4.5 text-safety" />
          </span>
          <DialogTitle className="mt-2 font-serif text-xl text-safety">
            You don't have to go through this alone
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed text-body">
            If you're in crisis or thinking about harming yourself, support is available any time.
            You can call or text 988 (US) to reach the Suicide &amp; Crisis Lifeline.
          </DialogDescription>
          <Button className="mt-1 h-11 w-full rounded-[11px] bg-safety text-white hover:bg-safety/90 sm:w-auto sm:self-start sm:px-6">
            <LifeBuoy className="h-4 w-4" />
            Call or text 988
          </Button>
          <p className="text-xs leading-relaxed text-muted-ink">
            Your clinician has been gently notified so they can check in with you. You're not in any
            trouble.
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
