"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Empty } from "@/components/ui";

type Row = { id: number; actor_type: string; actor_name: string; action: string; entity_type: string | null; entity_id: string | null; source_refs: any[]; details: any; hash: string; created_at: string };

export default function Audit() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [verify, setVerify] = useState<{ ok: boolean; first_bad_id: number | null } | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api<Row[]>(`/projects/${id}/audit?limit=1000`).then(setRows);
    api("/audit/verify").then(setVerify);
  }, [id]);
  const shown = (rows ?? []).filter((r) => !q || `${r.action} ${r.actor_name} ${r.entity_type}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-base font-semibold">Audit log</h1>
          <p className="text-xs text-neutral-500">Append-only and hash-chained. Every upload, agent run, approval, edit and export is recorded with its sources.</p>
        </div>
        {verify && (
          <span className={`rounded px-2 py-1 text-2xs font-semibold ${verify.ok ? "bg-neutral-100 text-neutral-600" : "bg-transparent text-red-600"}`}>
            {verify.ok ? "Hash chain verified" : `Chain broken at entry ${verify.first_bad_id}`}
          </span>
        )}
      </div>
      <input className="input w-72" placeholder="Filter (e.g. review.approve, agent)" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="card overflow-hidden">
        {rows === null ? <Empty>Loading…</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">When</th><th className="th">Who</th><th className="th">Action</th><th className="th">Entity</th><th className="th">Details</th><th className="th">Hash</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="td whitespace-nowrap">{fmtDateTime(r.created_at)}</td>
                  <td className="td"><span className="text-2xs text-neutral-400">{r.actor_type}</span> {r.actor_name}</td>
                  <td className="td font-medium">{r.action}</td>
                  <td className="td text-2xs">{r.entity_type} <span className="font-mono text-neutral-400">{r.entity_id?.slice(0, 8)}</span></td>
                  <td className="td max-w-md truncate font-mono text-2xs text-neutral-500" title={JSON.stringify(r.details)}>{JSON.stringify(r.details)}</td>
                  <td className="td font-mono text-2xs text-neutral-400">{r.hash.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
