"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, download } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CATEGORY_LABEL, cleanTitle } from "@/lib/text";
import { DuePhrase } from "@/components/inbox/doc";
import { ErrorBox } from "@/components/ui";
import { useProject } from "@/components/project-context";

type Notice = {
  event_id: string; event_ref: string; event_title: string; category: string; due_date: string; working_days_remaining: number;
  bucket: "overdue" | "this_week" | "next_week"; condition_precedent: boolean; draft_status: string | null; review_item_id: string | null;
  obligations: { clause_ref: string; label: string; due_date: string; condition_precedent: boolean }[];
};
type Reg = {
  event_id: string; ref: string; category: string; title: string; trigger_date: string; status: string; notice_state: string;
  next_due: string | null; time_bar_risk: boolean; estimated_value: number | null; value_note: string | null; claim_ref: string | null; review_item_id: string | null;
};
type ClaimRow = { id: string; ref: string; title: string; status: string; events: string[]; time_bar_risk: boolean; estimated_value: number | null; events_estimate: number | null; review_item_id: string | null };
type Item = { id: string; kind: string; text: string; owner: string | null; due_date: string | null; status: string; meeting_date: string; closed_on: string | null; overdue?: boolean };
type Pack = {
  meeting_date: string; since: string; previous_meeting: string | null;
  summary: Record<string, number>;
  notices: Notice[]; new_events: Reg[];
  new_revisions: { id: string; document: string; possible_variations: number; raised: number; understated: boolean; review_item_id: string | null }[];
  register: Reg[]; claims: ClaimRow[];
  totals: { by_category: Record<string, number>; all: number; notified: number; not_notified: number; time_bar_risk: number; unpriced_events: number };
  actions_open: Item[]; actions_closed: Item[]; decisions: Item[]; previous_decisions: Item[];
};

const eur = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `€${Math.round(v).toLocaleString("en-IE")}`);
const STATE: Record<string, string> = { issued: "Notified", overdue: "Notice overdue", open: "Notice due", none: "No notice clock" };
const today = () => new Date().toISOString().slice(0, 10);

export default function Meeting() {
  const { id } = useParams<{ id: string }>();
  const { project } = useProject();
  const [date, setDate] = useState(today());
  const [pack, setPack] = useState<Pack | null>(null);
  const [present, setPresent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<Pack>(`/projects/${id}/meeting?date=${date}`).then(setPack).catch((e) => setError(e.message)), [id, date]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    document.body.dataset.present = present ? "1" : "";
    return () => { document.body.dataset.present = ""; };
  }, [present]);

  const name = project?.name;
  const exportAs = (fmt: string) =>
    download(`/projects/${id}/meeting/export?format=${fmt}&date=${date}`, `Commercial meeting ${name ?? ""} ${date}.${fmt}`).catch((e) => setError(e.message));

  return (
    <div className="h-screen overflow-auto">
      <div className="present-scale mx-auto max-w-4xl px-8 pb-24 pt-7">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[26px] font-semibold tracking-tight text-neutral-900">Commercial meeting</h1>
            <p className="text-[14px] text-neutral-500">
              {name} · {pack ? new Date(`${pack.meeting_date}T12:00:00`).toLocaleDateString("en-IE", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : ""}
              {pack && <> · covering {pack.previous_meeting ? `since the last meeting on ${fmtDate(pack.previous_meeting)}` : `the 7 days since ${fmtDate(pack.since)}`}</>}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3 text-[13px]">
            <input type="date" aria-label="Meeting date" className="rounded-md border border-neutral-200 bg-white px-2 py-1" value={date} onChange={(e) => setDate(e.target.value || today())} />
            <button className="text-neutral-600 hover:text-neutral-900" onClick={() => exportAs("pdf")}>PDF</button>
            <button className="text-neutral-600 hover:text-neutral-900" onClick={() => exportAs("docx")}>Word</button>
            <button className="btn" onClick={() => setPresent(!present)}>{present ? "Exit present" : "Present"}</button>
          </div>
        </header>
        <ErrorBox error={error} />
        {!pack ? <p className="mt-8 text-sm text-neutral-400">Loading…</p> : (
          <>
            <Summary p={pack} />
            <Notices p={pack} projectId={id} name={name} />
            <NewSince p={pack} projectId={id} name={name} />
            <Register p={pack} projectId={id} name={name} onSaved={load} />
            <Actions p={pack} projectId={id} onChanged={load} />
          </>
        )}
      </div>
    </div>
  );
}

