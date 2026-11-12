"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, DeadlineT } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { CATEGORY_LABEL, cleanTitle } from "@/lib/text";
import { DuePhrase } from "@/components/inbox/doc";
import { PanelSection, PanelTitle, RegisterLayout, RegisterTable, rowClass, Segments } from "@/components/register";
import { Empty, ErrorBox } from "@/components/ui";
import { useProject } from "@/components/project-context";

type Show = "open" | "overdue" | "soon" | "all";

export default function Deadlines() {
  const { id } = useParams<{ id: string }>();
  const { project } = useProject();
  const [rows, setRows] = useState<DeadlineT[] | null>(null);
  const [show, setShow] = useState<Show>("open");
  const [selected, setSelected] = useState<string | null>(null);
  const [calcOpen, setCalcOpen] = useState(false);

  useEffect(() => {
    api<DeadlineT[]>(`/projects/${id}/deadlines?include_closed=${show === "all"}`).then(setRows);
  }, [id, show]);

  const shown = (rows ?? []).filter((d) => {
    const wd = d.working_days_remaining ?? 0;
    if (show === "overdue") return d.status === "running" && wd < 0;
    if (show === "soon") return d.status === "running" && wd >= 0 && wd <= 5;
    return true;
  });
  const sel = rows?.find((d) => d.id === selected) ?? null;
  const close = () => { setSelected(null); setCalcOpen(false); };

  return (
    <RegisterLayout
      title="Deadlines"
      description="Every running notice clock, calculated from the approved contract rules, Irish public holidays, weekends and project shutdowns."
      actions={<button className="btn" onClick={() => { setSelected(null); setCalcOpen(true); }}>Deadline calculator</button>}
      filters={<Segments value={show} onChange={setShow} options={[["open", "Open"], ["overdue", "Overdue"], ["soon", "Due in 5 working days"], ["all", "All, including closed"]]} />}
      panel={sel ? <DeadlinePanel d={sel} projectId={id} projectName={project?.name} /> : calcOpen ? <Calculator projectId={id} /> : undefined}
      onClose={close}
    >
      {rows === null ? <Empty>Loading…</Empty> : shown.length === 0 ? <Empty>Nothing here.</Empty> : (
        <RegisterTable head={["Due", "Obligation", "Event"]}>
          {shown.map((d) => (
            <tr key={d.id} className={rowClass(selected === d.id)} onClick={() => { setCalcOpen(false); setSelected(d.id); }}>
              <td className="td w-56">
                <div className="tabular-nums">{fmtDate(d.due_date)}</div>
                <div className="text-xs">{d.status === "running" ? <DuePhrase due={d.due_date} wd={d.working_days_remaining} /> : <span className="text-neutral-400">{d.status === "met" ? "Notice issued" : "Cancelled"}</span>}</div>
              </td>
              <td className="td">{d.label.replace(/^Clause /, "Clause ")}</td>
              <td className="td">{cleanTitle(d.event?.title ?? "", project?.name)}<div className="text-xs text-neutral-400">{d.event?.ref}</div></td>
            </tr>
          ))}
        </RegisterTable>
      )}
    </RegisterLayout>
  );
}

function DeadlinePanel({ d, projectId, projectName }: { d: DeadlineT; projectId: string; projectName?: string }) {
  const hols = d.trace.skipped.filter((s) => !s.reason.startsWith("weekend"));
  const clause = d.label.match(/^Clause (\S+)/)?.[1];
  return (
    <>
      <PanelTitle kicker={`${CATEGORY_LABEL[d.event?.category ?? ""] ?? "Event"} · ${d.event?.ref}`} title={cleanTitle(d.event?.title ?? "", projectName)} />
      <PanelSection label="What to do">
        {d.status === "running" ? (
          <p>Send a notice under clause {clause} by <b className="font-medium">{fmtDate(d.due_date)}</b>. <span className="text-[13px]"><DuePhrase due={d.due_date} wd={d.working_days_remaining} /></span></p>
        ) : <p>{d.status === "met" ? "Notice issued — the clock is stopped." : "This clock was cancelled when the event was dismissed."}</p>}
        {d.condition_precedent && <p className="mt-1 text-neutral-600">This notice is a condition precedent: if it is late, the entitlement can be lost.</p>}
        {d.review_item_id && <p className="mt-2"><Link className="link" href={`/projects/${projectId}/inbox?item=${d.review_item_id}`}>Open the draft notice in the review queue →</Link></p>}
      </PanelSection>
      <PanelSection label="How the date was calculated">
        <p>{d.trace.explanation}</p>
        {hols.length > 0 && <p className="mt-1 text-neutral-500">Not counted: {hols.map((s) => `${fmtDate(s.date)} (${s.reason.replace("public holiday: ", "").replace("shutdown: ", "")})`).join(", ")}</p>}
        <p className="mt-1 text-[13px] text-neutral-400">Worked out by the deadline engine from {d.label}, starting the day after {fmtDate(d.trigger_date)}.</p>
      </PanelSection>
    </>
  );
}

function Calculator({ projectId }: { projectId: string }) {
  const [calc, setCalc] = useState({ trigger_date: new Date().toISOString().slice(0, 10), period: 10, unit: "working_days" });
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setResult(await api(`/projects/${projectId}/deadline-calculator`, { method: "POST", json: calc }));
    } catch (err: any) {
      setError(err.message);
    }
  }
  return (
    <>
      <PanelTitle kicker="Tool" title="Deadline calculator"><p className="text-[13.5px] text-neutral-500">Uses this project’s calendar: public holidays, weekends and shutdowns.</p></PanelTitle>
      <form onSubmit={run} className="space-y-3 border-t border-neutral-100 pt-4">
        <label className="block space-y-1"><span className="label">Start date (the trigger day is not counted)</span><input type="date" className="input" value={calc.trigger_date} onChange={(e) => setCalc({ ...calc, trigger_date: e.target.value })} /></label>
        <div className="flex gap-2">
          <label className="block w-24 space-y-1"><span className="label">Period</span><input type="number" min={0} className="input" value={calc.period} onChange={(e) => setCalc({ ...calc, period: Number(e.target.value) })} /></label>
          <label className="block flex-1 space-y-1"><span className="label">Unit</span>
            <select className="input" value={calc.unit} onChange={(e) => setCalc({ ...calc, unit: e.target.value })}>
              <option value="working_days">working days</option><option value="calendar_days">calendar days</option><option value="weeks">weeks</option><option value="months">months</option>
            </select></label>
        </div>
        <button className="btn-primary">Calculate</button>
        <ErrorBox error={error} />
      </form>
      {result && (
        <PanelSection label="Result">
          <p className="text-[18px] font-semibold">{fmtDate(result.due_date)}</p>
          <p className="text-neutral-600">{result.explanation}</p>
          {result.skipped.filter((s: any) => !s.reason.startsWith("weekend")).length > 0 && (
            <p className="mt-1 text-neutral-500">Not counted: {result.skipped.filter((s: any) => !s.reason.startsWith("weekend")).map((s: any) => `${fmtDate(s.date)} (${s.reason.replace("public holiday: ", "")})`).join(", ")}</p>
          )}
        </PanelSection>
      )}
    </>
  );
}
