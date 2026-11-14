import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { ArrowLeft, Check, Info, Leaf } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState, ErrorState, LoadingBlocks } from "@/components/mirror/ClinicianStates";
import { TopNav } from "@/components/mirror/TopNav";
import { getPatientTrend, listPatients, listReviewFlags, markFlagReviewed } from "@/lib/api/client";
import {
  dailyReadings,
  dateTime,
  ESTIMATE_NOTE,
  relativeDay,
  retryUnlessRefused,
  sortFlags,
  type DayReading,
} from "@/lib/clinician";
import { hasRequiredRole } from "@/lib/role";

export const Route = createFileRoute("/clinician/$patientId")({
  beforeLoad: () => {
    if (!hasRequiredRole("clinician")) throw redirect({ to: "/" });
  },
  head: () => ({
    meta: [
      { title: "Patient dashboard — Mirror" },
      {
        name: "description",
        content: "Day-by-day estimates and the review queue for one patient.",
      },
    ],
  }),
  component: PatientDashboard,
});

export function PatientDashboard() {
  const { patientId } = Route.useParams();
  const queryClient = useQueryClient();

  const patients = useQuery({
    queryKey: ["clinician", "patients"],
    queryFn: listPatients,
    retry: retryUnlessRefused,
  });
  const trend = useQuery({
    queryKey: ["clinician", "trend", patientId],
    queryFn: () => getPatientTrend(patientId),
    retry: retryUnlessRefused,
  });
  const flags = useQuery({
    queryKey: ["clinician", "flags", patientId],
    queryFn: () => listReviewFlags(patientId),
    retry: retryUnlessRefused,
  });
  const review = useMutation({
    mutationFn: markFlagReviewed,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["clinician", "flags", patientId] }),
        queryClient.invalidateQueries({ queryKey: ["clinician", "patients"] }),
      ]),
  });

  const patient = patients.data?.find((p) => p.patient_id === patientId);
  const days = trend.data ? dailyReadings(trend.data) : [];
  const openFlags = flags.data?.filter((f) => f.reviewed_at === null).length ?? 0;
  const windows = trend.data?.length ?? 0;
  const steady = trend.data?.filter((p) => p.visual_status === "ok").length ?? 0;

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-6xl px-5 py-10">
        <Link
          to="/clinician"
          className="inline-flex items-center gap-1.5 text-sm text-muted-ink hover:text-body"
        >
          <ArrowLeft className="h-4 w-4" />
          All patients
        </Link>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {patient?.display_name ?? "Patient"}
          </h1>
          {openFlags > 0 && (
            <span className="rounded-full bg-lowmood px-3 py-1 text-xs font-medium text-safety">
              {openFlags} {openFlags === 1 ? "item needs" : "items need"} review
            </span>
          )}
        </div>

        <p className="mt-3 flex items-center gap-2 text-sm text-muted-ink">
          <Info className="h-4 w-4 shrink-0" />
          Everything below is a model estimate of expression or wording, never a feeling or a
          diagnosis. Each estimate shows how confident it is.
        </p>

        {(trend.isPending || flags.isPending) && <LoadingBlocks count={4} label="Loading" />}
        {(trend.isError || flags.isError) && (
          <ErrorState
            error={trend.error ?? flags.error}
            onRetry={() => {
              void trend.refetch();
              void flags.refetch();
            }}
          />
        )}

        {trend.data && flags.data && (
          <>
            <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Last session" value={relativeDay(patient?.last_session_at ?? null)} />
              <Stat label="Messages with a reading" value={String(windows)} />
              <Stat
                label="Steady camera readings"
                value={windows ? `${Math.round((100 * steady) / windows)}%` : "—"}
              />
              <Stat label="Open review items" value={String(openFlags)} />
            </div>

            <ReviewQueue
              flags={sortFlags(flags.data)}
              pendingId={review.isPending ? review.variables : undefined}
              failed={review.isError}
              onReview={(flagId) => review.mutate(flagId)}
            />

            {days.length === 0 ? (
              <EmptyState
                title="No sessions yet."
                detail="Estimates appear here after the patient's first chat session."
              />
            ) : (
              <>
                <WordingChart days={days} />
                <CameraByDay days={days} />
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <p className="text-[11px] uppercase tracking-wider text-muted-ink">{label}</p>
      <p className="mt-2 text-xl font-semibold text-ink">{value}</p>
    </div>
  );
}

function ReviewQueue({
  flags,
  pendingId,
  failed,
  onReview,
}: {
  flags: { flag_id: string; created_at: string; reviewed_at: string | null }[];
  pendingId: string | undefined;
  failed: boolean;
  onReview: (flagId: string) => void;
}) {
  return (
    <section className="mt-5 rounded-2xl border border-border bg-card p-6 shadow-soft">
      <h2 className="text-base font-medium">Review queue</h2>
      {flags.length === 0 ? (
        <p className="mt-3 text-sm text-muted-ink">Nothing to review.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {flags.map((flag) =>
            flag.reviewed_at === null ? (
              <li key={flag.flag_id} className="flex flex-wrap gap-3 rounded-xl bg-lowmood p-4">
                <Leaf className="mt-0.5 h-4 w-4 shrink-0 text-safety" />
                <p className="flex-1 text-sm leading-relaxed text-body">
                  <span className="font-medium text-safety">
                    Crisis resources were shown on {dateTime(flag.created_at)}.
                  </span>{" "}
                  A human check-in is recommended.
                </p>
                <button
                  type="button"
                  disabled={pendingId === flag.flag_id}
                  onClick={() => onReview(flag.flag_id)}
                  className="h-8 rounded-full border border-border bg-card px-3 text-xs font-medium text-ink hover:bg-secondary disabled:opacity-60"
                >
                  {pendingId === flag.flag_id ? "Saving…" : "Mark as reviewed"}
                </button>
              </li>
            ) : (
              <li
                key={flag.flag_id}
                className="flex gap-3 rounded-xl bg-secondary p-4 text-sm text-muted-ink"
              >
                <Check className="mt-0.5 h-4 w-4 shrink-0" />
                Crisis resources shown on {dateTime(flag.created_at)} · reviewed{" "}
                {dateTime(flag.reviewed_at)}
              </li>
            ),
          )}
        </ul>
      )}
      {failed && (
        <p role="alert" className="mt-3 text-sm text-safety">
          That didn't save. Please try again.
        </p>
      )}
    </section>
  );
}

function WordingChart({ days }: { days: DayReading[] }) {
  const data = days.map((d) => ({
    label: d.label,
    lighter: Math.round(d.lighterShare * 100),
    heavier: Math.round(d.heavierShare * 100),
    detail: `${d.textReadings} ${d.textReadings === 1 ? "message" : "messages"}, ${d.textConfidence}`,
  }));

  return (
    <section className="mt-5 rounded-2xl border border-border bg-card p-6 shadow-soft">
      <h2 className="text-base font-medium">How their messages read, day by day</h2>
      <p className="mt-1 text-xs text-muted-ink">
        Share of each day's messages whose wording the text model read as lighter or heavier.{" "}
        {ESTIMATE_NOTE} Days with fewer than 3 messages are low confidence.
      </p>
      <div className="mt-6 h-64" aria-label="Day-by-day wording estimate">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ left: -20, right: 8, top: 8 }}>
            <CartesianGrid stroke="#EDF0F5" vertical={false} />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "#8B97A6", fontSize: 12 }}
            />
            <YAxis
              domain={[0, 100]}
              unit="%"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "#8B97A6", fontSize: 12 }}
            />
            <RTooltip<number, string>
              formatter={(value, name) => [`${value}%`, `${name} wording`]}
              labelFormatter={(label, payload) =>
                `${String(label)}: ${(payload[0]?.payload as { detail?: string } | undefined)?.detail ?? ""}`
              }
              contentStyle={{
                borderRadius: 12,
                border: "1px solid #EDF0F5",
                fontSize: 12,
                color: "#4A5563",
              }}
            />
            <Bar dataKey="lighter" stackId="share" fill="#6DA588" radius={[0, 0, 4, 4]} />
            <Bar dataKey="heavier" stackId="share" fill="#CC8375" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-ink">
        {days.map((d) => (
          <li key={d.day}>
            {d.label}: {d.textReadings} {d.textReadings === 1 ? "message" : "messages"},{" "}
            {d.textConfidence}
          </li>
        ))}
      </ul>
    </section>
  );
}

function CameraByDay({ days }: { days: DayReading[] }) {
  return (
    <section className="mt-5 rounded-2xl border border-border bg-card p-6 shadow-soft">
      <h2 className="text-base font-medium">Camera estimate, day by day</h2>
      <p className="mt-1 text-xs text-muted-ink">
        The most common steady expression estimate. Mirror only uses a camera reading when it stays
        steady for 10 seconds. {ESTIMATE_NOTE}
      </p>
      <ul className="mt-2 divide-y divide-border">
        {[...days].reverse().map((d) => (
          <li key={d.day} className="flex items-center justify-between gap-3 py-3.5 text-sm">
            <span className="text-ink">{d.label}</span>
            <span className="text-right text-muted-ink">
              {d.cameraOff
                ? "Camera off"
                : d.faceEstimate
                  ? `${d.faceEstimate} · ${d.faceConfidence} · ${d.steadyFaceReadings} steady of ${d.windows}`
                  : `No steady reading (0 of ${d.windows})`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