function Summary({ p }: { p: Pack }) {
  const s = p.summary;
  const red = (n: number) => (n > 0 ? "text-red-600" : "");
  return (
    <p className="mt-5 text-[15px] leading-relaxed text-neutral-700">
      <span className={red(s.notices_overdue)}>{s.notices_overdue} notice{s.notices_overdue === 1 ? "" : "s"} overdue</span>,{" "}
      {s.notices_this_week} due this week, {s.notices_next_week} due next week. {s.new_events} new event{s.new_events === 1 ? "" : "s"} since the last meeting.{" "}
      {s.actions_open} open action{s.actions_open === 1 ? "" : "s"}{s.actions_overdue ? <span className="text-red-600"> ({s.actions_overdue} overdue)</span> : ""}.{" "}
      Estimated changes and claims {eur(p.totals.all)}{p.totals.time_bar_risk > 0 && <>, of which <span className="text-red-600">{eur(p.totals.time_bar_risk)} at time-bar risk</span></>}.
    </p>
  );
}

function H({ n, title, children }: { n: number; title: string; children?: React.ReactNode }) {
  return (
    <div className="mt-10 flex items-baseline justify-between border-b border-neutral-200 pb-2">
      <h2 className="text-[18px] font-semibold text-neutral-900"><span className="mr-2 text-neutral-400">{n}.</span>{title}</h2>
      {children}
    </div>
  );
}

