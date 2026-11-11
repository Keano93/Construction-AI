"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, DeadlineT } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CategoryBadge, DaysLeft, Empty } from "@/components/ui";
import { useProject } from "@/components/project-context";

type Agent = { name: string; title: string; pillar: string; description: string; status: string };

function Stat({ label, value, href, tone }: { label: string; value: number | undefined; href?: string; tone?: string }) {
  const body = (
    <div className="card px-3 py-2 hover:border-slate-300">
      <div className="label">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${tone ?? ""}`}>{value ?? "–"}</div>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function Overview() {
  const { project } = useProject();
  const [deadlines, setDeadlines] = useState<DeadlineT[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  useEffect(() => {
    if (!project) return;
    api<DeadlineT[]>(`/projects/${project.id}/deadlines`).then(setDeadlines);
    api<Agent[]>("/agents").then(setAgents);
  }, [project]);
  if (!project) return <Empty>Loading…</Empty>;
  const s = project.stats;
  const base = `/projects/${project.id}`;
  const pillars: Record<string, string> = { protect_the_money: "Protect the money", get_paid: "Get paid", win_the_work: "Win the work", core: "Core" };

  return (
    <div className="space-y-4 p-5">
      <div>
        <h1 className="text-base font-semibold">{project.name}</h1>
        <p className="text-xs text-slate-500">{project.location} · holidays: {project.holiday_region} · shutdowns: {project.shutdowns.map((x) => `${x.name} ${fmtDate(x.start)}–${fmtDate(x.end)}`).join("; ") || "none"}</p>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        <Stat label="To review" value={s.review_pending} href={`${base}/inbox`} />
        <Stat label="Low confidence" value={s.review_low_confidence} href={`${base}/inbox?low=1`} tone={s.review_low_confidence ? "text-amber-700" : ""} />
        <Stat label="Deadlines overdue" value={s.deadlines_overdue} href={`${base}/deadlines`} tone={s.deadlines_overdue ? "text-rose-700" : ""} />
        <Stat label="Due ≤ 5 WD" value={s.deadlines_due_5wd} href={`${base}/deadlines`} tone={s.deadlines_due_5wd ? "text-orange-700" : ""} />
        <Stat label="Open events" value={s.events_open} href={`${base}/events`} />
        <Stat label="Rules to approve" value={s.rules_proposed} href={`${base}/contract`} />
      </div>
      {s.jobs_queued > 0 && <div className="rounded border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-800">{s.jobs_queued} documents/messages still being processed by agents…</div>}

      <section className="card">
        <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
          <h2 className="text-xs font-semibold">Next notice deadlines</h2>
          <Link className="text-2xs text-sky-700 hover:underline" href={`${base}/deadlines`}>all deadlines</Link>
        </div>
        {deadlines.length === 0 ? <Empty>No running deadlines.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Due</th><th className="th">Remaining</th><th className="th">Event</th><th className="th">Obligation</th></tr></thead>
            <tbody>
              {deadlines.slice(0, 8).map((d) => (
                <tr key={d.id}>
                  <td className="td whitespace-nowrap font-medium tabular-nums">{fmtDate(d.due_date)}</td>
                  <td className="td whitespace-nowrap"><DaysLeft days={d.working_days_remaining} /></td>
                  <td className="td"><CategoryBadge category={d.event?.category ?? null} /> <span className="text-slate-500">{d.event?.ref}</span> {d.event?.title}</td>
                  <td className="td">{d.label}{d.condition_precedent ? <span className="ml-1 text-2xs font-semibold text-rose-700">condition precedent</span> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2 className="border-b border-slate-100 px-3 py-2 text-xs font-semibold">Agents</h2>
        <div className="grid gap-px bg-slate-100 md:grid-cols-4">
          {agents.map((a) => (
            <div key={a.name} className="bg-white p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold">{a.title}</span>
                <span className={`text-2xs font-semibold ${a.status === "live" ? "text-emerald-700" : "text-slate-400"}`}>{a.status === "live" ? "live" : "planned"}</span>
              </div>
              <div className="text-2xs text-slate-400">{pillars[a.pillar]}</div>
              <p className="mt-1 text-2xs leading-snug text-slate-600">{a.description}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
