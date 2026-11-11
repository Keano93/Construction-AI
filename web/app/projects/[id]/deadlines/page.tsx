"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, DeadlineT } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CategoryBadge, DaysLeft, Empty, ErrorBox, StatusPill } from "@/components/ui";

export default function Deadlines() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<DeadlineT[] | null>(null);
  const [all, setAll] = useState(false);
  const [calc, setCalc] = useState({ trigger_date: new Date().toISOString().slice(0, 10), period: 10, unit: "working_days" });
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<DeadlineT[]>(`/projects/${id}/deadlines?include_closed=${all}`).then(setRows);
  }, [id, all]);

  async function runCalc(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setResult(await api(`/projects/${id}/deadline-calculator`, { method: "POST", json: calc }));
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-base font-semibold">Deadlines</h1>
          <p className="text-xs text-slate-500">Computed deterministically from the approved contract rules, Irish/UK public holidays, weekends and project shutdowns.</p>
        </div>
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> include met / cancelled</label>
      </div>
      <div className="card overflow-hidden">
        {rows === null ? <Empty>Loading…</Empty> : rows.length === 0 ? <Empty>No deadlines.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Due</th><th className="th">Remaining</th><th className="th">Status</th><th className="th">Event</th><th className="th">Obligation</th><th className="th">Calculation</th></tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} className={d.urgency === "overdue" ? "bg-rose-50/50" : ""}>
                  <td className="td whitespace-nowrap font-semibold tabular-nums">{fmtDate(d.due_date)}</td>
                  <td className="td whitespace-nowrap"><DaysLeft days={d.working_days_remaining} status={d.status} /></td>
                  <td className="td"><StatusPill status={d.urgency ?? d.status} /></td>
                  <td className="td">
                    <CategoryBadge category={d.event?.category ?? null} />{" "}
                    {d.review_item_id ? <Link className="text-sky-800 hover:underline" href={`/projects/${id}/inbox?item=${d.review_item_id}`}>{d.event?.ref} {d.event?.title}</Link> : <span>{d.event?.ref} {d.event?.title}</span>}
                  </td>
                  <td className="td">{d.label}{d.condition_precedent ? <div className="text-2xs font-semibold text-rose-700">condition precedent</div> : null}</td>
                  <td className="td text-2xs text-slate-500">{d.trace.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form onSubmit={runCalc} className="card space-y-2 p-3">
        <h2 className="text-xs font-semibold">Deadline calculator (this project&apos;s calendar)</h2>
        <div className="flex flex-wrap items-end gap-2">
          <label className="space-y-0.5"><span className="label">Trigger date</span><input type="date" className="input" value={calc.trigger_date} onChange={(e) => setCalc({ ...calc, trigger_date: e.target.value })} /></label>
          <label className="space-y-0.5"><span className="label">Period</span><input type="number" min={0} className="input w-20" value={calc.period} onChange={(e) => setCalc({ ...calc, period: Number(e.target.value) })} /></label>
          <label className="space-y-0.5"><span className="label">Unit</span>
            <select className="input" value={calc.unit} onChange={(e) => setCalc({ ...calc, unit: e.target.value })}>
              <option value="working_days">working days</option><option value="calendar_days">calendar days</option><option value="weeks">weeks</option><option value="months">months</option>
            </select></label>
          <button className="btn-primary">Calculate</button>
        </div>
        <ErrorBox error={error} />
        {result && (
          <div className="text-xs">
            <div>Due: <b>{fmtDate(result.due_date)}</b> — {result.explanation}</div>
            {result.skipped.length > 0 && <div className="text-2xs text-slate-500">Non-working days: {result.skipped.map((s: any) => `${fmtDate(s.date)} (${s.reason})`).join(", ")}</div>}
          </div>
        )}
      </form>
    </div>
  );
}
