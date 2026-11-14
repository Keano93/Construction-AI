"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, download } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CATEGORY_LABEL, cleanTitle } from "@/lib/text";
import { DuePhrase } from "@/components/inbox/doc";
import { BarList, ChartCard, Columns, MiniTable } from "@/components/charts";
import { ErrorBox } from "@/components/ui";
import { useProject } from "@/components/project-context";

type Notice = {
  event_id: string; event_ref: string; event_title: string; due_date: string; working_days_remaining: number;
  bucket: "overdue" | "next_5" | "next_10"; condition_precedent: boolean; draft_status: string | null; review_item_id: string | null;
  obligations: { clause_ref: string }[];
};
type Reg = {
  event_id: string; ref: string; category: string; title: string; trigger_date: string; status: string; notice_state: string;
  next_due: string | null; time_bar_risk: boolean; estimated_value: number | null; value_note: string | null; claim_ref: string | null; review_item_id: string | null;
};
type ClaimRow = { id: string; ref: string; title: string; status: string; created_on: string; new_in_period: boolean; events: string[]; time_bar_risk: boolean; estimated_value: number | null; events_estimate: number | null; review_item_id: string | null };
type Pack = {
  from: string; to: string;
  summary: Record<string, number>;
  notices: Notice[];
  issued: { event_id: string; event_ref: string; event_title: string; clause_ref: string; issued_on: string; due_date: string; in_time: boolean }[];
  new_events: Reg[];
  new_revisions: { id: string; document: string; compared_on: string; possible_variations: number; raised: number; understated: boolean; review_item_id: string | null }[];
  weekly: { week_start: string; count: number; by_category: Record<string, number> }[];
  register: Reg[]; claims: ClaimRow[];
  totals: { by_category: Record<string, number>; all: number; notified: number; not_notified: number; time_bar_risk: number; unpriced_events: number };
  notice_position: Record<string, number>;
};
type Preset = "7" | "14" | "30" | "custom";

const eur = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `€${Math.round(v).toLocaleString("en-IE")}`);
const STATE: Record<string, string> = { issued: "Notified", overdue: "Notice overdue", open: "Notice due", none: "No notice clock" };
const iso = (d: Date) => d.toISOString().slice(0, 10);
const daysBefore = (to: string, n: number) => iso(new Date(new Date(`${to}T12:00:00`).getTime() - (n - 1) * 86400000));

export default function CommercialPack() {
  const { id } = useParams<{ id: string }>();
  const { project } = useProject();
  const [to, setTo] = useState(iso(new Date()));
  const [from, setFrom] = useState(daysBefore(iso(new Date()), 7));
  const [preset, setPreset] = useState<Preset>("7");
  const [pack, setPack] = useState<Pack | null>(null);
  const [loading, setLoading] = useState(false);
  const [present, setPresent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api<Pack>(`/projects/${id}/pack?from=${from}&to=${to}`).then(setPack).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [id, from, to]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    document.body.dataset.present = present ? "1" : "";
    return () => { document.body.dataset.present = ""; };
  }, [present]);

  const choose = (p: Preset) => {
    setPreset(p);
    if (p !== "custom") setFrom(daysBefore(to, Number(p)));
  };
  const name = project?.name;
  const exportAs = (fmt: string) =>
    download(`/projects/${id}/pack/export?format=${fmt}&from=${from}&to=${to}`, `Commercial pack ${name ?? ""} ${from} to ${to}.${fmt}`).catch((e) => setError(e.message));

  return (
    <div className="h-screen overflow-auto">
      <div className="present-scale mx-auto max-w-5xl px-8 pb-24 pt-7">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[26px] font-semibold tracking-tight text-neutral-900">Commercial pack</h1>
            <p className="text-[14px] text-neutral-500">{name} · {fmtDate(from)} to {fmtDate(to)} · built from the project record</p>
          </div>
          <div className="flex shrink-0 items-center gap-3 text-[13px]">
            <button className="text-neutral-600 hover:text-neutral-900" onClick={() => exportAs("pdf")}>PDF</button>
            <button className="text-neutral-600 hover:text-neutral-900" onClick={() => exportAs("docx")}>Word</button>
            <button className="btn" onClick={() => setPresent(!present)}>{present ? "Exit present" : "Present"}</button>
          </div>
        </header>

        {/* one filter row, above everything it scopes */}
        <div className="mt-5 flex flex-wrap items-center gap-2 text-[13px]">
          {([["7", "Last 7 days"], ["14", "Last 14 days"], ["30", "Last 30 days"], ["custom", "Custom"]] as [Preset, string][]).map(([v, t]) => (
            <button key={v} onClick={() => choose(v)} className={`rounded-md px-2.5 py-1 ${preset === v ? "bg-neutral-200/70 text-neutral-900" : "text-neutral-500 hover:text-neutral-900"}`}>{t}</button>
          ))}
          <span className="ml-2 inline-flex items-center gap-1.5 text-neutral-500">
            <input type="date" aria-label="From" className="rounded-md border border-neutral-200 bg-white px-2 py-0.5" value={from} max={to}
              onChange={(e) => { if (e.target.value) { setFrom(e.target.value); setPreset("custom"); } }} />
            to
            <input type="date" aria-label="To" className="rounded-md border border-neutral-200 bg-white px-2 py-0.5" value={to} min={from}
              onChange={(e) => { if (e.target.value) { setTo(e.target.value); if (preset !== "custom") setFrom(daysBefore(e.target.value, Number(preset))); } }} />
          </span>
        </div>
        <ErrorBox error={error} />

        {!pack ? <p className="mt-8 text-sm text-neutral-400">Loading…</p> : (
          <div className={`transition-opacity ${loading ? "opacity-60" : ""}`}>
            <Headline p={pack} />
            <Charts p={pack} />
            <NoticesSection p={pack} projectId={id} name={name} />
            <IssuedSection p={pack} name={name} />
            <NewSection p={pack} projectId={id} name={name} />
            <Register p={pack} projectId={id} name={name} onSaved={load} />
          </div>
        )}
      </div>
    </div>
  );
}

