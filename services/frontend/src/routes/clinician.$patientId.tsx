import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { ArrowLeft, Bell, Leaf } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TopNav } from "@/components/mirror/TopNav";
import { moodTrend, patients, recentSessions, toneClass, toneLabel } from "@/lib/mirror-data";
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
        content:
          "Mood trend across sessions, review queue and recent session tones for one patient.",
      },
      { property: "og:title", content: "Patient dashboard — Mirror" },
      {
        property: "og:description",
        content:
          "Mood trend across sessions, review queue and recent session tones for one patient.",
      },
    ],
  }),
  component: PatientDashboard,
});

function PatientDashboard() {
  const { patientId } = Route.useParams();

  const patient = patients.find((p) => p.id === patientId) ?? patients[1]!;

  const stats = [
    { label: "Avg. mood (valence)", value: patient.avgMood },
    { label: "Sessions this month", value: String(patient.sessionsThisMonth) },
    { label: "Engagement", value: patient.engagement },
    { label: "Open items", value: String(patient.openItems) },
  ];

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
          <h1 className="text-2xl font-semibold tracking-tight">{patient.name}</h1>
          <span className="text-sm text-muted-ink">{patient.id}</span>
          {patient.openItems > 0 && (
            <span className="rounded-full bg-lowmood px-3 py-1 text-xs font-medium text-safety">
              {patient.openItems} item needs review
            </span>
          )}
        </div>

        <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label} className="rounded-2xl border border-border bg-card p-5 shadow-soft">
              <p className="text-[11px] uppercase tracking-wider text-muted-ink">{s.label}</p>
              <p className="mt-2 text-xl font-semibold text-ink">{s.value}</p>
            </div>
          ))}
        </div>

        <section className="mt-5 rounded-2xl border border-border bg-card p-6 shadow-soft">
          <h2 className="text-base font-medium">Mood trend across sessions</h2>
          <p className="mt-1 text-xs text-muted-ink">
            Valence estimate, last 8 sessions · session 7 sits lowest
          </p>
          <div className="mt-6 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={moodTrend} margin={{ left: -20, right: 8, top: 8 }}>
                <CartesianGrid stroke="#EDF0F5" vertical={false} />
                <XAxis
                  dataKey="session"
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "#8B97A6", fontSize: 12 }}
                />
                <YAxis
                  domain={[0, 0.6]}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "#8B97A6", fontSize: 12 }}
                />
                <RTooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid #EDF0F5",
                    fontSize: 12,
                    color: "#4A5563",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="valence"
                  stroke="#6DA588"
                  strokeWidth={2.5}
                  dot={{ r: 3.5, fill: "#FFFFFF", stroke: "#6DA588", strokeWidth: 2 }}
                  activeDot={{ r: 6 }}
                />
                <ReferenceDot x="S7" y={0.11} r={6} fill="#CC8375" stroke="#CC8375" isFront />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <section className="rounded-2xl border border-border bg-card p-6 shadow-soft">
            <h2 className="text-base font-medium">Review queue</h2>
            <div className="mt-4 space-y-3">
              <div className="flex gap-3 rounded-xl bg-lowmood p-4">
                <Leaf className="mt-0.5 h-4 w-4 shrink-0 text-safety" />
                <p className="text-sm leading-relaxed text-body">
                  <span className="font-medium text-safety">Elevated distress — Session 7.</span>{" "}
                  Support resources were shared with the patient; a gentle human review is
                  recommended.
                </p>
              </div>
              <div className="flex gap-3 rounded-xl bg-anxious p-4">
                <Bell className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                <p className="text-sm leading-relaxed text-body">
                  <span className="font-medium text-ink">Engagement dip.</span> Two shorter sessions
                  this week. For context, no action required.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-border bg-card p-6 shadow-soft">
            <h2 className="text-base font-medium">Recent sessions</h2>
            <ul className="mt-2 divide-y divide-border">
              {recentSessions.map((s) => (
                <li key={s.date} className="flex items-center justify-between gap-3 py-3.5">
                  <div>
                    <p className="text-sm text-ink">{s.date}</p>
                    <p className="text-xs text-muted-ink">{s.length}</p>
                  </div>
                  <div className="flex gap-1.5">
                    {s.tones.map((t) => (
                      <span
                        key={t}
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${toneClass[t]}`}
                      >
                        {toneLabel[t]}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}
