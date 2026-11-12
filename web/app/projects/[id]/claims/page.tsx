"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Empty, StatusPill } from "@/components/ui";

type ClaimRow = { id: string; ref: string; title: string; status: string; event_ids: string[]; created_at: string; time_bar_risk: boolean; review_item_id: string | null };

export default function Claims() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<ClaimRow[] | null>(null);
  useEffect(() => {
    const load = () => api<ClaimRow[]>(`/projects/${id}/claims`).then(setRows);
    load();
    const t = setInterval(load, 5000); // claims are drafted in the background
    return () => clearInterval(t);
  }, [id]);

  return (
    <div className="space-y-3 p-4">
      <div>
        <h1 className="text-base font-semibold">Claims</h1>
        <p className="text-xs text-slate-500">
          Select events in the <Link className="text-sky-800 hover:underline" href={`/projects/${id}/events`}>event register</Link> and choose “Draft claim”. The Claims agent builds the evidence timeline, checks notice compliance and drafts the narrative for review.
        </p>
      </div>
      <div className="card overflow-hidden">
        {rows === null ? <Empty>Loading…</Empty> : rows.length === 0 ? <Empty>No claims yet.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Ref</th><th className="th">Claim</th><th className="th">Events</th><th className="th">Status</th><th className="th">Time-bar risk</th><th className="th">Created</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="td font-semibold">{c.ref}</td>
                  <td className="td">{c.review_item_id ? <Link className="font-medium text-sky-800 hover:underline" href={`/projects/${id}/inbox?item=${c.review_item_id}`}>{c.title}</Link> : c.title}</td>
                  <td className="td text-center">{c.event_ids.length}</td>
                  <td className="td"><StatusPill status={c.status === "drafting" ? "running" : c.status} />{c.status === "drafting" && <span className="ml-1 text-2xs text-slate-500">drafting…</span>}</td>
                  <td className="td">{c.time_bar_risk ? <span className="text-xs font-semibold text-rose-700">yes</span> : "—"}</td>
                  <td className="td whitespace-nowrap text-2xs">{fmtDateTime(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
