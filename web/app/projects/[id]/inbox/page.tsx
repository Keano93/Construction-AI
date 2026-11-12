"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { api, download, ReviewItemT } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CATEGORY_LABEL, cleanTitle } from "@/lib/text";
import { useProject } from "@/components/project-context";
import { DuePhrase, HighlightedText, Margin, Note, Section, sourceLabel, urgent } from "@/components/inbox/doc";
import { claimNotes, noticeNotes, revisionNotes, RevisionChanges } from "@/components/inbox/kinds";

type Row = ReviewItemT & { working_days_remaining: number | null };

function listTitle(r: Row, project?: string) {
  if (r.kind === "revision_comparison") {
    const c = r.payload?.counts;
    return `${r.payload?.revised?.filename?.replace(/\.[a-z]+$/i, "")}: ${c?.potential_variations ?? 0} possible variation${c?.potential_variations === 1 ? "" : "s"}`;
  }
  if (r.kind === "claim_draft") return `Claim ${r.payload?.claim_ref}: ${cleanTitle(r.title.replace(/^Claim CL-\d+:\s*/, ""), project)}`;
  return cleanTitle(r.title, project);
}

function Inbox() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const { project, reload: reloadProject } = useProject();
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState<Row[] | null>(null);
  const selected = params.get("item");

  const select = useCallback((itemId: string | null) => {
    router.replace(itemId ? `/projects/${id}/inbox?item=${itemId}` : `/projects/${id}/inbox`, { scroll: false });
  }, [id, router]);

  const load = useCallback(() => {
    api<Row[]>(`/projects/${id}/review?status=${status}`).then((rows) => {
      setItems(rows);
      if (!selected && rows[0]) select(rows[0].id);
    });
  }, [id, status, selected, select]);
  useEffect(load, [id, status]); // eslint-disable-line react-hooks/exhaustive-deps

  const index = items?.findIndex((x) => x.id === selected) ?? -1;
  const next = () => items && items.length && select(items[Math.min(index + 1, items.length - 1)].id);
  const prev = () => items && items.length && select(items[Math.max(index - 1, 0)].id);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, select")) return;
      if (e.key === "j") next();
      if (e.key === "k") prev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="flex h-screen bg-neutral-50">
      <section className="flex w-[320px] shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="flex items-center justify-between px-4 pb-2 pt-5">
          <h1 className="text-[15px] font-semibold text-neutral-900">To review</h1>
          <select className="rounded border-0 bg-transparent text-xs text-neutral-500 focus:ring-0" value={status} onChange={(e) => { setStatus(e.target.value); select(null); }}>
            <option value="pending">Pending</option><option value="approved">Approved</option><option value="dismissed">Dismissed</option><option value="all">All</option>
          </select>
        </div>
        <div className="flex-1 overflow-auto px-2 pb-4">
          {items === null ? <p className="p-4 text-sm text-neutral-400">Loading…</p> : items.length === 0 ? (
            <p className="p-4 text-sm text-neutral-400">Nothing to review.</p>
          ) : items.map((it) => (
            <button key={it.id} onClick={() => select(it.id)}
              className={`block w-full rounded-md px-3 py-2.5 text-left ${selected === it.id ? "bg-neutral-100" : "hover:bg-neutral-50"}`}>
              <div className="flex items-start gap-2">
                <span className="line-clamp-2 flex-1 text-[13.5px] leading-snug text-neutral-900">{listTitle(it, project?.name)}</span>
                {it.low_confidence && <span title="Needs checking: the agent is not confident" className="mt-1.5 h-2 w-2 shrink-0 rounded-full border border-neutral-400" />}
              </div>
              <div className="mt-0.5 text-xs">
                {it.priority_date ? <DuePhrase due={it.priority_date} wd={it.working_days_remaining} /> : <span className="text-neutral-400">{it.kind === "claim_draft" ? "Draft claim" : it.kind === "revision_comparison" ? "Drawing revision" : "No deadline"}</span>}
              </div>
            </button>
          ))}
        </div>
        <div className="border-t border-neutral-100 px-4 py-2 text-[11px] text-neutral-400">j / k to move between items</div>
      </section>
      <section className="min-w-0 flex-1 overflow-auto">
        {selected ? <Detail key={selected} reviewId={selected} projectId={id} projectName={project?.name}
          onChange={() => { load(); reloadProject(); }} onNext={index < (items?.length ?? 0) - 1 ? next : undefined} />
          : <p className="p-10 text-sm text-neutral-400">Select an item.</p>}
      </section>
    </div>
  );
}

