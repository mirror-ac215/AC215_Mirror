import { Video, VideoOff } from "lucide-react";
import { Progress } from "@/components/ui/progress";

type Props = {
  cameraConsent: boolean;
  expr: { calm: number; anxious: number; sad: number };
};

/** Side panel of the session screen. Without camera consent it shows an explicit off state. */
export function ExpressionPanel({ cameraConsent, expr }: Props) {
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
  );
}
