"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CategoryBadge, Empty, StatusPill } from "@/components/ui";

type EventRow = {
  id: string; ref: string; category: string; title: string; description: string; trigger_date: string; status: string;
  related_item_ids: string[]; deadlines: { label: string; due_date: string; status: string }[];
};

export default function Events() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<EventRow[] | null>(null);
  const [filter, setFilter] = useState("");
  useEffect(() => {
    api<EventRow[]>(`/projects/${id}/events`).then(setRows);
  }, [id]);
  const shown = (rows ?? []).filter((r) => !filter || r.category === filter);

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-base font-semibold">Event register</h1>
          <p className="text-xs text-slate-500">Potential changes, delays, instructions and disruption found in the project record.</p>
        </div>
        <select className="input w-44" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All categories</option><option>change</option><option>delay</option><option>instruction</option><option>disruption</option>
        </select>
      </div>
      <div className="card overflow-hidden">
        {rows === null ? <Empty>Loading…</Empty> : shown.length === 0 ? <Empty>No events.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Ref</th><th className="th">Aware</th><th className="th">Category</th><th className="th">Event</th><th className="th">Messages</th><th className="th">Notice due</th><th className="th">Status</th></tr></thead>
            <tbody>
              {shown.map((e) => (
                <tr key={e.id}>
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
