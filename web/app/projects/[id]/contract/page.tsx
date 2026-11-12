"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, RuleT } from "@/lib/api";
import { period } from "@/lib/format";
import { PanelSection, PanelTitle, RegisterLayout, RegisterTable, rowClass, Segments } from "@/components/register";
import { Empty, ErrorBox, StatusPill } from "@/components/ui";
import { SourcePassage } from "@/components/SourcePassage";
import { useProject } from "@/components/project-context";

type Contract = { id: string; document_id: string; title: string; status: string; rules: RuleT[]; clauses: { ref: string }[] };
type Show = "all" | "proposed" | "approved" | "rejected";
const CATS = ["change", "delay", "instruction", "disruption"];
const TYPES = ["notice", "time_bar", "payment", "retention", "variation", "eot"];
const UNITS = ["working_days", "calendar_days", "weeks", "months"];
const TYPE_TEXT: Record<string, string> = {
  notice: "Notice", time_bar: "Time bar", payment: "Payment", retention: "Retention", variation: "Change procedure", eot: "Extension of time",
};

function periodText(r: RuleT) {
  if (r.details?.day_of_month) return `By the ${r.details.day_of_month}th of each month`;
  return period(r.period_value, r.period_unit);
}

export default function ContractPage() {
  const { id } = useParams<{ id: string }>();
  const { reload } = useProject();
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [show, setShow] = useState<Show>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const load = useCallback(() => api<Contract[]>(`/projects/${id}/contract`).then(setContracts), [id]);
  useEffect(() => {
    load();
  }, [load]);

  const c = contracts?.[contracts.length - 1];
  const rules = (c?.rules ?? []).filter((r) => show === "all" || r.status === show);
  const sel = c?.rules.find((r) => r.id === selected) ?? null;
  const count = (s: string) => c?.rules.filter((r) => r.status === s).length ?? 0;

  return (
    <RegisterLayout
      title="Contract rules"
      description={c ? `The obligations the agents work from, read from ${c.title}. A rule is only used once you approve it.` : undefined}
      filters={c && <Segments value={show} onChange={setShow} options={[["all", "All"], ["proposed", `To approve (${count("proposed")})`], ["approved", `Approved (${count("approved")})`], ["rejected", "Rejected"]]} />}
      panel={sel && c ? <RulePanel key={sel.id} rule={sel} documentId={c.document_id} projectId={id} onDone={() => { load(); reload(); }} /> : undefined}
      onClose={() => setSelected(null)}
    >
      {contracts === null ? <Empty>Loading…</Empty> : !c ? <Empty>No contract uploaded yet. Upload it under Documents as type “contract”.</Empty> : rules.length === 0 ? <Empty>Nothing here.</Empty> : (
        <RegisterTable head={["Clause", "Obligation", "Period", "Status"]}>
          {rules.map((r) => (
            <tr key={r.id} className={rowClass(selected === r.id)} onClick={() => setSelected(r.id)}>
              <td className="td w-20 tabular-nums">{r.clause_ref}</td>
              <td className="td">{r.title}<div className="text-xs text-neutral-400">{TYPE_TEXT[r.rule_type] ?? r.rule_type}{r.condition_precedent ? " · condition precedent" : ""}</div></td>
              <td className="td w-56 text-neutral-600">{periodText(r)}</td>
              <td className="td w-32"><StatusPill status={r.status} />{r.edited && <span className="text-xs text-neutral-400"> · edited</span>}</td>
            </tr>
          ))}
        </RegisterTable>
      )}
    </RegisterLayout>
  );
}

