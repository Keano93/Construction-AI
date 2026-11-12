"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { api, Citation, ReviewItemT } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Confidence, ErrorBox } from "@/components/ui";
import { SourcePassage } from "@/components/SourcePassage";

// ---------------- Revision comparison ----------------

type Change = {
  id: string;
  kind: string;
  key: string;
  label: string;
  old_text: string;
  new_text: string;
  old_span: number[] | null;
  new_span: number[] | null;
  word_diff: { old: string; new: string }[];
  fields: Record<string, string[]>;
  issue_date: string | null;
  cross_refs: { events: { ref: string; title: string; match: string; id: string }[]; documents: { id: string; filename: string }[] };
  raised: null | { mode: string; event_ref: string; review_item?: string; possibly_related?: string[] };
  assessment: {
    summary: string;
    change_type: string;
    cost_impact: string;
    time_impact: string;
    affected_packages: string[];
    potential_variation: boolean;
    rationale: string;
    confidence: number;
    quote_issues: string[];
  };
};

const COST: Record<string, string> = {
  none: "text-slate-400", low: "text-slate-700", medium: "text-orange-700 font-semibold", high: "text-rose-700 font-semibold", unknown: "text-slate-500 italic",
};

function WordDiff({ c }: { c: Change }) {
  if (Object.keys(c.fields ?? {}).length) {
    return (
      <div className="space-y-0.5">
        {Object.entries(c.fields).map(([k, [o, n]]) => (
          <div key={k}><span className="text-slate-500">{k}:</span> {o && <del className="bg-rose-50 text-rose-700">{o}</del>} {n && <ins className="bg-emerald-50 text-emerald-800 no-underline">{n}</ins>}</div>
        ))}
      </div>
    );
  }
  if (c.kind === "added") return <ins className="bg-emerald-50 text-emerald-800 no-underline">{c.new_text}</ins>;
  if (c.kind === "removed") return <del className="bg-rose-50 text-rose-700">{c.old_text}</del>;
  return (
    <div className="space-y-0.5">
      {c.word_diff.map((d, i) => (
        <div key={i}>{d.old && <del className="bg-rose-50 text-rose-700">{d.old}</del>}{d.old && d.new ? " → " : ""}{d.new && <ins className="bg-emerald-50 text-emerald-800 no-underline">{d.new}</ins>}</div>
      ))}
    </div>
  );
}