function Notices({ p, projectId, name }: { p: Pack; projectId: string; name?: string }) {
  const [showAll, setShowAll] = useState(false);
  const groups: [string, Notice[]][] = [
    ["Overdue", p.notices.filter((n) => n.bucket === "overdue")],
    ["Due this week", p.notices.filter((n) => n.bucket === "this_week")],
    ["Due next week", p.notices.filter((n) => n.bucket === "next_week")],
  ];
  return (
    <section>
      <H n={1} title="Notices" />
      {groups.map(([label, rows]) => {
        const limited = label === "Overdue" && !showAll ? rows.slice(0, 6) : rows;
        return (
          <div key={label} className="mt-4">
            <h3 className="text-xs font-medium uppercase tracking-wide text-neutral-400">{label} ({rows.length})</h3>
            {rows.length === 0 ? <p className="mt-1 text-[14px] text-neutral-400">None.</p> : (
              <ul className="mt-1">
                {limited.map((n) => (
                  <li key={n.event_id} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
                    <span className="w-28 shrink-0 tabular-nums">{fmtDate(n.due_date)}</span>
                    <span className="min-w-0 flex-1">
                      {cleanTitle(n.event_title, name)}
                      <span className="block text-[12.5px] text-neutral-500">
                        {n.event_ref} · clause {n.obligations.map((o) => o.clause_ref).join(", ")}{n.condition_precedent ? " · condition precedent" : ""}{n.draft_status ? ` · ${n.draft_status}` : ""}
                      </span>
                    </span>
                    <span className="w-44 shrink-0 text-right text-[12.5px]"><DuePhrase due={n.due_date} wd={n.working_days_remaining} /></span>
                    {n.review_item_id && <Link className="link shrink-0 text-[12.5px] text-neutral-500" href={`/projects/${projectId}/inbox?item=${n.review_item_id}`}>open</Link>}
                  </li>
                ))}
              </ul>
            )}
            {label === "Overdue" && rows.length > 6 && (
              <button className="link mt-1 text-[13px] text-neutral-500" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${rows.length}`}</button>
            )}
          </div>
        );
      })}
    </section>
  );
}

function NewSince({ p, projectId, name }: { p: Pack; projectId: string; name?: string }) {
  return (
    <section>
      <H n={2} title={p.previous_meeting ? `New since ${fmtDate(p.previous_meeting)}` : "New this week"} />
      {p.new_events.length === 0 && p.new_revisions.length === 0 && <p className="mt-3 text-[14px] text-neutral-400">Nothing new.</p>}
      <ul className="mt-2">
        {p.new_events.map((e) => (
          <li key={e.event_id} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
            <span className="w-28 shrink-0 tabular-nums text-neutral-500">{fmtDate(e.trigger_date)}</span>
            <span className="min-w-0 flex-1">{cleanTitle(e.title, name)}<span className="block text-[12.5px] text-neutral-500">{CATEGORY_LABEL[e.category]} · {e.ref} · {STATE[e.notice_state]}{e.next_due ? ` by ${fmtDate(e.next_due)}` : ""}</span></span>
            {e.review_item_id && <Link className="link shrink-0 text-[12.5px] text-neutral-500" href={`/projects/${projectId}/inbox?item=${e.review_item_id}`}>open</Link>}
          </li>
        ))}
        {p.new_revisions.map((r) => (
          <li key={r.id} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
            <span className="w-28 shrink-0 text-neutral-500">Revision</span>
            <span className="min-w-0 flex-1">{r.document.replace(/\.[a-z]+$/i, "")}<span className="block text-[12.5px] text-neutral-500">{r.possible_variations} possible variation{r.possible_variations === 1 ? "" : "s"}, {r.raised} raised{r.understated ? " · described as minor" : ""}</span></span>
            {r.review_item_id && <Link className="link shrink-0 text-[12.5px] text-neutral-500" href={`/projects/${projectId}/inbox?item=${r.review_item_id}`}>open</Link>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Estimate({ value, onSave, label }: { value: number | null; onSave: (v: number | null) => Promise<void>; label: string }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  if (!editing) {
    return <button aria-label={`Edit estimate for ${label}`} className={`tabular-nums ${value === null ? "text-neutral-300 hover:text-neutral-600" : "hover:underline"}`} onClick={() => { setText(value?.toString() ?? ""); setEditing(true); }}>{value === null ? "add" : eur(value)}</button>;
  }
  const save = async () => {
    const cleaned = text.replace(/[€,\s]/g, "");
    setBusy(true);
    await onSave(cleaned === "" ? null : Number(cleaned));
    setBusy(false);
    setEditing(false);
  };
  return (
    <span className="inline-flex items-center gap-1">
      <input autoFocus aria-label={`Estimate for ${label}`} className="w-24 rounded border border-neutral-300 px-1 py-0.5 text-right text-[13px] tabular-nums" value={text}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }} />
      <button className="text-[12px] text-neutral-700" disabled={busy || (text !== "" && isNaN(Number(text.replace(/[€,\s]/g, ""))))} onClick={save}>Save</button>
    </span>
  );
}

function Register({ p, projectId, name, onSaved }: { p: Pack; projectId: string; name?: string; onSaved: () => void }) {
  const [onlyOpen, setOnlyOpen] = useState(true);
  const rows = p.register.filter((r) => !onlyOpen || r.status === "open");
  const t = p.totals;
  const saveEvent = (eventId: string) => async (v: number | null) => {
    await api(`/events/${eventId}/estimate`, { method: "PATCH", json: { estimated_value: v } });
    onSaved();
  };
  const saveClaim = (claimId: string) => async (v: number | null) => {
    await api(`/claims/${claimId}/estimate`, { method: "PATCH", json: { estimated_value: v } });
    onSaved();
  };
  return (
    <section>
      <H n={3} title="Change and claims register">
        <label className="flex items-center gap-1.5 text-[13px] text-neutral-500"><input type="checkbox" className="accent-neutral-800" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> open events only</label>
      </H>
      <p className="mt-3 text-[14px] text-neutral-600">
        Estimated {eur(t.all)} — notified {eur(t.notified)}, not yet notified {eur(t.not_notified)}
        {t.time_bar_risk > 0 && <>, <span className="text-red-600">at time-bar risk {eur(t.time_bar_risk)}</span></>}.
        {" "}{t.unpriced_events} event{t.unpriced_events === 1 ? "" : "s"} not estimated yet. QS estimates, excl. VAT; click a value to change it.
      </p>
      <table className="mt-2 w-full">
        <thead><tr><th className="th">Event</th><th className="th">Notice</th><th className="th text-right">Estimate</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.event_id}>
              <td className="td">
                {cleanTitle(r.title, name)}
                <div className="text-xs text-neutral-400">{r.ref} · {CATEGORY_LABEL[r.category]}{r.claim_ref ? ` · in ${r.claim_ref}` : ""}{r.value_note ? ` · ${r.value_note}` : ""}</div>
              </td>
              <td className="td w-48 text-[13px]">
                <span className={r.time_bar_risk ? "text-red-600" : "text-neutral-600"}>{STATE[r.notice_state]}</span>
                {r.time_bar_risk && <div className="text-xs text-red-600">time-bar risk</div>}
              </td>
              <td className="td w-40 text-right"><Estimate value={r.estimated_value} onSave={saveEvent(r.event_id)} label={r.ref} /></td>
            </tr>
          ))}
          <tr><td className="td font-medium" colSpan={2}>Total (all events)</td><td className="td text-right font-medium tabular-nums">{eur(t.all)}</td></tr>
        </tbody>
      </table>
      {p.claims.length > 0 && (
        <>
          <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-neutral-400">Claims</h3>
          <table className="mt-1 w-full">
            <tbody>
              {p.claims.map((c) => (
                <tr key={c.id}>
                  <td className="td">
                    {c.review_item_id ? <Link className="link" href={`/projects/${projectId}/inbox?item=${c.review_item_id}`}>{c.ref} {c.title}</Link> : `${c.ref} ${c.title}`}
                    <div className="text-xs text-neutral-400">events {c.events.join(", ")}{c.events_estimate !== null ? ` · events estimated at ${eur(c.events_estimate)}` : ""}</div>
                  </td>
                  <td className="td w-48 text-[13px]">{c.time_bar_risk ? <span className="text-red-600">Time-bar risk</span> : <span className="text-neutral-600">{c.status}</span>}</td>
                  <td className="td w-40 text-right"><Estimate value={c.estimated_value} onSave={saveClaim(c.id)} label={c.ref} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function Actions({ p, projectId, onChanged }: { p: Pack; projectId: string; onChanged: () => void }) {
  const [form, setForm] = useState({ kind: "action", text: "", owner: "", due_date: "" });
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`/projects/${projectId}/meeting-items`, { method: "POST", json: {
        kind: form.kind, text: form.text, owner: form.owner || null, due_date: form.kind === "action" && form.due_date ? form.due_date : null, meeting_date: p.meeting_date } });
      setForm({ ...form, text: "", owner: "", due_date: "" });
      onChanged();
    } catch (err: any) {
      setError(err.message);
    }
  }
  async function close(item: Item) {
    await api(`/meeting-items/${item.id}`, { method: "PATCH", json: { status: "done", closed_on: p.meeting_date } });
    onChanged();
  }

  return (
    <section>
      <H n={4} title="Decisions and actions" />
      <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-neutral-400">Actions carried forward ({p.actions_open.length})</h3>
      {p.actions_open.length === 0 ? <p className="mt-1 text-[14px] text-neutral-400">None open.</p> : (
        <ul className="mt-1">
          {p.actions_open.map((a) => (
            <li key={a.id} className="flex items-baseline gap-3 border-b border-neutral-100 py-2 text-[14.5px]">
              <input type="checkbox" className="accent-neutral-800" aria-label={`Mark done: ${a.text}`} onChange={() => close(a)} />
              <span className="min-w-0 flex-1">{a.text}<span className="block text-[12.5px] text-neutral-500">{a.owner ?? "no owner"} · raised {fmtDate(a.meeting_date)}</span></span>
              <span className={`shrink-0 text-[12.5px] ${a.overdue ? "text-red-600" : "text-neutral-500"}`}>{a.due_date ? `due ${fmtDate(a.due_date)}` : "no due date"}</span>
            </li>
          ))}
        </ul>
      )}
      {p.actions_closed.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-neutral-400">Closed since the last meeting</h3>
          <ul className="mt-1">{p.actions_closed.map((a) => <li key={a.id} className="py-1 text-[14px] text-neutral-400 line-through">{a.text} — {a.owner}</li>)}</ul>
        </>
      )}
      {p.previous_decisions.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-neutral-400">Decided at the last meeting ({fmtDate(p.previous_meeting)})</h3>
          <ul className="mt-1 list-disc pl-5">{p.previous_decisions.map((d) => <li key={d.id} className="py-0.5 text-[14px] text-neutral-600">{d.text}</li>)}</ul>
        </>
      )}
      <h3 className="mt-6 text-xs font-medium uppercase tracking-wide text-neutral-400">This meeting</h3>
      {p.decisions.length > 0 && <ul className="mt-1 list-disc pl-5">{p.decisions.map((d) => <li key={d.id} className="py-0.5 text-[14.5px]">{d.text}</li>)}</ul>}
      <form onSubmit={add} className="mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
        <select aria-label="Decision or action" className="rounded-md border border-neutral-200 bg-white px-2 py-1" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          <option value="action">Action</option><option value="decision">Decision</option>
        </select>
        <input className="min-w-[260px] flex-1 rounded-md border border-neutral-200 px-2 py-1" placeholder={form.kind === "action" ? "What needs doing" : "What was decided"} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} required minLength={2} />
        {form.kind === "action" && (
          <>
            <input className="w-36 rounded-md border border-neutral-200 px-2 py-1" placeholder="Owner" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} />
            <input type="date" aria-label="Action due date" className="rounded-md border border-neutral-200 px-2 py-1" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          </>
        )}
        <button className="btn-primary">Add</button>
      </form>
      <ErrorBox error={error} />
    </section>
  );
}
