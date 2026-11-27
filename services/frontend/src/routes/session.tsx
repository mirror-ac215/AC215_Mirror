import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Send, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { CrisisDialog } from "@/components/mirror/CrisisDialog";
import { ExpressionPanel } from "@/components/mirror/ExpressionPanel";
import { TopNav } from "@/components/mirror/TopNav";
import { USE_MOCK_API } from "@/lib/config";
import { openingLine, seededChat } from "@/lib/mirror-data";
import * as api from "@/lib/api/client";
import type { ContextObject, CrisisPayload } from "@/lib/api/types";
import { fillEmptyReply, type ChatMessage } from "@/lib/chat";
import {
  attachCameraStream,
  captureJpeg,
  reportCameraCaptureFailure,
  stopCamera,
  visualFromFrameAck,
} from "@/lib/camera";
import { hasRequiredRole } from "@/lib/role";
import { MAX_MESSAGE_LENGTH, MESSAGE_NOT_SENT } from "@/lib/screen-states";

const EXPIRED_SESSION_NOTICE =
  "Your session expired. Call or text 988, or call 911 in an emergency.";
const UNAVAILABLE_SESSION_NOTICE =
  "Your session ended because the service is unavailable. Call or text 988, or call 911 in an emergency.";

export const Route = createFileRoute("/session")({
  beforeLoad: ({ search }) => {
    if (!hasRequiredRole("patient")) {
      throw redirect({
        to: "/",
        search: {
          notice: typeof search.notice === "string" ? search.notice : EXPIRED_SESSION_NOTICE,
        },
      });
    }
  },
  // The camera choice from /consent arrives as ?camera=true. Anything else, including
  // opening /session directly, means no camera: consent is never assumed.
  validateSearch: (search: Record<string, unknown>): { camera?: boolean; notice?: string } => ({
    ...(search["camera"] === true ? { camera: true } : {}),
    ...(typeof search["notice"] === "string" ? { notice: search["notice"] } : {}),
  }),
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

export function Session() {
  // Demo messages only in mock mode: a real session starts with the greeting alone.
  const [messages, setMessages] = useState<ChatMessage[]>(
    USE_MOCK_API ? seededChat : [{ from: "bot", text: openingLine }],
  );
  const [draft, setDraft] = useState("");
  const [crisis, setCrisis] = useState<CrisisPayload | null>(null);
  const [visual, setVisual] = useState<ContextObject["visual"] | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sessionFailed, setSessionFailed] = useState(false);
  const [sendFailed, setSendFailed] = useState(false);
  const [breakNote, setBreakNote] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0); // bump to retry starting the session
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraRequested, setCameraRequested] = useState(true);
  const [cameraIssue, setCameraIssue] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Each camera run gets a number, so a late reply can't show a reading from an earlier run.
  const cameraRunRef = useRef(0);
  const runWithReadingRef = useRef<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const terminateSession = useCallback(
    (notice: string) => {
      if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
      stopCamera(cameraStreamRef.current);
      cameraStreamRef.current = null;
      setCameraActive(false);
      setCameraRequested(false);
      setVisual(null);
      setSessionId(null);
      api.logout();
      navigate({ to: "/", search: { notice } });
    },
    [navigate],
  );

  // Start a session with the gateway (or the mock) when the screen opens.
  const cameraConsent = Route.useSearch().camera === true;
  useEffect(() => {
    setSessionFailed(false);
    api
      .startSession(cameraConsent)
      .then((s) => setSessionId(s.session_id))
      .catch((error) => {
        setSessionId(null);
        if (error instanceof Error && error.message.includes("401")) {
          terminateSession(EXPIRED_SESSION_NOTICE);
          return;
        }
        setSessionFailed(true);
      });
  }, [cameraConsent, attempt, terminateSession]);

  useEffect(() => {
    if (!sessionId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const scheduleRenewal = () => {
      const delay = api.accessTokenRefreshDelayMs();
      if (delay === null) return;
      timer = setTimeout(() => {
        void api
          .refreshAccessToken()
          .then(() => {
            if (!disposed) scheduleRenewal();
          })
          .catch((error) => {
            if (!disposed) {
              terminateSession(
                error instanceof Error && error.message.includes("401")
                  ? EXPIRED_SESSION_NOTICE
                  : UNAVAILABLE_SESSION_NOTICE,
              );
            }
          });
      }, delay);
    };
    scheduleRenewal();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId, terminateSession]);

  useEffect(() => {
    if (!cameraConsent || !sessionId || !cameraRequested) return;
    const run = ++cameraRunRef.current;
    setCameraIssue(null);
    setVisual(null); // a new camera run starts with no reading, whatever came before it
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraActive(false);
      setVisual(null);
      setCameraIssue("Camera frames are unavailable; messages remain text-only.");
      return;
    }
    let disposed = false;
    const stopWithIssue = (error: unknown) => {
      reportCameraCaptureFailure(error);
      if (!disposed) {
        cameraRunRef.current += 1;
        setCameraActive(false);
        setVisual(null);
        setCameraIssue("Camera frames are not being sent; messages remain text-only.");
        setCameraRequested(false);
      }
    };
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: false })
      .then(async (stream) => {
        if (disposed) {
          stopCamera(stream);
          return;
        }
        cameraStreamRef.current = stream;
        if (!videoRef.current) {
          stopCamera(stream);
          cameraStreamRef.current = null;
          return;
        }
        await attachCameraStream(videoRef.current, stream);
        if (disposed) {
          stopCamera(stream);
          return;
        }
        setCameraActive(true);
        captureIntervalRef.current = setInterval(async () => {
          if (!videoRef.current || !cameraStreamRef.current) return;
          try {
            const jpeg = await captureJpeg(videoRef.current);
            const ack = await api.sendFrame(sessionId, jpeg);
            // Camera turned off while this frame was on its way: keep the panel clear.
            if (!disposed && cameraStreamRef.current) {
              runWithReadingRef.current = run;
              setVisual(visualFromFrameAck(ack));
            }
          } catch (error) {
            stopWithIssue(error);
            if (error instanceof Error && error.message.includes("401")) {
              terminateSession(EXPIRED_SESSION_NOTICE);
            }
          }
        }, 1500);
      })
      .catch(stopWithIssue);
    return () => {
      disposed = true;
      cameraRunRef.current += 1;
      if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
      stopCamera(cameraStreamRef.current);
      cameraStreamRef.current = null;
      setCameraActive(false);
    };
  }, [cameraConsent, sessionId, cameraRequested, terminateSession]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !sessionId || sending) return;
    setDraft("");
    setSendFailed(false);
    setSending(true);
    // Until this run has its own reading, the gateway's answer may still reflect an earlier run.
    const readingRun =
      runWithReadingRef.current === cameraRunRef.current ? cameraRunRef.current : null;
    // Show the patient's message, plus an empty bot bubble that fills up as tokens arrive.
    setMessages((m) => [...m, { from: "user", text }, { from: "bot", text: "" }]);
    try {
      await api.sendMessage(sessionId, text, (event) => {
        if (event.type === "crisis") {
          setMessages((m) => m.slice(0, -1)); // no persona reply on a crisis turn
          setCrisis(event.data);
        } else if (event.type === "wellbeing") {
          setBreakNote(event.data.message);
        } else if (event.type === "done") {
          // The readout follows the gateway's reading for this turn, never a guess in the browser.
          if (readingRun === cameraRunRef.current) setVisual(event.data.context.visual);
        } else if (event.type === "token") {
          setMessages((m) => {
            const last = m[m.length - 1];
            if (!last) return m;
            return [...m.slice(0, -1), { ...last, text: last.text + event.data }];
          });
        }
      });
      setMessages(fillEmptyReply);
    } catch (error) {
      if (error instanceof Error && error.message.includes("401")) {
        terminateSession(EXPIRED_SESSION_NOTICE);
        return;
      }
      // Take back the unsent message and the empty reply, and give the text back to the
      // patient: the error is shown apart from the chat, never in Mirror's voice.
      setMessages((m) => m.slice(0, -2));
      setDraft(text);
      setSendFailed(true);
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
                    {m.from === "bot" && !m.text && sending && i === messages.length - 1 ? (
                      <span
                        role="status"
                        aria-label="Mirror is replying"
                        className="flex gap-1 py-1.5"
                      >
                        {[0, 150, 300].map((delay) => (
                          <span
                            key={delay}
                            className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-ink"
                            style={{ animationDelay: `${delay}ms` }}
                          />
                        ))}
                      </span>
                    ) : (
                      m.text
                    )}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>

            <div className="border-t border-border p-4">
              {!sessionId && !sessionFailed && (
                <p role="status" className="mb-2 text-sm text-muted-ink">
                  Starting your session…
                </p>
              )}
              {breakNote && (
                <p role="status" className="mb-2 text-sm text-muted-ink">
                  {breakNote}{" "}
                  <button onClick={() => setBreakNote(null)} className="underline">
                    Dismiss
                  </button>
                </p>
              )}
              {sendFailed && (
                <p role="alert" className="mb-2 text-sm text-safety">
                  {MESSAGE_NOT_SENT}{" "}
                  <button onClick={() => void send()} className="underline">
                    Try again
                  </button>
                </p>
              )}
              {sessionFailed && (
                <p role="alert" className="mb-2 text-sm text-safety">
                  Couldn&apos;t start your session.{" "}
                  <button onClick={() => setAttempt((a) => a + 1)} className="underline">
                    Try again
                  </button>
                </p>
              )}
              <div className="flex gap-2">
                <Input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  maxLength={MAX_MESSAGE_LENGTH}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder={sessionId ? "Type a message…" : "Connecting…"}
                  disabled={!sessionId}
                  className="h-11 rounded-[11px]"
                />
                <Button
                  onClick={send}
                  disabled={!sessionId || sending}
                  className="brand-gradient h-11 w-11 shrink-0 rounded-[11px] p-0 text-white hover:opacity-95"
                  aria-label="Send message"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </section>

          {/* side panel */}
          <div className="space-y-2">
            {cameraConsent && (
              <button
                type="button"
                onClick={() => {
                  if (cameraActive) {
                    setVisual(null);
                    setCameraIssue(null);
                  }
                  setCameraRequested((requested) => !requested);
                }}
                className="text-xs text-muted-ink underline"
              >
                {cameraActive ? "Turn camera off" : "Turn camera on"}
              </button>
            )}
            {cameraIssue && <p className="text-xs text-safety">{cameraIssue}</p>}
            <ExpressionPanel
              cameraConsent={cameraConsent && cameraActive}
              visual={visual}
              videoRef={videoRef}
            />
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-muted-ink">
          Prototype for demonstration · not medical advice · in crisis, call or text 988.
        </p>
      </main>

      <CrisisDialog crisis={crisis} onClose={() => setCrisis(null)} />
    </div>
  );
}
