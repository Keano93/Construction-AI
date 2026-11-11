"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, Citation } from "@/lib/api";

type Doc = { id: string; filename: string; kind: string; text: string };
const cache = new Map<string, Promise<Doc>>();

export function useDocument(id: string | null) {
  const [doc, setDoc] = useState<Doc | null>(null);
  useEffect(() => {
    if (!id) return;
    if (!cache.has(id)) cache.set(id, api<Doc>(`/documents/${id}`));
    let live = true;
    cache.get(id)!.then((d) => live && setDoc(d)).catch(() => cache.delete(id));
    return () => {
      live = false;
    };
  }, [id]);
  return doc;
}

/** Shows the exact cited passage in context, highlighted, with a link to the full document. */
export function SourcePassage({ citation, projectId, context = 220 }: { citation: Citation; projectId: string; context?: number }) {
  const doc = useDocument(citation.document_id);
  const boxRef = useRef<HTMLDivElement>(null);
  const markRef = useRef<HTMLElement>(null);
  useEffect(() => {
    // keep the highlighted passage in view inside the scroll box
    if (boxRef.current && markRef.current) boxRef.current.scrollTop = Math.max(0, markRef.current.offsetTop - 24); // box is the offsetParent (position: relative)
  }, [doc]);
  const start = citation.char_start;
  const end = citation.char_end;
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-2 py-1">
        <span className="text-2xs font-semibold text-slate-600">
          {citation.label ?? "Source"}
          {citation.clause_ref ? ` · clause ${citation.clause_ref}` : ""}
          {doc ? ` · ${doc.filename}` : ""}
        </span>
        <Link className="text-2xs text-sky-700 hover:underline" href={`/projects/${projectId}/documents/${citation.document_id}?hl=${start}-${end}`}>
          open source ↗
        </Link>
      </div>
      <div ref={boxRef} className="relative max-h-48 overflow-auto whitespace-pre-wrap px-2 py-1.5 font-mono text-[11.5px] leading-relaxed text-slate-700">
        {doc ? (
          <>
            {start - context > 0 ? "…" : ""}
            {doc.text.slice(Math.max(0, start - context), start)}
            <mark ref={markRef} className="cite">{doc.text.slice(start, end)}</mark>
            {doc.text.slice(end, end + context)}
            {end + context < doc.text.length ? "…" : ""}
          </>
        ) : (
          <span className="text-slate-400">loading…</span>
        )}
      </div>
    </div>
  );
}
