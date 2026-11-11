"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, download, ReviewItemT } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { CategoryBadge, Confidence, DaysLeft, Empty, ErrorBox, StatusPill } from "@/components/ui";
import { SourcePassage } from "@/components/SourcePassage";
import { useProject } from "@/components/project-context";

const CATS = ["", "change", "delay", "instruction", "disruption", "noise"];

function Inbox() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const { reload: reloadProject } = useProject();
  const [status, setStatus] = useState("pending");
  const [category, setCategory] = useState("");
  const [lowOnly, setLowOnly] = useState(params.get("low") === "1");
  const [items, setItems] = useState<ReviewItemT[] | null>(null);
  const [selected, setSelected] = useState<string | null>(params.get("item"));

  const load = useCallback(() => {
    const q = new URLSearchParams({ status });
    if (category) q.set("category", category);
    if (lowOnly) q.set("low_confidence", "true");
    api<ReviewItemT[]>(`/projects/${id}/review?${q}`).then((rows) => {
      setItems(rows);
      setSelected((cur) => cur ?? rows[0]?.id ?? null);
    });
  }, [id, status, category, lowOnly]);
  useEffect(load, [load]);

  return (
    <div className="flex h-screen">
      <section className="flex w-[380px] shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="space-y-2 border-b border-slate-200 p-2">
          <div className="flex items-center justify-between">
            <h1 className="text-sm font-semibold">Review queue</h1>
            <span className="text-2xs text-slate-500">{items?.length ?? 0} items</span>
          </div>
          <div className="flex gap-1">
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="pending">Pending</option><option value="approved">Approved</option><option value="dismissed">Dismissed</option><option value="all">All</option>
            </select>
            <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATS.map((c) => <option key={c} value={c}>{c || "All categories"}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-1.5 text-2xs text-slate-600"><input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} /> Low confidence only</label>
        </div>
        <div className="flex-1 overflow-auto">
          {items === null ? <Empty>Loading…</Empty> : items.length === 0 ? <Empty>Nothing here.</Empty> : items.map((it) => (
            <button key={it.id} onClick={() => setSelected(it.id)}
              className={`block w-full border-b border-slate-100 px-2.5 py-2 text-left ${selected === it.id ? "bg-sky-50" : "hover:bg-slate-50"} ${it.low_confidence ? "border-l-2 border-l-amber-400" : "border-l-2 border-l-transparent"}`}>
              <div className="flex items-center gap-1.5">
                <CategoryBadge category={it.category} />
                <span className="text-2xs text-slate-400">{it.payload?.event_ref}</span>
                <span className="ml-auto"><Confidence value={it.confidence} low={it.low_confidence} /></span>
              </div>
              <div className="mt-1 line-clamp-2 text-xs font-medium leading-snug">{it.title}</div>
              <div className="mt-0.5 flex justify-between text-2xs text-slate-500">
                <span>{it.payload?.source?.channel} · {fmtDate(it.payload?.source?.timestamp)}</span>
                {it.priority_date && <span>notice due <b className="text-slate-700">{fmtDate(it.priority_date)}</b></span>}
              </div>
            </button>
          ))}
        </div>
      </section>
      <section className="min-w-0 flex-1 overflow-auto">
        {selected ? <Detail key={selected} reviewId={selected} projectId={id} onChange={() => { load(); reloadProject(); }} /> : <Empty>Select an item.</Empty>}
      </section>
    </div>
  );
}

