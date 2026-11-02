import { Heart, LifeBuoy } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { CrisisPayload } from "@/lib/api/types";

type Props = {
  // the "crisis" event from the gateway (M3-07); null keeps the dialog closed
  crisis: CrisisPayload | null;
  onClose: () => void;
};

/** Shown instead of a reply when the gateway's safety check fires. Text comes from the gateway. */
export function CrisisDialog({ crisis, onClose }: Props) {
  return (
    <Dialog open={crisis !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md rounded-2xl border-none bg-lowmood p-7 shadow-lift">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-card/70">
          <Heart className="h-4.5 w-4.5 text-safety" />
        </span>
        <DialogTitle className="mt-2 font-serif text-xl text-safety">
          You don't have to go through this alone
        </DialogTitle>
        <DialogDescription className="text-sm leading-relaxed text-body">
          {crisis?.message}
        </DialogDescription>
        <ul className="space-y-2">
          {crisis?.resources.map((r) => (
            <li
              key={r.name}
              className="flex items-center gap-2 rounded-[11px] bg-card/70 px-4 py-2.5 text-sm"
            >
              <LifeBuoy className="h-4 w-4 shrink-0 text-safety" />
              <span>
                <span className="font-medium text-body">{r.name}</span>
                <span className="text-muted-ink"> · {r.contact}</span>
              </span>
            </li>
          ))}
        </ul>
        {crisis?.review_flag_created && (
          <p className="text-xs leading-relaxed text-muted-ink">
            Your clinician has been gently notified so they can check in with you. You're not in any
            trouble.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
