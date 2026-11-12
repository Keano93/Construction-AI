"use client";

/** Kind-specific pieces of the review document: notes for notices and claims, the change list for revisions. */

import Link from "next/link";
import { useState } from "react";
import { api, Citation, ReviewItemT } from "@/lib/api";
import { complianceText, fmtDate } from "@/lib/format";
import { Note, sourceLabel } from "./doc";

// ---------- notice ----------

export function noticeNotes(r: ReviewItemT): Note[] {
  const notes: Note[] = [];
  const source = r.payload?.source;
  r.citations.forEach((c, i) => {
    if (c.clause_ref) {
      const rule = (r.payload?.rules ?? []).find((x: any) => x.clause_ref === c.clause_ref);
      notes.push({ id: `c${i}`, title: `Clause ${c.clause_ref}${rule ? ` · ${rule.title}` : ""}`,
        subtitle: rule?.condition_precedent ? "Condition precedent: a late notice can bar the claim" : undefined,
        preview: c.quote, citation: c, quote: c.quote });
    } else {
      notes.push({ id: `c${i}`, title: "What was said", subtitle: sourceLabel(source), preview: c.quote, citation: c, quote: c.quote });
    }
  });
  for (const d of r.deadlines ?? []) {
    const hols = d.trace.skipped.filter((s) => !s.reason.startsWith("weekend"));
    notes.push({
      id: `d${d.id}`, title: `Deadline · ${fmtDate(d.due_date)}`, subtitle: d.label, preview: d.trace.explanation,
      content: (
        <div className="space-y-1">
          <p>{d.trace.explanation}</p>
          {hols.length > 0 && <p className="text-neutral-500">Not counted: {hols.map((s) => `${fmtDate(s.date)} (${s.reason.replace("public holiday: ", "")})`).join(", ")}</p>}
          <p className="text-neutral-400">Calculated by the deadline engine from the approved contract rule, not by the AI.</p>
        </div>
      ),
    });
  }
  notes.push(whyNote(r));
  return notes;
}

export function whyNote(r: ReviewItemT): Note {
  const issues: string[] = r.payload?.verification?.issues ?? r.payload?.issues ?? [];
  const also: string[] = r.payload?.classification?.secondary_categories ?? [];
  return {
    id: "why", title: "Why the agent flagged this", subtitle: `Confidence ${Math.round(r.confidence * 100)}%${r.low_confidence ? " · needs checking" : ""}`,
    content: (
      <div className="space-y-1">
        {r.payload?.classification?.trigger_date_basis && <p>Date aware: {r.payload.classification.trigger_date_basis}</p>}
        {also.length > 0 && <p>Could also be: {also.join(", ")}</p>}
        {issues.length > 0 ? <ul className="list-disc pl-4 text-neutral-500">{issues.map((x, i) => <li key={i}>{x}</li>)}</ul>
          : <p className="text-neutral-500">All quotes were found in the source documents.</p>}
        <p className="text-neutral-400">{r.agent.replace("_", " ")}</p>
      </div>
    ),
  };
}

// ---------- claim ----------

export function claimNotes(r: ReviewItemT): Note[] {
  const claim = (r as any).claim;
  if (!claim) return [];
  const notes: Note[] = [];
  const risky = claim.notice_compliance.filter((c: any) => c.time_bar_risk);
  notes.push({
    id: "notices", title: "Notice position", subtitle: risky.length ? `${risky.length} condition-precedent notice(s) not given in time` : "From the contract rules and notice record",
    content: (
      <ul className="space-y-1">
        {claim.notice_compliance.map((c: any, i: number) => (
          <li key={i}>
            <span className="font-medium">{c.event_ref} · clause {c.clause_ref}</span> {c.title}
            <div className={c.time_bar_risk ? "text-red-600" : "text-neutral-500"}>{complianceText(c)}</div>
          </li>
        ))}
      </ul>
    ),
  });
  claim.timeline.forEach((t: any, i: number) => {
    const cit: Citation = { document_id: t.document_id, item_id: t.item_id, clause_ref: null, char_start: t.char_start, char_end: t.char_end,
      quote: t.quote, label: t.filename, verified: true };
    notes.push({ id: `t${i}`, title: `${fmtDate(t.date)} · ${t.significance}`, subtitle: sourceLabel({ author: t.author, channel: t.channel }),
      preview: t.description, citation: cit, quote: t.quote });
  });
  if (claim.gaps.length) {
    notes.push({ id: "gaps", title: "Records still needed", subtitle: `${claim.gaps.length} item(s)`,
      content: <ul className="list-disc pl-4">{claim.gaps.map((g: string, i: number) => <li key={i}>{g}</li>)}</ul> });
  }
  notes.push(whyNote(r));
  return notes;
}

// ---------- revision ----------

type Change = {
  id: string; kind: string; key: string; label: string; old_text: string; new_text: string;
  old_span: number[] | null; new_span: number[] | null; word_diff: { old: string; new: string }[];
  fields: Record<string, string[]>; issue_date: string | null;
  cross_refs: { events: { ref: string; title: string; match: string }[] };
  raised: null | { mode: string; event_ref: string; review_item?: string };
  assessment: { summary: string; change_type: string; cost_impact: string; time_impact: string; potential_variation: boolean; rationale: string; affected_packages: string[] };
};

