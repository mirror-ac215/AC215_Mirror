import { Video, VideoOff } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import type { ContextObject } from "@/lib/api/types";

type Props = {
  cameraConsent: boolean;
  // visual part of the context object from the last reply's "done" event; null before the first reply
  visual: ContextObject["visual"] | null;
};

const LABELS: Record<string, string> = {
  angry: "Angry",
  disgust: "Disgusted",
  fear: "Afraid",
  happy: "Happy",
  neutral: "Neutral",
  sad: "Sad",
  surprise: "Surprised",
};

// Same bar as the prompt template: MIN_VISUAL_PROB in services/api-gateway/app/prompt.py (M3-08).
// Below it the reply does not mention the face, and the panel does not show numbers either.
const MIN_VISUAL_PROB = 0.4;

// What the patient sees when there is no trusted reading. No numbers in these states.
const UNCLEAR = "The reading is unclear right now, so it is not used.";
const NO_READING: Record<string, string> = {
  uncertain: UNCLEAR,
  dropped: "Your face wasn't in view long enough for a reading.",
  camera_off: "No camera reading for this message.",
};

/** Side panel of the session screen. Without camera consent it shows an explicit off state. */
export function ExpressionPanel({ cameraConsent, visual }: Props) {
  if (!cameraConsent) {
    return (
      <aside className="space-y-5">
        <div className="rounded-2xl border border-border bg-card p-3 shadow-soft">
          <div className="flex aspect-[4/3] items-center justify-center rounded-xl bg-neutral">
            <VideoOff className="h-6 w-6 text-muted-ink" />
          </div>
          <p className="mt-2.5 px-1 text-xs text-muted-ink">
            Camera off · expression sensing is not used in this session
          </p>
        </div>
        <p className="px-1 text-[11px] leading-relaxed text-muted-ink">
          Replies are based on your messages only. You can turn the camera on next time from the
          consent screen.
        </p>
      </aside>
    );
  }

  // Numbers only for an "ok" reading whose top label is known and at least MIN_VISUAL_PROB:
  // the same rule the prompt uses (M3-08), therefore the screen and the reply agree.
  const raw = visual?.status === "ok" ? (visual.top2 ?? []) : [];
  const first = raw[0];
  const trusted = first !== undefined && first[0] in LABELS && first[1] >= MIN_VISUAL_PROB;
  const top2 = trusted ? raw.filter(([l]) => l in LABELS) : [];

  return (
    <aside className="space-y-5">
      <div className="rounded-2xl border border-border bg-card p-3 shadow-soft">
        <div className="flex aspect-[4/3] items-center justify-center rounded-xl bg-neutral">
          <Video className="h-6 w-6 text-muted-ink" />
        </div>
        <p className="mt-2.5 px-1 text-xs text-muted-ink">Camera preview · expression sensing on</p>
      </div>

      <div className="rounded-2xl bg-reflective p-5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-ink">
          Predicted expression
        </p>
        {top2.length > 0 ? (
          <div className="mt-4 space-y-3.5">
            {top2.map(([label, prob]) => (
              <div key={label}>
                <div className="mb-1.5 flex justify-between text-xs text-body">
                  <span>{LABELS[label]}</span>
                  <span className="text-muted-ink">{Math.round(prob * 100)}%</span>
                </div>
                <Progress
                  value={prob * 100}
                  className="h-1.5 bg-card/70 [&>div]:bg-lavender [&>div]:transition-all [&>div]:duration-700"
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-xs text-body">
            {visual ? (NO_READING[visual.status] ?? UNCLEAR) : "No reading yet."}
          </p>
        )}
        <p className="mt-4 text-[11px] leading-relaxed text-muted-ink">
          An estimate of expression, not a measure of how you truly feel.
        </p>
      </div>
    </aside>
  );
}
