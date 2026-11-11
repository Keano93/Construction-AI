"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, RuleT } from "@/lib/api";
import { period } from "@/lib/format";
import { Confidence, Empty, ErrorBox, StatusPill } from "@/components/ui";
import { SourcePassage } from "@/components/SourcePassage";
import { useProject } from "@/components/project-context";

type Contract = { id: string; document_id: string; title: string; form: string | null; status: string; rules: RuleT[]; clauses: { ref: string; title: string }[] };
const CATS = ["change", "delay", "instruction", "disruption"];
const TYPES = ["notice", "time_bar", "payment", "retention", "variation", "eot"];
const UNITS = ["working_days", "calendar_days", "weeks", "months"];

export default function ContractPage() {
  const { id } = useParams<{ id: string }>();
  const { reload } = useProject();
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const load = useCallback(() => api<Contract[]>(`/projects/${id}/contract`).then(setContracts), [id]);
  useEffect(() => {
    load();
  }, [load]);

  if (contracts === null) return <Empty>Loading…</Empty>;
  if (contracts.length === 0) return <Empty>No contract uploaded yet. Upload it under Documents with type “contract”.</Empty>;
  const c = contracts[contracts.length - 1];
  const rule = c.rules.find((r) => r.id === selected) ?? null;
  const counts = c.rules.reduce<Record<string, number>>((a, r) => ({ ...a, [r.status]: (a[r.status] ?? 0) + 1 }), {});

  return (
    <div className="flex h-screen">
      <div className="min-w-0 flex-1 overflow-auto p-4">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h1 className="text-base font-semibold">Contract rules</h1>
            <p className="text-xs text-slate-500">{c.title} · {c.clauses.length} clauses · status <StatusPill status={c.status} /></p>
          </div>
          <div className="text-xs text-slate-600">{counts.approved ?? 0} approved · {counts.proposed ?? 0} to review · {counts.rejected ?? 0} rejected</div>
        </div>
        <div className="mb-3 rounded border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
          Rules are extracted by the contract agent and only go live once approved here. Agents link events only to approved rules; deadlines are computed from the approved period and unit.
        </div>
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr><th className="th">Clause</th><th className="th">Obligation</th><th className="th">Type</th><th className="th">Period</th><th className="th">Applies to</th><th className="th">CP</th><th className="th">Confidence</th><th className="th">Status</th></tr>
            </thead>
            <tbody>
              {c.rules.map((r) => (
                <tr key={r.id} onClick={() => setSelected(r.id)} className={`cursor-pointer ${selected === r.id ? "bg-sky-50" : "hover:bg-slate-50"}`}>
                  <td className="td font-semibold">{r.clause_ref}</td>
                  <td className="td"><div className="font-medium">{r.title}</div><div className="line-clamp-1 text-2xs text-slate-500">{r.trigger_event}</div></td>
                  <td className="td">{r.rule_type.replace("_", " ")}</td>
                  <td className="td whitespace-nowrap">{r.details?.day_of_month ? `by the ${r.details.day_of_month}th of each month` : period(r.period_value, r.period_unit)}</td>
                  <td className="td text-2xs">{r.event_categories.join(", ") || "—"}</td>
                  <td className="td">{r.condition_precedent ? <span className="font-semibold text-rose-700">yes</span> : "—"}</td>
                  <td className="td"><Confidence value={r.confidence} />{r.details?.quote_verified === false && <div className="text-2xs text-amber-700">quote not found</div>}</td>
                  <td className="td"><StatusPill status={r.status} />{r.edited && <span className="ml-1 text-2xs text-slate-500">edited</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <aside className="w-[440px] shrink-0 overflow-auto border-l border-slate-200 bg-white">
        {rule ? <RulePanel key={rule.id} rule={rule} documentId={c.document_id} projectId={id} onDone={() => { load(); reload(); }} /> : <Empty>Select a rule to review it against the contract text.</Empty>}
      </aside>
    </div>
  );
}

function RulePanel({ rule, documentId, projectId, onDone }: { rule: RuleT; documentId: string; projectId: string; onDone: () => void }) {
  const [f, setF] = useState({ ...rule });
  const [error, setError] = useState<string | null>(null);
  const editable = ["rule_type", "clause_ref", "title", "summary", "trigger_event", "event_categories", "period_value", "period_unit", "recipient", "required_form", "condition_precedent"] as const;
  const edits = Object.fromEntries(editable.filter((k) => JSON.stringify(f[k]) !== JSON.stringify(rule[k])).map((k) => [k, f[k]]));
  const hasEdits = Object.keys(edits).length > 0;

  async function decide(decision: string) {
    setError(null);
    try {
      await api(`/rules/${rule.id}/review`, { method: "POST", json: { decision, edits: hasEdits && decision === "approve" ? edits : null } });
      onDone();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="space-y-3 p-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Clause {rule.clause_ref} · {rule.title}</h2>
        <StatusPill status={rule.status} />
      </div>
      {rule.source_char_start !== null && (
        <SourcePassage projectId={projectId} context={400}
          citation={{ document_id: documentId, item_id: null, clause_ref: rule.clause_ref, char_start: rule.source_char_start, char_end: rule.source_char_end!, quote: rule.source_quote, label: "Contract", verified: true }} />
      )}
      <ErrorBox error={error} />
      <div className="grid grid-cols-2 gap-2">
        <label className="space-y-0.5"><span className="label">Type</span>
          <select className="input" value={f.rule_type} onChange={(e) => setF({ ...f, rule_type: e.target.value })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
        <label className="space-y-0.5"><span className="label">Clause</span><input className="input" value={f.clause_ref} onChange={(e) => setF({ ...f, clause_ref: e.target.value })} /></label>
        <label className="space-y-0.5"><span className="label">Period</span><input className="input" type="number" min={0} value={f.period_value ?? ""} onChange={(e) => setF({ ...f, period_value: e.target.value === "" ? null : Number(e.target.value) })} /></label>
        <label className="space-y-0.5"><span className="label">Unit</span>
          <select className="input" value={f.period_unit ?? ""} onChange={(e) => setF({ ...f, period_unit: e.target.value || null })}><option value="">—</option>{UNITS.map((u) => <option key={u} value={u}>{u.replace("_", " ")}</option>)}</select></label>
      </div>
      <label className="block space-y-0.5"><span className="label">Title</span><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
      <label className="block space-y-0.5"><span className="label">Trigger event</span><input className="input" value={f.trigger_event ?? ""} onChange={(e) => setF({ ...f, trigger_event: e.target.value })} /></label>
      <label className="block space-y-0.5"><span className="label">Recipient</span><input className="input" value={f.recipient ?? ""} onChange={(e) => setF({ ...f, recipient: e.target.value })} /></label>
      <label className="block space-y-0.5"><span className="label">Required form</span><input className="input" value={f.required_form ?? ""} onChange={(e) => setF({ ...f, required_form: e.target.value })} /></label>
      <label className="block space-y-0.5"><span className="label">Summary</span><textarea className="input h-16" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></label>
      <div className="space-y-0.5">
        <span className="label">Applies to events</span>
        <div className="flex flex-wrap gap-2 text-xs">
          {CATS.map((c) => (
            <label key={c} className="flex items-center gap-1"><input type="checkbox" checked={f.event_categories.includes(c)}
              onChange={(e) => setF({ ...f, event_categories: e.target.checked ? [...f.event_categories, c] : f.event_categories.filter((x) => x !== c) })} />{c}</label>
          ))}
        </div>
      </div>
      <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={f.condition_precedent} onChange={(e) => setF({ ...f, condition_precedent: e.target.checked })} /> Condition precedent / time bar</label>
      <div className="flex gap-1.5 border-t border-slate-100 pt-2">
        {rule.status !== "approved" && <button className="btn-primary" onClick={() => decide("approve")}>{hasEdits ? "Save edits & approve" : "Approve"}</button>}
        {rule.status !== "rejected" && <button className="btn-danger" onClick={() => decide("reject")}>Reject</button>}
        {rule.status !== "proposed" && <button className="btn" onClick={() => decide("reopen")}>Reopen</button>}
      </div>
      {hasEdits && <p className="text-2xs text-slate-500">Edited fields: {Object.keys(edits).join(", ")}. The original extraction is kept for audit.</p>}
    </div>
  );
}
