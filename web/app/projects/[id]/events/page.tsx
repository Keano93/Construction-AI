"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ItemT } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { CATEGORY_LABEL, cleanTitle } from "@/lib/text";
import { DuePhrase } from "@/components/inbox/doc";
import { PanelSection, PanelTitle, RegisterLayout, RegisterTable, rowClass, Segments } from "@/components/register";
import { Empty, ErrorBox, StatusPill } from "@/components/ui";
import { useProject } from "@/components/project-context";

type Deadline = { id: string; label: string; due_date: string; status: string; working_days_remaining?: number };
type EventRow = {
  id: string; ref: string; category: string; title: string; description: string; trigger_date: string; status: string;
  related_item_ids: string[]; deadlines: Deadline[]; review_item_id: string | null;
};
type Cat = "" | "change" | "delay" | "instruction" | "disruption";

function nextDue(e: EventRow) {
  return e.deadlines.filter((d) => d.status === "running").sort((a, b) => a.due_date.localeCompare(b.due_date))[0];
}

export default function Events() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { project } = useProject();
  const [rows, setRows] = useState<EventRow[] | null>(null);
  const [cat, setCat] = useState<Cat>("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [claimTitle, setClaimTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<EventRow[]>(`/projects/${id}/events`).then(setRows);
  }, [id]);
  const shown = (rows ?? []).filter((r) => !cat || r.category === cat);
  const sel = rows?.find((r) => r.id === selected) ?? null;
  const toggle = (eid: string) => setPicked((s) => { const n = new Set(s); n.has(eid) ? n.delete(eid) : n.add(eid); return n; });

  async function draftClaim(ids: string[], title?: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${id}/claims`, { method: "POST", json: { event_ids: ids, title: title || null } });
      router.push(`/projects/${id}/claims`);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <RegisterLayout
      title="Event register"
      description="Changes, delays, instructions and disruption the agents found in the project record. Tick events to draft a claim."
      filters={<Segments value={cat} onChange={setCat} options={[["", "All"], ["change", "Changes"], ["delay", "Delays"], ["instruction", "Instructions"], ["disruption", "Disruption"]]} />}
      panel={sel ? <EventPanel e={sel} projectId={id} projectName={project?.name} busy={busy} onClaim={() => draftClaim([sel.id], cleanTitle(sel.title, project?.name))} /> : undefined}
      onClose={() => setSelected(null)}
    >
      {picked.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg bg-white px-4 py-2.5 text-[13.5px] ring-1 ring-neutral-200">
          <span>{picked.size} selected</span>
          <input className="input w-72" placeholder="Claim title (optional)" value={claimTitle} onChange={(e) => setClaimTitle(e.target.value)} />
          <button className="btn-primary" disabled={busy} onClick={() => draftClaim(Array.from(picked), claimTitle)}>{busy ? "Starting…" : "Draft claim"}</button>
          <button className="text-neutral-500 hover:text-neutral-900" onClick={() => setPicked(new Set())}>Clear</button>
        </div>
      )}
      <ErrorBox error={error} />
      {rows === null ? <Empty>Loading…</Empty> : shown.length === 0 ? <Empty>No events.</Empty> : (
        <RegisterTable head={["", "Event", "Aware", "Next notice due"]}>
          {shown.map((e) => {
            const nd = nextDue(e);
            return (
              <tr key={e.id} className={rowClass(selected === e.id)} onClick={() => setSelected(e.id)}>
                <td className="td w-8" onClick={(ev) => ev.stopPropagation()}>
                  <input type="checkbox" className="accent-neutral-800" checked={picked.has(e.id)} onChange={() => toggle(e.id)} aria-label={`select ${e.ref}`} />
                </td>
                <td className="td">
                  <div>{cleanTitle(e.title, project?.name)}</div>
                  <div className="text-xs text-neutral-400">{CATEGORY_LABEL[e.category]} · {e.ref}{e.status !== "open" ? ` · ${e.status}` : ""}</div>
                </td>
                <td className="td w-32 whitespace-nowrap tabular-nums text-neutral-600">{fmtDate(e.trigger_date)}</td>
                <td className="td w-56 text-xs">{nd ? <><div className="text-[13.5px] tabular-nums text-neutral-800">{fmtDate(nd.due_date)}</div><DuePhrase due={nd.due_date} wd={nd.working_days_remaining} /></> : <span className="text-neutral-400">{e.status === "notified" ? "Notice issued" : "—"}</span>}</td>
              </tr>
            );
          })}
        </RegisterTable>
      )}
    </RegisterLayout>
  );
}

function EventPanel({ e, projectId, projectName, busy, onClaim }: { e: EventRow; projectId: string; projectName?: string; busy: boolean; onClaim: () => void }) {
  const [items, setItems] = useState<ItemT[]>([]);
  useEffect(() => {
    Promise.all(e.related_item_ids.map((i) => api<ItemT>(`/items/${i}`).catch(() => null))).then((xs) => setItems(xs.filter(Boolean) as ItemT[]));
  }, [e]);
  return (
    <>
      <PanelTitle kicker={`${CATEGORY_LABEL[e.category]} · ${e.ref} · aware ${fmtDate(e.trigger_date)}`} title={cleanTitle(e.title, projectName)} />
      <PanelSection label="What happened"><p>{e.description}</p></PanelSection>
      <PanelSection label="Notices">
        {e.deadlines.length === 0 ? <p className="text-neutral-500">No notice clock linked.</p> : (
          <ul className="space-y-1.5">
            {e.deadlines.map((d) => (
              <li key={d.id}>
                {d.label} — <span className="tabular-nums">{fmtDate(d.due_date)}</span>{" "}
                <span className="text-[13px]">{d.status === "running" ? <DuePhrase due={d.due_date} wd={d.working_days_remaining} /> : <StatusPill status={d.status} />}</span>
              </li>
            ))}
          </ul>
        )}
        {e.review_item_id && <p className="mt-2"><Link className="link" href={`/projects/${projectId}/inbox?item=${e.review_item_id}`}>Open the draft notice →</Link></p>}
      </PanelSection>
      <PanelSection label={`Records (${e.related_item_ids.length})`}>
        <ul className="space-y-3">
          {items.map((it) => (
            <li key={it.id}>
              <div className="text-[13px] text-neutral-500">{(it.author ?? "unknown").split("<")[0]} · {it.kind === "whatsapp" ? "WhatsApp" : it.kind} · {fmtDateTime(it.timestamp)}</div>
              <div className="line-clamp-3 text-[13.5px]">{it.text}</div>
              <Link className="link text-[13px] text-neutral-500" href={`/projects/${projectId}/documents/${it.document_id}?hl=${it.char_start}-${it.char_end}`}>open source</Link>
            </li>
          ))}
        </ul>
      </PanelSection>
      <PanelSection label="Claim">
        <button className="btn" disabled={busy} onClick={onClaim}>{busy ? "Starting…" : "Draft a claim for this event"}</button>
      </PanelSection>
    </>
  );
}
