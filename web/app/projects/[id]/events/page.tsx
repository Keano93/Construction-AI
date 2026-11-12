"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CategoryBadge, Empty, ErrorBox, StatusPill } from "@/components/ui";

type EventRow = {
  id: string; ref: string; category: string; title: string; description: string; trigger_date: string; status: string;
  related_item_ids: string[]; deadlines: { label: string; due_date: string; status: string }[];
};

export default function Events() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rows, setRows] = useState<EventRow[] | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<EventRow[]>(`/projects/${id}/events`).then(setRows);
  }, [id]);
  const shown = (rows ?? []).filter((r) => !filter || r.category === filter);
  const toggle = (eid: string) => setSelected((s) => { const n = new Set(s); n.has(eid) ? n.delete(eid) : n.add(eid); return n; });

  async function draftClaim() {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${id}/claims`, { method: "POST", json: { event_ids: Array.from(selected), title: title || null } });
      router.push(`/projects/${id}/claims`);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-base font-semibold">Event register</h1>
          <p className="text-xs text-slate-500">Potential changes, delays, instructions and disruption found in the project record. Select events to draft a claim.</p>
        </div>
        <select className="input w-44" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All categories</option><option>change</option><option>delay</option><option>instruction</option><option>disruption</option>
        </select>
      </div>
      {selected.size > 0 && (
        <div className="card flex flex-wrap items-center gap-2 border-sky-300 bg-sky-50 p-2 text-xs">
          <span className="font-semibold">{selected.size} event(s) selected</span>
          <input className="input w-80" placeholder="Claim title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <button className="btn-primary" disabled={busy} onClick={draftClaim}>{busy ? "Starting…" : "Draft claim"}</button>
          <button className="btn" onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}
      <ErrorBox error={error} />
      <div className="card overflow-hidden">
        {rows === null ? <Empty>Loading…</Empty> : shown.length === 0 ? <Empty>No events.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th w-6"></th><th className="th">Ref</th><th className="th">Aware</th><th className="th">Category</th><th className="th">Event</th><th className="th">Records</th><th className="th">Notice due</th><th className="th">Status</th></tr></thead>
            <tbody>
              {shown.map((e) => (
                <tr key={e.id} className={selected.has(e.id) ? "bg-sky-50" : ""}>
                  <td className="td"><input type="checkbox" checked={selected.has(e.id)} onChange={() => toggle(e.id)} aria-label={`select ${e.ref}`} /></td>
                  <td className="td font-semibold">{e.ref}</td>
                  <td className="td whitespace-nowrap">{fmtDate(e.trigger_date)}</td>
                  <td className="td"><CategoryBadge category={e.category} /></td>
                  <td className="td"><div className="font-medium">{e.title}</div><div className="line-clamp-2 text-2xs text-slate-500">{e.description}</div></td>
                  <td className="td text-center">{e.related_item_ids.length}</td>
                  <td className="td whitespace-nowrap text-2xs">{e.deadlines.map((d, i) => <div key={i}>{fmtDate(d.due_date)} · {d.label.split(" ").slice(0, 2).join(" ")} <span className="text-slate-400">{d.status}</span></div>)}</td>
                  <td className="td"><StatusPill status={e.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
