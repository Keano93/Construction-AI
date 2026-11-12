"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Empty, ErrorBox } from "@/components/ui";

type Comp = {
  id: string; summary: string; flags: string[]; created_at: string; method: string; review_item_id: string | null;
  base: { id: string; filename: string }; revised: { id: string; filename: string };
  counts: { changes: number; potential_variations: number; raised: number };
};
type Candidate = { base: { id: string; filename: string }; revised: { id: string; filename: string }; kind: string; compared: boolean };
type Doc = { id: string; filename: string; kind: string };

export default function Revisions() {
  const { id } = useParams<{ id: string }>();
  const [comps, setComps] = useState<Comp[] | null>(null);
  const [cands, setCands] = useState<Candidate[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [pick, setPick] = useState({ base: "", revised: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Comp[]>(`/projects/${id}/revisions`).then(setComps);
    api<Candidate[]>(`/projects/${id}/revisions/candidates`).then(setCands);
  }, [id]);
  useEffect(() => {
    load();
    api<Doc[]>(`/projects/${id}/documents`).then((d) => setDocs(d.filter((x) => ["drawing_register", "spec", "drawing", "other"].includes(x.kind))));
  }, [id, load]);

  async function compare(base: string, revised: string) {
    setError(null);
    setMsg(null);
    try {
      await api(`/projects/${id}/revisions`, { method: "POST", json: { base_document_id: base, revised_document_id: revised } });
      setMsg("Comparison queued — the Revision agent will add it below and to the review queue.");
      setTimeout(load, 1500);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const pending = cands.filter((c) => !c.compared);
  return (
    <div className="space-y-4 p-4">
      <div>
        <h1 className="text-base font-semibold">Revisions</h1>
        <p className="text-xs text-slate-500">New revisions of drawing registers, specifications and drawings are compared with the previous revision automatically. Changes are found by code; the Revision agent assesses scope, cost and time impact and you decide what to raise.</p>
      </div>
      <ErrorBox error={error} />
      {msg && <div className="rounded border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-800">{msg}</div>}

      <section className="card overflow-hidden">
        <h2 className="border-b border-slate-100 px-3 py-2 text-xs font-semibold">Comparisons</h2>
        {comps === null ? <Empty>Loading…</Empty> : comps.length === 0 ? <Empty>No comparisons yet. Upload a new revision under Documents, or compare two documents below.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Previous → revised</th><th className="th">Changes</th><th className="th">Potential variations</th><th className="th">Raised / attached</th><th className="th">Summary</th><th className="th">When</th></tr></thead>
            <tbody>
              {comps.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="td">
                    {c.review_item_id ? <Link className="font-medium text-sky-800 hover:underline" href={`/projects/${id}/inbox?item=${c.review_item_id}`}>{c.base.filename} → {c.revised.filename}</Link> : `${c.base.filename} → ${c.revised.filename}`}
                    {c.flags.length > 0 && <div className="text-2xs font-semibold text-amber-700">understated revision</div>}
                  </td>
                  <td className="td text-center tabular-nums">{c.counts.changes}</td>
                  <td className="td text-center tabular-nums font-semibold">{c.counts.potential_variations}</td>
                  <td className="td text-center tabular-nums">{c.counts.raised}</td>
                  <td className="td max-w-md text-2xs text-slate-600">{c.summary}</td>
                  <td className="td whitespace-nowrap text-2xs">{fmtDateTime(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {pending.length > 0 && (
        <section className="card p-3">
          <h2 className="mb-2 text-xs font-semibold">Suggested pairs not yet compared</h2>
          {pending.map((c) => (
            <div key={c.revised.id} className="flex items-center justify-between border-t border-slate-100 py-1.5 text-xs first:border-0">
              <span>{c.base.filename} → {c.revised.filename} <span className="text-slate-400">({c.kind})</span></span>
              <button className="btn" onClick={() => compare(c.base.id, c.revised.id)}>Compare</button>
            </div>
          ))}
        </section>
      )}

      <section className="card flex flex-wrap items-end gap-2 p-3">
        <label className="space-y-0.5"><span className="label">Previous revision</span>
          <select className="input w-72" value={pick.base} onChange={(e) => setPick({ ...pick, base: e.target.value })}>
            <option value="">Select…</option>{docs.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
          </select></label>
        <label className="space-y-0.5"><span className="label">Revised</span>
          <select className="input w-72" value={pick.revised} onChange={(e) => setPick({ ...pick, revised: e.target.value })}>
            <option value="">Select…</option>{docs.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
          </select></label>
        <button className="btn-primary" disabled={!pick.base || !pick.revised || pick.base === pick.revised} onClick={() => compare(pick.base, pick.revised)}>Compare</button>
      </section>
    </div>
  );
}