function Headline({ p }: { p: Pack }) {
  const s = p.summary;
  const tiles: [string, string, boolean][] = [
    ["Notices overdue", String(s.notices_overdue), s.notices_overdue > 0],
    ["Due in 10 working days", String(s.notices_next_5 + s.notices_next_10), false],
    ["Notices issued", String(s.notices_issued), false],
    ["New events", String(s.new_events), false],
    ["Estimated value", eur(s.estimated_total), false],
    ["At time-bar risk", eur(s.time_bar_risk), s.time_bar_risk > 0],
  ];
  return (
    <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-neutral-200 ring-1 ring-neutral-200 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map(([label, value, red]) => (
        <div key={label} className="bg-white px-4 py-3">
          <dt className="text-xs text-neutral-500">{label}</dt>
          <dd className={`mt-0.5 text-[22px] font-semibold ${red ? "text-red-600" : "text-neutral-900"}`}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Charts({ p }: { p: Pack }) {
  const weeks = p.weekly.map((w) => ({
    key: w.week_start, label: new Date(`${w.week_start}T12:00:00`).toLocaleDateString("en-IE", { day: "numeric", month: "short" }), value: w.count,
    detail: `week of ${fmtDate(w.week_start)}${w.count ? " · " + Object.entries(w.by_category).filter(([, n]) => n).map(([c, n]) => `${n} ${c}`).join(", ") : ""}`,
  }));
  const pos = p.notice_position;
  const position = [
    { key: "overdue", label: "Notice overdue", value: pos.overdue, urgent: true },
    { key: "open", label: "Notice due", value: pos.open },
    { key: "issued", label: "Notified", value: pos.issued },
    { key: "none", label: "No notice clock", value: pos.none },
  ];
  const values = Object.entries(p.totals.by_category).sort((a, b) => b[1] - a[1]).map(([c, v]) => ({ key: c, label: CATEGORY_LABEL[c], value: v }));
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-3">
      <ChartCard title="Events found per week" subtitle={`${fmtDate(p.from)} to ${fmtDate(p.to)}`}
        table={<MiniTable head={["Week of", "Events"]} rows={p.weekly.map((w) => [fmtDate(w.week_start), w.count])} />}>
        <Columns data={weeks} label="Events found per week" unit="event" />
      </ChartCard>
      <ChartCard title="Notice position" subtitle={`Open events at ${fmtDate(p.to)}`}
        table={<MiniTable head={["Position", "Events"]} rows={position.map((r) => [r.label, r.value])} />}>
        <BarList rows={position} />
      </ChartCard>
      <ChartCard title="Estimated value by type" subtitle={`QS estimates, excl. VAT · ${p.totals.unpriced_events} not estimated`}
        table={<MiniTable head={["Type", "Estimate"]} rows={values.map((r) => [r.label, eur(r.value)])} />}>
        <BarList rows={values} format={(v) => (v ? eur(v) : "—")} />
      </ChartCard>
    </div>
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

const Sub = ({ children }: { children: React.ReactNode }) => <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-neutral-400">{children}</h3>;
const None = () => <p className="mt-1 text-[14px] text-neutral-400">None.</p>;

function NoticesSection({ p, projectId, name }: { p: Pack; projectId: string; name?: string }) {
  const [showAll, setShowAll] = useState(false);
  const groups: [string, Notice[]][] = [
    ["Overdue", p.notices.filter((n) => n.bucket === "overdue")],
    ["Due within 5 working days", p.notices.filter((n) => n.bucket === "next_5")],
    ["Due within 10 working days", p.notices.filter((n) => n.bucket === "next_10")],
  ];
  return (
    <section>
      <H n={1} title={`Notices at ${fmtDate(p.to)}`} />
      {groups.map(([label, rows]) => {
        const shown = label === "Overdue" && !showAll ? rows.slice(0, 6) : rows;
        return (
          <div key={label}>
            <Sub>{label} ({rows.length})</Sub>
            {rows.length === 0 ? <None /> : (
              <ul className="mt-1">
                {shown.map((n) => (
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
            {label === "Overdue" && rows.length > 6 && <button className="link mt-1 text-[13px] text-neutral-500" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${rows.length}`}</button>}
          </div>
        );
      })}
    </section>
  );
}

function IssuedSection({ p, name }: { p: Pack; name?: string }) {
  return (
    <section>
      <H n={2} title="Notices issued in the period" />
      {p.issued.length === 0 ? <None /> : (
        <ul className="mt-2">
          {p.issued.map((i, k) => (
            <li key={k} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
              <span className="w-28 shrink-0 tabular-nums">{fmtDate(i.issued_on)}</span>
              <span className="min-w-0 flex-1">{cleanTitle(i.event_title, name)}<span className="block text-[12.5px] text-neutral-500">{i.event_ref} · clause {i.clause_ref} · was due {fmtDate(i.due_date)}</span></span>
              <span className={`shrink-0 text-[12.5px] ${i.in_time ? "text-neutral-500" : "text-red-600"}`}>{i.in_time ? "In time" : "Late"}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NewSection({ p, projectId, name }: { p: Pack; projectId: string; name?: string }) {
  const claims = p.claims.filter((c) => c.new_in_period);
  const open = (rid: string | null) => rid && <Link className="link shrink-0 text-[12.5px] text-neutral-500" href={`/projects/${projectId}/inbox?item=${rid}`}>open</Link>;
  return (
    <section>
      <H n={3} title="New in the period" />
      {p.new_events.length + p.new_revisions.length + claims.length === 0 && <None />}
      <ul className="mt-2">
        {p.new_events.map((e) => (
          <li key={e.event_id} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
            <span className="w-28 shrink-0 tabular-nums text-neutral-500">{fmtDate(e.trigger_date)}</span>
            <span className="min-w-0 flex-1">{cleanTitle(e.title, name)}<span className="block text-[12.5px] text-neutral-500">{CATEGORY_LABEL[e.category]} · {e.ref} · {STATE[e.notice_state]}{e.next_due ? ` by ${fmtDate(e.next_due)}` : ""}</span></span>
            {open(e.review_item_id)}
          </li>
        ))}
        {p.new_revisions.map((r) => (
          <li key={r.id} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
            <span className="w-28 shrink-0 tabular-nums text-neutral-500">{fmtDate(r.compared_on)}</span>
            <span className="min-w-0 flex-1">{r.document.replace(/\.[a-z]+$/i, "")}<span className="block text-[12.5px] text-neutral-500">Drawing revision · {r.possible_variations} possible variation{r.possible_variations === 1 ? "" : "s"}, {r.raised} raised{r.understated ? " · described as minor" : ""}</span></span>
            {open(r.review_item_id)}
          </li>
        ))}
        {claims.map((c) => (
          <li key={c.id} className="flex items-baseline gap-4 border-b border-neutral-100 py-2 text-[14.5px]">
            <span className="w-28 shrink-0 tabular-nums text-neutral-500">{fmtDate(c.created_on)}</span>
            <span className="min-w-0 flex-1">{c.ref} {c.title}<span className="block text-[12.5px] text-neutral-500">Claim · events {c.events.join(", ")}{c.time_bar_risk ? " · time-bar risk" : ""}</span></span>
            {open(c.review_item_id)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Estimate({ value, onSave, label }: { value: number | null; onSave: (v: number | null) => Promise<void>; label: string }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const parsed = text.replace(/[€,\s]/g, "");
  const invalid = parsed !== "" && (isNaN(Number(parsed)) || Number(parsed) < 0);
  if (!editing) {
    return <button aria-label={`Edit estimate for ${label}`} className={`tabular-nums ${value === null ? "text-neutral-300 hover:text-neutral-600" : "hover:underline"}`}
      onClick={() => { setText(value?.toString() ?? ""); setEditing(true); }}>{value === null ? "add" : eur(value)}</button>;
  }
  const save = async () => {
    if (invalid) return;
    setBusy(true);
    await onSave(parsed === "" ? null : Number(parsed));
    setBusy(false);
    setEditing(false);
  };
  return (
    <span className="inline-flex items-center gap-1">
      <input autoFocus aria-label={`Estimate for ${label}`} className="w-24 rounded border border-neutral-300 px-1 py-0.5 text-right text-[13px] tabular-nums" value={text}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }} />
      <button className="text-[12px] text-neutral-700" disabled={busy || invalid} onClick={save}>Save</button>
    </span>
  );
}

function Register({ p, projectId, name, onSaved }: { p: Pack; projectId: string; name?: string; onSaved: () => void }) {
  const [onlyOpen, setOnlyOpen] = useState(true);
  const rows = p.register.filter((r) => !onlyOpen || r.status === "open");
  const t = p.totals;
  const save = (path: string) => async (v: number | null) => {
    await api(path, { method: "PATCH", json: { estimated_value: v } });
    onSaved();
  };
  return (
    <section>
      <H n={4} title={`Change and claims register at ${fmtDate(p.to)}`}>
        <label className="flex items-center gap-1.5 text-[13px] text-neutral-500"><input type="checkbox" className="accent-neutral-800" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> open events only</label>
      </H>
      <p className="mt-3 text-[14px] text-neutral-600">
        Estimated {eur(t.all)} — notified {eur(t.notified)}, not yet notified {eur(t.not_notified)}
        {t.time_bar_risk > 0 && <>, <span className="text-red-600">at time-bar risk {eur(t.time_bar_risk)}</span></>}.
        {" "}{t.unpriced_events} event{t.unpriced_events === 1 ? "" : "s"} not estimated yet. Click a value to change it.
      </p>
      <table className="mt-2 w-full">
        <thead><tr><th className="th">Event</th><th className="th">Notice</th><th className="th text-right">Estimate</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.event_id}>
              <td className="td">{cleanTitle(r.title, name)}<div className="text-xs text-neutral-400">{r.ref} · {CATEGORY_LABEL[r.category]}{r.claim_ref ? ` · in ${r.claim_ref}` : ""}{r.value_note ? ` · ${r.value_note}` : ""}</div></td>
              <td className="td w-48 text-[13px]"><span className={r.time_bar_risk ? "text-red-600" : "text-neutral-600"}>{STATE[r.notice_state]}</span>{r.time_bar_risk && <div className="text-xs text-red-600">time-bar risk</div>}</td>
              <td className="td w-40 text-right"><Estimate value={r.estimated_value} onSave={save(`/events/${r.event_id}/estimate`)} label={r.ref} /></td>
            </tr>
          ))}
          <tr><td className="td font-medium" colSpan={2}>Total (all events)</td><td className="td text-right font-medium tabular-nums">{eur(t.all)}</td></tr>
        </tbody>
      </table>
      {p.claims.length > 0 && (
        <>
          <Sub>Claims</Sub>
          <table className="mt-1 w-full"><tbody>
            {p.claims.map((c) => (
              <tr key={c.id}>
                <td className="td">
                  {c.review_item_id ? <Link className="link" href={`/projects/${projectId}/inbox?item=${c.review_item_id}`}>{c.ref} {c.title}</Link> : `${c.ref} ${c.title}`}
                  <div className="text-xs text-neutral-400">events {c.events.join(", ")}{c.events_estimate !== null ? ` · events estimated at ${eur(c.events_estimate)}` : ""}</div>
                </td>
                <td className="td w-48 text-[13px]">{c.time_bar_risk ? <span className="text-red-600">Time-bar risk</span> : <span className="text-neutral-600">{c.status}</span>}</td>
                <td className="td w-40 text-right"><Estimate value={c.estimated_value} onSave={save(`/claims/${c.id}/estimate`)} label={c.ref} /></td>
              </tr>
            ))}
          </tbody></table>
        </>
      )}
    </section>
  );
}