export function RevisionBody({ r, projectId, onRaised }: { r: ReviewItemT; projectId: string; onRaised: () => void }) {
  const comp = (r as any).comparison as { id: string; changes: Change[]; base: { id: string; filename: string }; revised: { id: string; filename: string }; flags: string[]; method: string } | undefined;
  const [open, setOpen] = useState<string | null>(null);
  const [onlyPv, setOnlyPv] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!comp) return null;

  async function raise(c: Change, forceNew = false) {
    setBusy(c.id);
    setError(null);
    try {
      await api(`/revisions/${comp!.id}/changes/${c.id}/raise`, { method: "POST", json: { force_new: forceNew } });
      onRaised();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  const rows = comp.changes.filter((c) => !onlyPv || c.assessment.potential_variation);
  const cite = (docId: string, span: number[], text: string, label: string): Citation =>
    ({ document_id: docId, item_id: null, clause_ref: null, char_start: span[0], char_end: span[1], quote: text, label, verified: true });

  return (
    <div className="space-y-2">
      {comp.flags.length > 0 && (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {comp.flags.map((f, i) => <div key={i}><b>Understated revision:</b> {f}</div>)}
        </div>
      )}
      <div className="flex items-center justify-between text-xs">
        <div className="text-slate-600">
          <Link className="text-sky-800 hover:underline" href={`/projects/${projectId}/documents/${comp.base.id}`}>{comp.base.filename}</Link> →{" "}
          <Link className="text-sky-800 hover:underline" href={`/projects/${projectId}/documents/${comp.revised.id}`}>{comp.revised.filename}</Link>
          <span className="ml-2 text-2xs text-slate-400">changes found by {comp.method} diff (code); impact assessed by the agent</span>
        </div>
        <label className="flex items-center gap-1 text-2xs"><input type="checkbox" checked={onlyPv} onChange={(e) => setOnlyPv(e.target.checked)} /> potential variations only</label>
      </div>
      <ErrorBox error={error} />
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead><tr><th className="th">#</th><th className="th">Change</th><th className="th">Old → new</th><th className="th">Assessment</th><th className="th">Already on register</th><th className="th"></th></tr></thead>
          <tbody>
            {rows.map((c) => (
              <Fragment key={c.id}>
                <tr className={`cursor-pointer ${open === c.id ? "bg-sky-50" : "hover:bg-slate-50"}`} onClick={() => setOpen(open === c.id ? null : c.id)}>
                  <td className="td text-2xs text-slate-500">{c.id}<div>{c.kind}</div></td>
                  <td className="td max-w-[220px]"><div className="font-medium">{c.label}</div>{c.issue_date && <div className="text-2xs text-slate-500">issued {fmtDate(c.issue_date)}</div>}</td>
                  <td className="td max-w-[260px] text-2xs"><WordDiff c={c} /></td>
                  <td className="td max-w-[260px] text-2xs">
                    <div>{c.assessment.summary}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span>{c.assessment.change_type.replace("_", " ")}</span>
                      <span className={COST[c.assessment.cost_impact]}>cost {c.assessment.cost_impact}</span>
                      <span>time {c.assessment.time_impact}</span>
                      <Confidence value={c.assessment.confidence} />
                    </div>
                  </td>
                  <td className="td text-2xs">
                    {c.cross_refs.events.map((e) => (
                      <div key={e.ref} title={e.title}>{e.ref} <span className="text-slate-400">{e.match === "similar" ? "(similar - check)" : "(same identifier)"}</span></div>
                    ))}
                    {c.cross_refs.documents.slice(0, 2).map((d) => (
                      <div key={d.id}><Link className="text-sky-800 hover:underline" href={`/projects/${projectId}/documents/${d.id}`}>{d.filename}</Link></div>
                    ))}
                  </td>
                  <td className="td whitespace-nowrap text-2xs" onClick={(e) => e.stopPropagation()}>
                    {c.raised ? (
                      <div>
                        {c.raised.mode === "attached" ? "Attached to " : "Raised as "}
                        {c.raised.review_item ? <Link className="font-semibold text-sky-800 hover:underline" href={`/projects/${projectId}/inbox?item=${c.raised.review_item}`}>{c.raised.event_ref}</Link> : <b>{c.raised.event_ref}</b>}
                        {c.raised.mode === "attached" && <div><button className="text-sky-700 hover:underline" disabled={busy !== null} onClick={() => raise(c, true)}>raise as new anyway</button></div>}
                      </div>
                    ) : c.assessment.potential_variation ? (
                      <button className="btn" disabled={busy !== null} onClick={() => raise(c)}>{busy === c.id ? "…" : "Raise potential variation"}</button>
                    ) : <span className="text-slate-400">no action</span>}
                  </td>
                </tr>
                {open === c.id && (
                  <tr>
                    <td colSpan={6} className="border-b border-slate-200 bg-slate-50 p-2">
                      <div className="mb-1 text-2xs text-slate-600"><b>Rationale:</b> {c.assessment.rationale} {c.assessment.affected_packages.length > 0 && `· packages: ${c.assessment.affected_packages.join(", ")}`}</div>
                      <div className="grid gap-2 md:grid-cols-2">
                        {c.old_span ? <SourcePassage projectId={projectId} context={160} citation={cite(comp.base.id, c.old_span, c.old_text, `Previous: ${comp.base.filename}`)} /> : <div className="text-2xs text-slate-500">Not in previous revision.</div>}
                        {c.new_span ? <SourcePassage projectId={projectId} context={160} citation={cite(comp.revised.id, c.new_span, c.new_text, `Revised: ${comp.revised.filename}`)} /> : <div className="text-2xs text-slate-500">Removed in the revision.</div>}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-2xs text-slate-500">“Raise potential variation” hands the change to the Notice agent: it starts the clause clock from the issue date (or the date the revision was received) and drafts a notice for review. Changes sharing a drawing number or grid reference with an existing event are attached to it instead.</p>
    </div>
  );
}

// ---------------- Claim draft ----------------

const SIG_STYLE: Record<string, string> = {
  cause: "bg-violet-50 text-violet-800", effect: "bg-orange-50 text-orange-800", instruction: "bg-sky-50 text-sky-800",
  notice: "bg-emerald-50 text-emerald-800", response: "bg-slate-100 text-slate-700", mitigation: "bg-teal-50 text-teal-800", record: "bg-slate-50 text-slate-600",
};
const STATE_STYLE: Record<string, string> = {
  given_in_time: "text-emerald-700", given_late: "text-rose-700 font-semibold", not_given_overdue: "text-rose-700 font-semibold",
  not_given_open: "text-orange-700", cancelled: "text-slate-400",
};

export function ClaimBody({ r, projectId }: { r: ReviewItemT; projectId: string }) {
  const claim = (r as any).claim;
  const [open, setOpen] = useState<number | null>(null);
  if (!claim) return null;
  const n = claim.narrative ?? {};
  return (
    <div className="space-y-3">
      {claim.time_bar_risk && (
        <div className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-900">
          <b>Time-bar risk.</b> At least one notice that is a condition precedent was not given in time. The narrative says so; take advice before relying on this claim.
        </div>
      )}
      <section className="space-y-1">
        <h3 className="label">Notice compliance (computed from the contract rules and the notice record)</h3>
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead><tr><th className="th">Event</th><th className="th">Clause</th><th className="th">Aware</th><th className="th">Due</th><th className="th">Position</th></tr></thead>
            <tbody>
              {claim.notice_compliance.map((c: any, i: number) => (
                <tr key={i}>
                  <td className="td">{c.event_ref}</td>
                  <td className="td">{c.clause_ref} {c.title}{c.condition_precedent && <div className="text-2xs font-semibold text-rose-700">condition precedent</div>}</td>
                  <td className="td whitespace-nowrap">{fmtDate(c.trigger_date)}</td>
                  <td className="td whitespace-nowrap">{fmtDate(c.due_date)}</td>
                  <td className={`td ${STATE_STYLE[c.state] ?? ""}`}>{c.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="space-y-1">
        <h3 className="label">Evidence timeline ({claim.timeline.length} entries, dated from the records; click to see the source)</h3>
        <div className="card overflow-hidden">
          <table className="w-full">
            <tbody>
              {claim.timeline.map((t: any, i: number) => (
                <Fragment key={i}>
                  <tr className="cursor-pointer hover:bg-slate-50" onClick={() => setOpen(open === i ? null : i)}>
                    <td className="td whitespace-nowrap tabular-nums">{fmtDate(t.date)}</td>
                    <td className="td"><span className={`rounded px-1.5 py-px text-2xs font-semibold ${SIG_STYLE[t.significance] ?? ""}`}>{t.significance}</span></td>
                    <td className="td">{t.description}</td>
                    <td className="td whitespace-nowrap text-2xs text-slate-500">{t.evidence_id} · {t.channel} · {t.author?.split("<")[0]}</td>
                  </tr>
                  {open === i && (
                    <tr><td colSpan={4} className="border-b border-slate-200 bg-slate-50 p-2">
                      <SourcePassage projectId={projectId} citation={{ document_id: t.document_id, item_id: t.item_id, clause_ref: null, char_start: t.char_start, char_end: t.char_end, quote: t.quote, label: t.filename, verified: true }} />
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="grid gap-3 md:grid-cols-2">
        <section className="space-y-1">
          <h3 className="label">Quantum (placeholders — no figures generated)</h3>
          <div className="card divide-y divide-slate-100 text-xs">
            {(n.quantum_heads ?? []).map((q: any, i: number) => (
              <div key={i} className="px-2 py-1.5"><b>{q.head}</b>: EUR [to be quantified]<div className="text-2xs text-slate-500">{q.basis}. Records: {q.records_needed.join(", ")}</div></div>
            ))}
          </div>
        </section>
        <section className="space-y-1">
          <h3 className="label">Risks and missing records</h3>
          <ul className="card list-disc space-y-0.5 py-1.5 pl-6 pr-2 text-xs">
            {(n.risks ?? []).map((x: string, i: number) => <li key={`r${i}`}>{x}</li>)}
            {claim.gaps.map((g: string, i: number) => <li key={`g${i}`} className="text-slate-600">Missing: {g}</li>)}
          </ul>
        </section>
      </div>
      {(r.payload?.issues?.length ?? 0) > 0 && (
        <details className="text-2xs text-slate-500"><summary>Verification notes ({r.payload.issues.length})</summary><ul className="list-disc pl-4">{r.payload.issues.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></details>
      )}
    </div>
  );
}

