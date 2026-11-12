"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { PanelSection, PanelTitle, RegisterLayout, RegisterTable, rowClass } from "@/components/register";
import { Empty, ErrorBox } from "@/components/ui";

type Ref = { id: string; filename: string };
type Comp = {
  id: string; summary: string; flags: string[]; created_at: string; review_item_id: string | null; base: Ref; revised: Ref;
  counts: { changes: number; potential_variations: number; raised: number };
  changes?: { id: string; label: string; raised: null | { mode: string; event_ref: string }; assessment: { potential_variation: boolean; cost_impact: string } }[];
};
type Candidate = { base: Ref; revised: Ref; kind: string; compared: boolean };
type Doc = { id: string; filename: string; kind: string };

const strip = (f: string) => f.replace(/\.[a-z]+$/i, "");

export default function Revisions() {
  const { id } = useParams<{ id: string }>();
  const [comps, setComps] = useState<Comp[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const load = useCallback(() => api<Comp[]>(`/projects/${id}/revisions`).then(setComps), [id]);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <RegisterLayout
      title="Revisions"
      description="New revisions of drawings, registers and specifications are compared with the previous one automatically. Changes are found by code; the Revision agent judges which may be variations."
      actions={<button className="btn" onClick={() => { setSelected(null); setComparing(true); }}>Compare two documents</button>}
      panel={selected ? <ComparisonPanel key={selected} compId={selected} projectId={id} /> : comparing ? <ComparePanel projectId={id} onQueued={() => setTimeout(load, 1500)} /> : undefined}
      onClose={() => { setSelected(null); setComparing(false); }}
    >
      {comps === null ? <Empty>Loading…</Empty> : comps.length === 0 ? <Empty>No comparisons yet. Upload a new revision under Documents.</Empty> : (
        <RegisterTable head={["Revision", "Possible variations", "Raised", "Compared"]}>
          {comps.map((c) => (
            <tr key={c.id} className={rowClass(selected === c.id)} onClick={() => { setComparing(false); setSelected(c.id); }}>
              <td className="td">{strip(c.revised.filename)}<div className="text-xs text-neutral-400">previous: {strip(c.base.filename)}{c.flags.length ? " · described as minor" : ""}</div></td>
              <td className="td w-40 tabular-nums">{c.counts.potential_variations} of {c.counts.changes}</td>
              <td className="td w-24 tabular-nums">{c.counts.raised}</td>
              <td className="td w-36 whitespace-nowrap text-neutral-600">{fmtDate(c.created_at)}</td>
            </tr>
          ))}
        </RegisterTable>
      )}
    </RegisterLayout>
  );
}

function ComparisonPanel({ compId, projectId }: { compId: string; projectId: string }) {
  const [c, setC] = useState<Comp | null>(null);
  useEffect(() => {
    api<Comp>(`/revisions/${compId}`).then(setC);
  }, [compId]);
  if (!c) return <p className="text-sm text-neutral-400">Loading…</p>;
  const pv = (c.changes ?? []).filter((x) => x.assessment.potential_variation);
  return (
    <>
      <PanelTitle kicker={`Drawing revision · previous: ${strip(c.base.filename)}`} title={strip(c.revised.filename)} />
      <PanelSection label="What changed">
        <p>{c.summary}</p>
        {c.flags.map((f, i) => <p key={i} className="mt-2 text-neutral-600">Note: {f}</p>)}
      </PanelSection>
      <PanelSection label={`Possible variations (${pv.length})`}>
        <ul className="space-y-1.5">
          {pv.map((x) => (
            <li key={x.id}>
              {x.label}
              <div className="text-[13px] text-neutral-500">
                likely cost {x.assessment.cost_impact} · {x.raised ? (x.raised.mode === "attached" ? `added to ${x.raised.event_ref}` : `raised as ${x.raised.event_ref}`) : "not raised yet"}
              </div>
            </li>
          ))}
        </ul>
        {c.review_item_id && <p className="mt-3"><Link className="link" href={`/projects/${projectId}/inbox?item=${c.review_item_id}`}>Review the changes and raise variations →</Link></p>}
      </PanelSection>
    </>
  );
}

function ComparePanel({ projectId, onQueued }: { projectId: string; onQueued: () => void }) {
  const [cands, setCands] = useState<Candidate[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [pick, setPick] = useState({ base: "", revised: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Candidate[]>(`/projects/${projectId}/revisions/candidates`).then(setCands);
    api<Doc[]>(`/projects/${projectId}/documents`).then((d) => setDocs(d.filter((x) => ["drawing_register", "spec", "drawing", "other"].includes(x.kind))));
  }, [projectId]);

  async function compare(base: string, revised: string) {
    setError(null);
    try {
      await api(`/projects/${projectId}/revisions`, { method: "POST", json: { base_document_id: base, revised_document_id: revised } });
      setMsg("Queued. The comparison will appear in the list and in the review queue.");
      onQueued();
    } catch (e: any) {
      setError(e.message);
    }
  }
  const pending = cands.filter((c) => !c.compared);
  return (
    <>
      <PanelTitle kicker="Tool" title="Compare two documents" />
      {pending.length > 0 && (
        <PanelSection label="Suggested">
          {pending.map((c) => (
            <div key={c.revised.id} className="flex items-center justify-between gap-2 py-1">
              <span>{strip(c.base.filename)} → {strip(c.revised.filename)}</span>
              <button className="btn" onClick={() => compare(c.base.id, c.revised.id)}>Compare</button>
            </div>
          ))}
        </PanelSection>
      )}
      <PanelSection label="Choose documents">
        <div className="space-y-2.5">
          <label className="block space-y-1"><span className="label">Previous revision</span>
            <select className="input" value={pick.base} onChange={(e) => setPick({ ...pick, base: e.target.value })}><option value="">Select…</option>{docs.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select></label>
          <label className="block space-y-1"><span className="label">Revised</span>
            <select className="input" value={pick.revised} onChange={(e) => setPick({ ...pick, revised: e.target.value })}><option value="">Select…</option>{docs.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}</select></label>
          <button className="btn-primary" disabled={!pick.base || !pick.revised || pick.base === pick.revised} onClick={() => compare(pick.base, pick.revised)}>Compare</button>
          {msg && <p className="text-[13px] text-neutral-600">{msg}</p>}
          <ErrorBox error={error} />
        </div>
      </PanelSection>
    </>
  );
}