function diffSentence(c: Change): string {
  if (Object.keys(c.fields ?? {}).length) {
    if (c.kind === "added") return "New drawing added to the register.";
    const rev = c.fields.Revision;
    return rev ? `Revised ${rev[0]} → ${rev[1]}${c.fields.Title ? `, retitled "${c.fields.Title[1]}"` : ""}.` : "Register details changed.";
  }
  if (c.kind === "added") return "Added in this revision.";
  if (c.kind === "removed") return "Removed in this revision.";
  const tidy = (t: string) => t.replace(/[,;:.]+$/, "");
  return c.word_diff.slice(0, 4).map((d) => `${tidy(d.old) || "—"} → ${tidy(d.new) || "—"}`).join("; ");
}

export function revisionNotes(r: ReviewItemT): Note[] {
  const comp = (r as any).comparison;
  if (!comp) return [];
  const notes: Note[] = [];
  for (const c of comp.changes as Change[]) {
    if (!c.assessment.potential_variation) continue;
    const before: Citation | undefined = c.old_span ? { document_id: comp.base.id, item_id: null, clause_ref: null, char_start: c.old_span[0], char_end: c.old_span[1], quote: c.old_text, label: `Before · ${comp.base.filename}`, verified: true } : undefined;
    const after: Citation | undefined = c.new_span ? { document_id: comp.revised.id, item_id: null, clause_ref: null, char_start: c.new_span[0], char_end: c.new_span[1], quote: c.new_text, label: `After · ${comp.revised.filename}`, verified: true } : undefined;
    notes.push({
      id: `ch${c.id}`, title: c.label, subtitle: `Likely cost: ${c.assessment.cost_impact} · time: ${c.assessment.time_impact}`,
      preview: c.assessment.rationale,
      content: (
        <div className="space-y-2">
          <p>{c.assessment.rationale}</p>
          {c.cross_refs.events.length > 0 && (
            <p className="text-neutral-500">Related: {c.cross_refs.events.map((e) => `${e.ref} ${e.title}${e.match === "similar" ? " (similar wording)" : ""}`).join("; ")}</p>
          )}
          {before && <PassageMini c={before} />}
          {after && <PassageMini c={after} />}
        </div>
      ),
    });
  }
  notes.push(whyNote(r));
  return notes;
}

function PassageMini({ c }: { c: Citation }) {
  return (
    <div>
      <div className="text-neutral-400">{c.label}</div>
      <div className="whitespace-pre-wrap rounded bg-neutral-50 px-2 py-1 font-mono text-[11.5px]">{c.quote}</div>
    </div>
  );
}

export function RevisionChanges({ r, projectId, active, onSelect, onChanged }: {
  r: ReviewItemT; projectId: string; active: string | null; onSelect: (id: string) => void; onChanged: () => void;
}) {
  const comp = (r as any).comparison;
  const [busy, setBusy] = useState<string | null>(null);
  const [showAdmin, setShowAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!comp) return null;
  const changes = comp.changes as Change[];
  const pv = changes.filter((c) => c.assessment.potential_variation);
  const other = changes.filter((c) => !c.assessment.potential_variation);

  async function raise(c: Change, forceNew = false) {
    setBusy(c.id);
    setError(null);
    try {
      await api(`/revisions/${comp.id}/changes/${c.id}/raise`, { method: "POST", json: { force_new: forceNew } });
      onChanged();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  const row = (c: Change) => {
    const covered = c.cross_refs.events.find((e) => e.match === "identifier");
    return (
      <li key={c.id} className={`-mx-3 rounded-md px-3 py-2.5 ${active === `ch${c.id}` ? "bg-neutral-100" : ""}`}>
        <button className="block w-full text-left" onClick={() => onSelect(`ch${c.id}`)}>
          <div className="font-medium text-neutral-900">{c.label}</div>
          <div className="text-[14px] text-neutral-600">{diffSentence(c)}</div>
        </button>
        {c.assessment.potential_variation && (
          <div className="mt-1 text-[13px]">
            {c.raised ? (
              <span className="text-neutral-500">
                {c.raised.mode === "attached" ? "Added as evidence to " : "Raised as "}
                {c.raised.review_item ? <Link className="underline underline-offset-2" href={`/projects/${projectId}/inbox?item=${c.raised.review_item}`}>{c.raised.event_ref}</Link> : c.raised.event_ref}
                {c.raised.mode === "attached" && <> · <button className="underline underline-offset-2" disabled={!!busy} onClick={() => raise(c, true)}>raise separately</button></>}
              </span>
            ) : (
              <span className="space-x-3">
                <button className="font-medium text-neutral-900 underline underline-offset-2" disabled={!!busy} onClick={() => raise(c)}>
                  {busy === c.id ? "Raising…" : covered ? `Add to ${covered.ref}` : "Raise as variation"}
                </button>
                {covered && <span className="text-neutral-400">already on the register: {covered.title}</span>}
              </span>
            )}
          </div>
        )}
      </li>
    );
  };

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul>{pv.map(row)}</ul>
      {other.length > 0 && (
        <div className="text-[13px] text-neutral-500">
          <button className="underline underline-offset-2" onClick={() => setShowAdmin(!showAdmin)}>
            {showAdmin ? "Hide" : "Show"} {other.length} change{other.length === 1 ? "" : "s"} with no commercial effect
          </button>
          {showAdmin && <ul className="mt-1">{other.map(row)}</ul>}
        </div>
      )}
    </div>
  );
}