function Detail({ reviewId, projectId, onChange }: { reviewId: string; projectId: string; onChange: () => void }) {
  const [r, setR] = useState<ReviewItemT | null>(null);
  const [draft, setDraft] = useState({ subject: "", recipient: "", body: "" });
  const [trigger, setTrigger] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const apply = (x: ReviewItemT) => {
    setR(x);
    if (x.draft) setDraft({ subject: x.draft.subject, recipient: x.draft.recipient ?? "", body: x.draft.body });
    setTrigger(x.event?.trigger_date ?? "");
  };
  useEffect(() => {
    api<ReviewItemT>(`/review/${reviewId}`).then(apply).catch((e) => setError(e.message));
  }, [reviewId]);

  if (!r) return <div className="p-4"><ErrorBox error={error} />{!error && <Empty>Loading…</Empty>}</div>;
  const pending = r.status === "pending";
  const dirty = !!r.draft && (draft.subject !== r.draft.subject || draft.body !== r.draft.body || draft.recipient !== (r.draft.recipient ?? ""));
  const triggerDirty = !!r.event && trigger !== r.event.trigger_date;

  async function act(path: string, json: object = {}) {
    setBusy(true);
    setError(null);
    try {
      apply(await api<ReviewItemT>(`/review/${reviewId}/${path}`, { method: "POST", json: { comment: comment || null, ...json } }));
      setComment("");
      onChange();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const save = () => act("edit", { ...(dirty ? draft : {}), ...(triggerDirty ? { trigger_date: trigger } : {}) });
  const approve = async () => {
    if (dirty || triggerDirty) await save();
    await act("approve");
  };
  const issues: string[] = r.payload?.verification?.issues ?? [];
  const cls = r.payload?.classification;
  const msgCites = r.citations.filter((c) => !c.clause_ref);
  const clauseCites = r.citations.filter((c) => c.clause_ref);

  return (
    <div className="space-y-3 p-4">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <CategoryBadge category={r.category} />
          <Confidence value={r.confidence} low={r.low_confidence} />
          <StatusPill status={r.status} />
          {r.event && <span className="text-2xs text-slate-500">{r.payload?.event_ref} · event {r.event.status}</span>}
          <span className="ml-auto text-2xs text-slate-400">{r.agent} · {fmtDateTime(r.created_at)}</span>
        </div>
        <h2 className="text-base font-semibold leading-snug">{r.title}</h2>
        <p className="text-xs text-slate-600">{r.summary}</p>
        {cls?.secondary_categories?.length > 0 && <p className="text-2xs text-slate-500">Also: {cls.secondary_categories.join(", ")}</p>}
      </header>

      {r.low_confidence && (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <b>Low confidence.</b> Check the classification, the linked clause and the awareness date against the source before approving.
          {issues.length > 0 && <ul className="mt-1 list-disc pl-4 text-2xs">{issues.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        </div>
      )}
      {!r.low_confidence && issues.length > 0 && (
        <details className="text-2xs text-slate-500"><summary>Verification notes ({issues.length})</summary><ul className="list-disc pl-4">{issues.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
      )}
      <ErrorBox error={error} />

      <div className="grid gap-3 xl:grid-cols-2">
        {/* left: evidence */}
        <div className="space-y-3">
          <section className="space-y-1.5">
            <h3 className="label">Triggering message</h3>
            {r.source_item && (
              <div className="text-2xs text-slate-500">{r.source_item.author} · {r.source_item.kind} · {fmtDateTime(r.source_item.timestamp)}{r.source_item.subject ? ` · ${r.source_item.subject}` : ""}</div>
            )}
            {msgCites.length === 0 && <div className="text-2xs text-amber-700">No verified quote from the message.</div>}
            {msgCites.map((c, i) => <SourcePassage key={i} citation={c} projectId={projectId} />)}
            {(r.related_items?.length ?? 0) > 1 && (
              <details className="text-2xs text-slate-600">
                <summary>{r.related_items!.length - 1} further message(s) linked to this event</summary>
                {r.related_items!.filter((x) => x.id !== r.source_item_id).map((x) => (
                  <div key={x.id} className="mt-1 rounded border border-slate-200 bg-white p-1.5"><b>{x.author}</b> {fmtDateTime(x.timestamp)}<div className="whitespace-pre-wrap">{x.text}</div></div>
                ))}
              </details>
            )}
          </section>

          <section className="space-y-1.5">
            <h3 className="label">Contract clauses relied on</h3>
            {(r.payload?.rules ?? []).length === 0 && <div className="text-2xs text-amber-700">No approved clause linked.</div>}
            {clauseCites.map((c, i) => <SourcePassage key={i} citation={c} projectId={projectId} context={120} />)}
          </section>

          <section className="space-y-1.5">
            <h3 className="label">Deadlines (computed by the deadline engine)</h3>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-600">Contractor aware on</span>
              <input type="date" className="input w-36" value={trigger} disabled={!pending} onChange={(e) => setTrigger(e.target.value)} />
              {triggerDirty && <span className="text-2xs text-amber-700">save to recompute</span>}
            </div>
            {cls?.trigger_date_basis && <div className="text-2xs text-slate-500">Basis: {cls.trigger_date_basis}</div>}
            <div className="card divide-y divide-slate-100">
              {(r.deadlines ?? []).map((d) => (
                <div key={d.id} className="px-2 py-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{d.label}</span>
                    <span className="flex items-center gap-2"><b className="tabular-nums">{fmtDate(d.due_date)}</b><StatusPill status={d.status} /></span>
                  </div>
                  <div className="text-2xs text-slate-500">{d.trace.explanation}</div>
                  {d.trace.skipped.filter((s) => !s.reason.startsWith("weekend")).length > 0 && (
                    <div className="text-2xs text-slate-500">Skipped: {d.trace.skipped.filter((s) => !s.reason.startsWith("weekend")).map((s) => `${fmtDate(s.date)} (${s.reason})`).join(", ")}</div>
                  )}
                </div>
              ))}
              {(r.deadlines ?? []).length === 0 && <div className="px-2 py-1.5 text-2xs text-slate-500">No deadline (no linked rule with a fixed period).</div>}
            </div>
          </section>
        </div>

        {/* right: draft */}
        <div className="space-y-2">
          <h3 className="label">Draft notice {r.draft ? `· v${r.draft.version} · ${r.draft.status}` : ""}</h3>
          {r.draft ? (
            <div className="card space-y-2 p-2">
              <label className="block space-y-0.5"><span className="label">To</span><input className="input" value={draft.recipient} disabled={!pending} onChange={(e) => setDraft({ ...draft, recipient: e.target.value })} /></label>
              <label className="block space-y-0.5"><span className="label">Subject</span><input className="input font-medium" value={draft.subject} disabled={!pending} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} /></label>
              <textarea className="input h-[420px] font-serif text-[12.5px] leading-relaxed" value={draft.body} disabled={!pending} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            </div>
          ) : <Empty>No draft for this item.</Empty>}

          <input className="input" placeholder="Comment (logged with your decision)" value={comment} onChange={(e) => setComment(e.target.value)} />
          <div className="flex flex-wrap gap-1.5">
            {pending && (
              <>
                <button className="btn-primary" disabled={busy} onClick={approve}>{r.draft ? "Approve draft" : "Confirm"}</button>
                <button className="btn" disabled={busy || (!dirty && !triggerDirty)} onClick={save}>Save edits</button>
                <button className="btn-danger" disabled={busy} onClick={() => act("dismiss")}>Dismiss</button>
              </>
            )}
            {!pending && <button className="btn" disabled={busy} onClick={() => act("reopen")}>Reopen</button>}
            {r.status === "approved" && r.draft && (
              <>
                <button className="btn" onClick={() => download(`/drafts/${r.draft!.id}/export?format=docx`, `${r.draft!.subject}.docx`).catch((e) => setError(e.message))}>Export DOCX</button>
                <button className="btn" onClick={() => download(`/drafts/${r.draft!.id}/export?format=pdf`, `${r.draft!.subject}.pdf`).catch((e) => setError(e.message))}>Export PDF</button>
                {r.event?.status !== "notified" && <button className="btn" disabled={busy} onClick={() => act("mark-issued", { issued_on: new Date().toISOString().slice(0, 10) })}>Mark as issued today</button>}
              </>
            )}
          </div>
          <p className="text-2xs text-slate-500">Notice never sends anything. Export the approved draft and send it from your own email, then mark it issued to stop the clock.</p>
          {(r.actions?.length ?? 0) > 0 && (
            <div className="text-2xs text-slate-500">
              <div className="label">History</div>
              {r.actions!.map((a, i) => <div key={i}>{fmtDateTime(a.created_at)} · {a.action}{a.comment ? ` — ${a.comment}` : ""}</div>)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function InboxPage() {
  return <Suspense><Inbox /></Suspense>;
}