function RulePanel({ rule, documentId, projectId, onDone }: { rule: RuleT; documentId: string; projectId: string; onDone: () => void }) {
  const [f, setF] = useState({ ...rule });
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editable = ["rule_type", "clause_ref", "title", "summary", "trigger_event", "event_categories", "period_value", "period_unit", "recipient", "required_form", "condition_precedent"] as const;
  const edits = Object.fromEntries(editable.filter((k) => JSON.stringify(f[k]) !== JSON.stringify(rule[k])).map((k) => [k, f[k]]));
  const hasEdits = Object.keys(edits).length > 0;

  async function decide(decision: string) {
    setError(null);
    try {
      await api(`/rules/${rule.id}/review`, { method: "POST", json: { decision, edits: hasEdits && decision === "approve" ? edits : null } });
      setEditing(false);
      onDone();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <>
      <PanelTitle kicker={`Clause ${rule.clause_ref} · ${TYPE_TEXT[rule.rule_type] ?? rule.rule_type}`} title={rule.title}>
        <p className="text-[13px] text-neutral-500"><StatusPill status={rule.status} />{rule.details?.quote_verified === false && " · quote not found in the contract, check carefully"}</p>
      </PanelTitle>
      <PanelSection label="What it means">
        <p>{rule.summary}</p>
        <p className="mt-2 text-neutral-600">
          {periodText(rule)}{rule.trigger_event ? ` after ${rule.trigger_event}` : ""}.
          {rule.recipient ? ` To: ${rule.recipient}.` : ""}
          {rule.condition_precedent ? " Condition precedent: a late notice can bar the entitlement." : ""}
        </p>
        {rule.event_categories.length > 0 && <p className="mt-1 text-[13px] text-neutral-500">The Notice agent links this rule to: {rule.event_categories.join(", ")}.</p>}
      </PanelSection>
      {rule.source_char_start !== null && (
        <PanelSection label="In the contract">
          <SourcePassage projectId={projectId} context={300}
            citation={{ document_id: documentId, item_id: null, clause_ref: rule.clause_ref, char_start: rule.source_char_start, char_end: rule.source_char_end!, quote: rule.source_quote, label: "Contract", verified: true }} />
        </PanelSection>
      )}
      {editing && (
        <PanelSection label="Edit before approving">
          <div className="space-y-2.5">
            <div className="grid grid-cols-2 gap-2">
              <label className="space-y-1"><span className="label">Type</span><select className="input" value={f.rule_type} onChange={(e) => setF({ ...f, rule_type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{TYPE_TEXT[t]}</option>)}</select></label>
              <label className="space-y-1"><span className="label">Clause</span><input className="input" value={f.clause_ref} onChange={(e) => setF({ ...f, clause_ref: e.target.value })} /></label>
              <label className="space-y-1"><span className="label">Period</span><input className="input" type="number" min={0} value={f.period_value ?? ""} onChange={(e) => setF({ ...f, period_value: e.target.value === "" ? null : Number(e.target.value) })} /></label>
              <label className="space-y-1"><span className="label">Unit</span><select className="input" value={f.period_unit ?? ""} onChange={(e) => setF({ ...f, period_unit: e.target.value || null })}><option value="">—</option>{UNITS.map((u) => <option key={u} value={u}>{u.replace("_", " ")}</option>)}</select></label>
            </div>
            <label className="block space-y-1"><span className="label">Title</span><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
            <label className="block space-y-1"><span className="label">Clock starts after</span><input className="input" value={f.trigger_event ?? ""} onChange={(e) => setF({ ...f, trigger_event: e.target.value })} /></label>
            <label className="block space-y-1"><span className="label">Send to</span><input className="input" value={f.recipient ?? ""} onChange={(e) => setF({ ...f, recipient: e.target.value })} /></label>
            <label className="block space-y-1"><span className="label">Required form</span><input className="input" value={f.required_form ?? ""} onChange={(e) => setF({ ...f, required_form: e.target.value })} /></label>
            <label className="block space-y-1"><span className="label">Summary</span><textarea className="input h-20" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></label>
            <div className="space-y-1">
              <span className="label">Applies to events</span>
              <div className="flex flex-wrap gap-3 text-[13px]">
                {CATS.map((cat) => (
                  <label key={cat} className="flex items-center gap-1"><input type="checkbox" className="accent-neutral-800" checked={f.event_categories.includes(cat)}
                    onChange={(e) => setF({ ...f, event_categories: e.target.checked ? [...f.event_categories, cat] : f.event_categories.filter((x) => x !== cat) })} />{cat}</label>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-1.5 text-[13px]"><input type="checkbox" className="accent-neutral-800" checked={f.condition_precedent} onChange={(e) => setF({ ...f, condition_precedent: e.target.checked })} /> Condition precedent / time bar</label>
            {hasEdits && <p className="text-xs text-neutral-400">Changed: {Object.keys(edits).join(", ")}. The original extraction is kept for audit.</p>}
          </div>
        </PanelSection>
      )}
      <div className="flex items-center gap-3 border-t border-neutral-100 pt-4 text-[14px]">
        {rule.status !== "approved" && <button className="btn-primary" onClick={() => decide("approve")}>{hasEdits ? "Save and approve" : "Approve"}</button>}
        {!editing && rule.status !== "approved" && <button className="text-neutral-700 hover:text-neutral-900" onClick={() => setEditing(true)}>Edit</button>}
        {editing && <button className="text-neutral-500 hover:text-neutral-900" onClick={() => { setEditing(false); setF({ ...rule }); }}>Cancel</button>}
        {rule.status !== "rejected" && <button className="text-neutral-500 hover:text-neutral-900" onClick={() => decide("reject")}>Reject</button>}
        {rule.status !== "proposed" && <button className="text-neutral-500 hover:text-neutral-900" onClick={() => decide("reopen")}>Reopen</button>}
      </div>
      <ErrorBox error={error} />
    </>
  );
}
