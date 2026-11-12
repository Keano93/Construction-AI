"use client";

/** Document-style building blocks for the review queue: due phrase, highlighted body, margin notes. */

import { Fragment, useMemo } from "react";
import { Citation } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { findSpan } from "@/lib/text";
import { SourcePassage } from "@/components/SourcePassage";

export type Note = {
  id: string;
  title: string;
  subtitle?: string;
  preview?: string; // one line shown when collapsed
  citation?: Citation; // source passage shown when open
  quote?: string; // text to highlight in the body
  content?: React.ReactNode; // custom content shown when open
};

export function urgent(wd: number | null | undefined) {
  return wd !== null && wd !== undefined && wd <= 3;
}

export function DuePhrase({ due, wd, issued }: { due: string | null; wd: number | null | undefined; issued?: boolean }) {
  if (issued) return <span className="text-neutral-500">Notice issued</span>;
  if (!due || wd === null || wd === undefined) return <span className="text-neutral-400">No deadline</span>;
  const cls = urgent(wd) ? "text-red-600" : "text-neutral-500";
  if (wd < 0) return <span className={cls}>Overdue by {-wd} working day{wd === -1 ? "" : "s"}</span>;
  if (wd === 0) return <span className={cls}>Due today</span>;
  return <span className={cls}>Due {fmtDate(due)} · {wd} working day{wd === 1 ? "" : "s"} left</span>;
}

/** Renders text as paragraphs, marking passages that match margin notes. */
export function HighlightedText({ text, notes, active, onSelect }: { text: string; notes: Note[]; active: string | null; onSelect: (id: string) => void }) {
  const marks = useMemo(() => {
    const spans: { s: number; e: number; id: string }[] = [];
    for (const n of notes) {
      if (!n.quote) continue;
      const sp = findSpan(text, n.quote);
      if (sp && !spans.some((x) => sp[0] < x.e && sp[1] > x.s)) spans.push({ s: sp[0], e: sp[1], id: n.id });
    }
    return spans.sort((a, b) => a.s - b.s);
  }, [text, notes]);

  const parts: React.ReactNode[] = [];
  let pos = 0;
  marks.forEach((m, i) => {
    parts.push(<Fragment key={`t${i}`}>{text.slice(pos, m.s)}</Fragment>);
    parts.push(
      <mark key={`m${i}`} onClick={() => onSelect(m.id)}
        className={`cursor-pointer rounded-sm border-b border-dotted border-neutral-400 px-0.5 text-inherit ${active === m.id ? "bg-neutral-200" : "bg-neutral-100 hover:bg-neutral-200"}`}>
        {text.slice(m.s, m.e)}
      </mark>,
    );
    pos = m.e;
  });
  parts.push(<Fragment key="end">{text.slice(pos)}</Fragment>);
  return <div className="whitespace-pre-wrap">{parts}</div>;
}

export function Margin({ notes, active, onSelect, projectId }: { notes: Note[]; active: string | null; onSelect: (id: string | null) => void; projectId: string }) {
  if (!notes.length) return null;
  return (
    <aside className="hidden w-[320px] shrink-0 space-y-2 py-8 pr-6 xl:block">
      <div className="px-3 text-xs text-neutral-400">Sources and reasoning</div>
      {notes.map((n) => {
        const open = active === n.id;
        return (
          <div key={n.id} id={`note-${n.id}`} className={`rounded-md px-3 py-2 transition ${open ? "bg-white shadow-sm ring-1 ring-neutral-200" : "hover:bg-neutral-100"}`}>
            <button className="block w-full text-left" onClick={() => onSelect(open ? null : n.id)}>
              <div className="text-[13px] font-medium text-neutral-800">{n.title}</div>
              {n.subtitle && <div className="text-xs text-neutral-500">{n.subtitle}</div>}
              {!open && n.preview && <div className="mt-0.5 line-clamp-2 text-xs text-neutral-500">{n.preview}</div>}
            </button>
            {open && (
              <div className="mt-2 space-y-2 text-xs text-neutral-700">
                {n.content}
                {n.citation && <SourcePassage citation={n.citation} projectId={projectId} context={160} />}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}

export function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1">
      <h2 className="text-xs font-medium uppercase tracking-wide text-neutral-400">{label}</h2>
      <div className="text-[15px] leading-relaxed text-neutral-800">{children}</div>
    </section>
  );
}

export function sourceLabel(source: { author?: string | null; channel?: string; timestamp?: string | null } | undefined) {
  if (!source) return "Source";
  const who = (source.author ?? "unknown").split("<")[0].trim();
  const via = source.channel === "whatsapp" ? "WhatsApp" : source.channel === "diary" ? "site diary" : source.channel ?? "";
  return `${who}${via ? ` · ${via}` : ""}${source.timestamp ? ` · ${fmtDate(source.timestamp)}` : ""}`;
}
