import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { TopNav } from "@/components/mirror/TopNav";
import { patients, toneClass, toneLabel } from "@/lib/mirror-data";
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
        content:
          "A calm overview of patient emotional trends and items that may need a gentle review.",
      },
      { property: "og:title", content: "Your patients — Mirror" },
      {
        property: "og:description",
        content:
          "A calm overview of patient emotional trends and items that may need a gentle review.",
      },
    ],
  }),
  component: PatientList,
});

function PatientList() {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto max-w-6xl px-5 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Your patients</h1>
        <p className="mt-1.5 text-sm text-muted-ink">Six active patients · 1 item needs review</p>

        <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {patients.map((p) => (
            <Link
              key={p.id}
              to="/clinician/$patientId"
              params={{ patientId: p.id }}
              className="rounded-2xl border border-border bg-card p-5 shadow-soft transition-shadow hover:shadow-lift"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-ink">{p.name}</p>
                  <p className="mt-0.5 text-xs text-muted-ink">{p.id}</p>
                </div>
                {p.needsReview && (
                  <span className="rounded-full bg-lowmood px-2.5 py-1 text-[11px] font-medium text-safety">
                    needs review
                  </span>
                )}
              </div>
              <div className="mt-5 flex items-center justify-between">
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-medium ${toneClass[p.tone]}`}
                >
                  {toneLabel[p.tone]}
                </span>
                <span className="text-xs text-muted-ink">{p.lastActive}</span>
              </div>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
