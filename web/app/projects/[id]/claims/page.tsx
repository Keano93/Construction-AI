"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { complianceText, fmtDate } from "@/lib/format";
import { PanelSection, PanelTitle, RegisterLayout, RegisterTable, rowClass } from "@/components/register";
import { Empty, StatusPill } from "@/components/ui";

type ClaimRow = { id: string; ref: string; title: string; status: string; event_ids: string[]; created_at: string; time_bar_risk: boolean; review_item_id: string | null };
type ClaimFull = ClaimRow & {
  narrative: { executive_summary?: string; quantum_heads?: { head: string }[] };
  notice_compliance: { event_ref: string; clause_ref: string; title: string; text: string; time_bar_risk: boolean; state: string; due_date: string; met_on?: string | null }[];
  timeline: { date: string; description: string; significance: string }[];
  gaps: string[];
};

export default function Claims() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<ClaimRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const load = () => api<ClaimRow[]>(`/projects/${id}/claims`).then((r) => { setRows(r); return r; });
    load();
    const t = setInterval(() => load().then((r) => { if (!r.some((x) => x.status === "drafting")) clearInterval(t); }), 4000);
    return () => clearInterval(t);
  }, [id]);
  const sel = rows?.find((r) => r.id === selected);

  return (
    <RegisterLayout
      title="Claims"
      description="To start a claim, tick events in the Event register and choose Draft claim. The Claims agent builds the evidence timeline, checks the notices and drafts the narrative for you to review."
      panel={sel ? <ClaimPanel key={sel.id} claimId={sel.id} reviewItemId={sel.review_item_id} projectId={id} /> : undefined}
      onClose={() => setSelected(null)}
    >
      {rows === null ? <Empty>Loading…</Empty> : rows.length === 0 ? <Empty>No claims yet.</Empty> : (
        <RegisterTable head={["Ref", "Claim", "Events", "Status"]}>
          {rows.map((c) => (
            <tr key={c.id} className={rowClass(selected === c.id)} onClick={() => setSelected(c.id)}>
              <td className="td w-24 tabular-nums">{c.ref}</td>
              <td className="td">{c.title}<div className="text-xs text-neutral-400">started {fmtDate(c.created_at)}</div></td>
              <td className="td w-20 tabular-nums">{c.event_ids.length}</td>
              <td className="td w-44"><StatusPill status={c.status} />{c.time_bar_risk && <div className="text-xs text-red-600">Time-bar risk</div>}</td>
            </tr>
          ))}
        </RegisterTable>
      )}
    </RegisterLayout>
  );
}

function ClaimPanel({ claimId, reviewItemId, projectId }: { claimId: string; reviewItemId: string | null; projectId: string }) {
  const [c, setC] = useState<ClaimFull | null>(null);
  useEffect(() => {
    api<ClaimFull>(`/claims/${claimId}`).then(setC);
  }, [claimId]);
  if (!c) return <p className="text-sm text-neutral-400">Loading…</p>;
  if (c.status === "drafting") return <PanelTitle kicker={`Claim ${c.ref}`} title={c.title}><p className="text-neutral-500">The Claims agent is still drafting this claim.</p></PanelTitle>;
  return (
    <>
      <PanelTitle kicker={`Claim ${c.ref}`} title={c.title} />
      <PanelSection label="Summary"><p>{c.narrative.executive_summary}</p></PanelSection>
      <PanelSection label="Notice position">
        <ul className="space-y-1.5">
          {c.notice_compliance.map((n, i) => (
            <li key={i}>{n.event_ref} · clause {n.clause_ref} {n.title}<div className={`text-[13px] ${n.time_bar_risk ? "text-red-600" : "text-neutral-500"}`}>{complianceText(n)}</div></li>
          ))}
        </ul>
      </PanelSection>
      <PanelSection label={`Evidence (${c.timeline.length} records)`}>
        <ul className="space-y-1">
          {c.timeline.slice(0, 5).map((t, i) => <li key={i}><span className="tabular-nums text-neutral-500">{fmtDate(t.date)}</span> — {t.description}</li>)}
          {c.timeline.length > 5 && <li className="text-neutral-400">and {c.timeline.length - 5} more</li>}
        </ul>
        {c.gaps.length > 0 && <p className="mt-2 text-[13px] text-neutral-500">Still needed: {c.gaps.join("; ")}</p>}
      </PanelSection>
      {reviewItemId && <p className="pt-2"><Link className="link" href={`/projects/${projectId}/inbox?item=${reviewItemId}`}>Open the draft claim →</Link></p>}
    </>
  );
}
