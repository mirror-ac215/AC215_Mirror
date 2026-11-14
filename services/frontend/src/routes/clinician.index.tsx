import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { EmptyState, ErrorState, LoadingBlocks } from "@/components/mirror/ClinicianStates";
import { TopNav } from "@/components/mirror/TopNav";
import { listPatients } from "@/lib/api/client";
import { relativeDay, retryUnlessRefused } from "@/lib/clinician";
import { hasRequiredRole } from "@/lib/role";

export const Route = createFileRoute("/clinician/")({
  beforeLoad: () => {
    if (!hasRequiredRole("clinician")) throw redirect({ to: "/" });
  },
  head: () => ({
    meta: [
      { title: "Your patients — Mirror" },
      {
        name: "description",
        content: "Your assigned patients, their last session and anything that needs a review.",
      },
    ],
  }),
  component: PatientList,
});

export function PatientList() {
  const patients = useQuery({
    queryKey: ["clinician", "patients"],
    queryFn: listPatients,
    retry: retryUnlessRefused,
  });
  const needsReview = patients.data?.filter((p) => p.needs_review).length ?? 0;

  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-6xl px-5 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Your patients</h1>
        {patients.data && patients.data.length > 0 && (
          <p className="mt-1.5 text-sm text-muted-ink">
            {patients.data.length} {patients.data.length === 1 ? "patient" : "patients"} ·{" "}
            {needsReview} {needsReview === 1 ? "needs" : "need"} review
          </p>
        )}

        {patients.isPending && <LoadingBlocks label="Loading your patients" />}
        {patients.isError && (
          <ErrorState error={patients.error} onRetry={() => void patients.refetch()} />
        )}
        {patients.data?.length === 0 && (
          <EmptyState
            title="No patients are assigned to you yet."
            detail="Patients appear here once they are assigned to you."
          />
        )}

        {patients.data && patients.data.length > 0 && (
          <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {patients.data.map((p) => (
              <Link
                key={p.patient_id}
                to="/clinician/$patientId"
                params={{ patientId: p.patient_id }}
                className="rounded-2xl border border-border bg-card p-5 shadow-soft transition-shadow hover:shadow-lift"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="font-medium text-ink">{p.display_name}</p>
                  {p.needs_review && (
                    <span className="rounded-full bg-lowmood px-2.5 py-1 text-[11px] font-medium text-safety">
                      needs review
                    </span>
                  )}
                </div>
                <p className="mt-5 text-xs text-muted-ink">
                  Last session: {relativeDay(p.last_session_at)}
                </p>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
