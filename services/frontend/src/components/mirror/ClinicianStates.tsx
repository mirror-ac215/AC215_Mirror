import { Link } from "@tanstack/react-router";
import { AlertCircle } from "lucide-react";
import { ApiError } from "@/lib/api/client";

/** Grey placeholder blocks while a clinician call is in flight. */
export function LoadingBlocks({ count = 3, label }: { count?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="h-28 animate-pulse rounded-2xl border border-border bg-secondary" />
      ))}
    </div>
  );
}

/** Explains a failed call in plain words, with the right next step for each status. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = error instanceof ApiError ? error.status : null;
  const message =
    status === 401
      ? "Your login has expired."
      : status === 403
        ? "This page is only for the patient's own clinician."
        : "We couldn't load this right now.";

  return (
    <div
      role="alert"
      className="mt-7 flex items-start gap-3 rounded-2xl border border-border bg-card p-5 shadow-soft"
    >
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-safety" />
      <div>
        <p className="text-sm font-medium text-ink">{message}</p>
        {status === 401 ? (
          <Link to="/" className="mt-2 inline-block text-sm text-body underline">
            Log in again
          </Link>
        ) : (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 text-sm text-body underline hover:text-ink"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="mt-7 rounded-2xl border border-dashed border-border bg-card p-8 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 text-sm text-muted-ink">{detail}</p>
    </div>
  );
}