function Detail({ reviewId, projectId, projectName, onChange, onNext }: {
  reviewId: string; projectId: string; projectName?: string; onChange: () => void; onNext?: () => void;
}) {
  const [r, setR] = useState<(ReviewItemT & { working_days_remaining?: number | null }) | null>(null);
  const [draft, setDraft] = useState({ subject: "", recipient: "", body: "" });
  const [editing, setEditing] = useState(false);
  const [editDate, setEditDate] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const apply = (x: ReviewItemT) => {
    setR(x);
    if (x.draft) setDraft({ subject: x.draft.subject, recipient: x.draft.recipient ?? "", body: x.draft.body });
  };
  const reload = useCallback(() => api<ReviewItemT>(`/review/${reviewId}`).then(apply).catch((e) => setError(e.message)), [reviewId]);
  useEffect(() => {
    reload();
  }, [reload]);

  const notes: Note[] = useMemo(() => {
    if (!r) return [];
    if (r.kind === "revision_comparison") return revisionNotes(r);
    if (r.kind === "claim_draft") return claimNotes(r);
    return noticeNotes(r);
  }, [r]);

  if (!r) return <p className="p-10 text-sm text-neutral-400">{error ?? "Loading…"}</p>;

  const pending = r.status === "pending";
  const dirty = !!r.draft && (draft.subject !== r.draft.subject || draft.body !== r.draft.body || draft.recipient !== (r.draft.recipient ?? ""));

  async function act(path: string, json: object = {}) {
    setBusy(true);
    setError(null);
    try {
      apply(await api<ReviewItemT>(`/review/${reviewId}/${path}`, { method: "POST", json: { comment: comment || null, ...json } }));
      setComment("");
      setShowComment(false);
      onChange();
      return true;
    } catch (e: any) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const save = async () => {
    if (await act("edit", draft)) setEditing(false);
  };
  const approve = async () => {
    if (dirty && !(await act("edit", draft))) return;
    setEditing(false);
    await act("approve");
  };
  const saveDate = async () => {
    if (editDate && (await act("edit", { trigger_date: editDate }))) setEditDate(null);
  };
  const focus = (id: string | null) => {
    setActive(id);
    if (id) document.getElementById(`note-${id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  // ---- header text per kind
  const isNotice = r.kind === "notice_flag" || r.kind === "possible_event";
  const comp = (r as any).comparison;
  const claim = (r as any).claim;
  const kindLine = isNotice
    ? [CATEGORY_LABEL[r.category ?? "noise"], r.payload?.event_ref, sourceLabel(r.payload?.source)].filter(Boolean).join(" · ")
    : r.kind === "revision_comparison" ? `Drawing revision · ${comp?.base.filename} → ${comp?.revised.filename}`
    : `Claim · ${claim?.ref} · ${(r.payload?.events ?? []).map((e: any) => e.ref).join(", ")}`;
  const title = r.kind === "revision_comparison" ? listTitle(r as Row, projectName) : cleanTitle(r.title, projectName);
  const primary = r.payload?.rules?.[0];
  const primaryDeadline = (r.deadlines ?? []).find((d) => d.rule_id === primary?.id) ?? r.deadlines?.[0];
  const wd = r.working_days_remaining;
  const issued = r.event?.status === "notified";

  return (
    <div className="flex min-h-full">
      <article className="mx-auto w-full max-w-[720px] px-10 pb-28 pt-8">
        <div className="text-[13px] text-neutral-500">{kindLine}</div>
        <h1 className="mt-1 text-[26px] font-semibold leading-tight tracking-tight text-neutral-900">{title}</h1>
        {r.low_confidence && (
          <p className="mt-2 flex items-center gap-1.5 text-[13px] text-neutral-500">
            <span className="h-2 w-2 rounded-full border border-neutral-400" />
            Needs checking — the agent isn’t confident. <button className="underline underline-offset-2" onClick={() => focus("why")}>Why?</button>
          </p>
        )}

        <div className="mt-6 space-y-5">
          <Section label="What happened">
            <p>{r.summary}</p>
            {comp?.flags?.length > 0 && <p className="mt-2">Note: {comp.flags[0]}</p>}
          </Section>

          <Section label="What to do">
            {isNotice && primary && primaryDeadline ? (
              <p>
                {r.status === "approved" ? (issued ? "Notice issued. " : "Approved — export the letter, send it from your own email, then mark it issued. ")
                  : <>Send a notice under <button className="underline decoration-neutral-300 underline-offset-2" onClick={() => focus(r.citations.findIndex((c) => c.clause_ref === primary.clause_ref) >= 0 ? `c${r.citations.findIndex((c) => c.clause_ref === primary.clause_ref)}` : "why")}>clause {primary.clause_ref}</button> by{" "}
                    <button className={`font-medium underline decoration-neutral-300 underline-offset-2 ${urgent(wd) ? "text-red-600" : ""}`} onClick={() => focus(`d${primaryDeadline.id}`)}>{fmtDate(primaryDeadline.due_date)}</button>.{" "}</>}
                <span className="text-[13px]"><DuePhrase due={r.priority_date} wd={wd} issued={issued} /></span>
              </p>
            ) : isNotice ? (
              <p>No contract clause is linked yet — approve the contract rules, then check whether a notice is needed.</p>
            ) : r.kind === "revision_comparison" ? (
              <p>Check each change below and raise the ones that are variations. {r.payload?.counts?.not_on_register === 0 ? "All of them relate to events already on the register." : `${r.payload?.counts?.not_on_register} aren’t on the register yet.`}</p>
            ) : (
              <p>Review the draft claim below.{claim?.time_bar_risk && <> <span className="text-red-600">Time-bar risk:</span> notices that are conditions precedent were not given in time — <button className="underline underline-offset-2" onClick={() => focus("notices")}>see notice position</button>.</>}</p>
            )}
            {isNotice && r.event && pending && (
              <p className="mt-1 text-[13px] text-neutral-500">
                Clock started {editDate === null ? (
                  <><button className="underline decoration-neutral-300 underline-offset-2" onClick={() => setEditDate(r.event!.trigger_date)}>{fmtDate(r.event.trigger_date)}</button> (date aware)</>
                ) : (
                  <span className="inline-flex items-center gap-1.5">
                    <input type="date" className="rounded border border-neutral-300 px-1 py-0.5 text-[13px]" value={editDate} onChange={(e) => setEditDate(e.target.value)} />
                    <button className="font-medium text-neutral-900" disabled={busy} onClick={saveDate}>Recalculate</button>
                    <button onClick={() => setEditDate(null)}>Cancel</button>
                  </span>
                )}
              </p>
            )}
          </Section>

          {r.kind === "revision_comparison" ? (
            <Section label="Changes">
              <RevisionChanges r={r} projectId={projectId} active={active} onSelect={focus} onChanged={() => { reload(); onChange(); }} />
            </Section>
          ) : r.draft ? (
            <Section label={r.kind === "claim_draft" ? "Draft claim" : "Draft notice"}>
              <div className="mt-2 rounded-lg bg-white px-8 py-7 shadow-sm ring-1 ring-neutral-200">
                {editing ? (
                  <div className="space-y-3">
                    <input className="w-full border-b border-neutral-200 pb-1 text-[14px] text-neutral-600 focus:outline-none" value={draft.recipient} onChange={(e) => setDraft({ ...draft, recipient: e.target.value })} placeholder="To" />
                    <input className="w-full border-b border-neutral-200 pb-1 text-[15px] font-semibold focus:outline-none" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} placeholder="Subject" />
                    <textarea className="min-h-[480px] w-full resize-y text-[15px] leading-relaxed focus:outline-none" value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
                  </div>
                ) : (
                  <div className="space-y-3 text-[15px] leading-relaxed">
                    <div className="text-[14px] text-neutral-500">To: {draft.recipient}</div>
                    <div className="font-semibold">{draft.subject}</div>
                    <HighlightedText text={draft.body} notes={notes} active={active} onSelect={focus} />
                  </div>
                )}
              </div>
              {!editing && notes.some((n) => n.quote) && <p className="mt-2 text-[12px] text-neutral-400">Underlined passages come from the source documents — click one to see where.</p>}
            </Section>
          ) : null}
        </div>

        {/* action bar */}
        <div className="sticky bottom-4 mt-8 flex items-center gap-3 rounded-lg bg-white/95 px-4 py-2.5 text-[14px] shadow-md ring-1 ring-neutral-200 backdrop-blur">
          {pending && !editing && (
            <>
              <button className="rounded-md bg-neutral-900 px-3.5 py-1.5 font-medium text-white hover:bg-neutral-800 disabled:opacity-50" disabled={busy} onClick={approve}>
                {r.kind === "revision_comparison" ? "Mark as reviewed" : "Approve"}
              </button>
              {r.draft && <button className="text-neutral-700 hover:text-neutral-900" onClick={() => setEditing(true)}>Edit</button>}
              <button className="text-neutral-500 hover:text-neutral-900" disabled={busy} onClick={() => (showComment ? act("dismiss") : setShowComment(true))}>{showComment ? "Confirm dismiss" : "Dismiss"}</button>
            </>
          )}
          {pending && editing && (
            <>
              <button className="rounded-md bg-neutral-900 px-3.5 py-1.5 font-medium text-white disabled:opacity-50" disabled={busy} onClick={approve}>Save and approve</button>
              <button className="text-neutral-700" disabled={busy || !dirty} onClick={save}>Save</button>
              <button className="text-neutral-500" onClick={() => { setEditing(false); apply(r); }}>Cancel</button>
            </>
          )}
          {!pending && (
            <>
              <span className="text-neutral-500">{r.status === "approved" ? "Approved" : "Dismissed"}</span>
              {r.status === "approved" && r.draft && (
                <>
                  <button className="text-neutral-700 hover:text-neutral-900" onClick={() => download(`/drafts/${r.draft!.id}/export?format=docx`, `${r.draft!.subject}.docx`).catch((e) => setError(e.message))}>Word</button>
                  <button className="text-neutral-700 hover:text-neutral-900" onClick={() => download(`/drafts/${r.draft!.id}/export?format=pdf`, `${r.draft!.subject}.pdf`).catch((e) => setError(e.message))}>PDF</button>
                  {isNotice && !issued && <button className="text-neutral-700 hover:text-neutral-900" disabled={busy} onClick={() => act("mark-issued", { issued_on: new Date().toISOString().slice(0, 10) })}>Mark issued today</button>}
                </>
              )}
              <button className="text-neutral-500 hover:text-neutral-900" disabled={busy} onClick={() => act("reopen")}>Reopen</button>
            </>
          )}
          {showComment && pending && (
            <input autoFocus className="min-w-0 flex-1 rounded border border-neutral-200 px-2 py-1 text-[13px] focus:outline-none" placeholder="Reason (optional, kept in the audit log)" value={comment} onChange={(e) => setComment(e.target.value)} />
          )}
          {error && <span className="truncate text-[13px] text-red-600">{error}</span>}
          {onNext && <button className="ml-auto text-neutral-500 hover:text-neutral-900" onClick={onNext}>Next →</button>}
        </div>
      </article>
      <Margin notes={notes} active={active} onSelect={focus} projectId={projectId} />
    </div>
  );
}

export default function InboxPage() {
  return <Suspense><Inbox /></Suspense>;
}
