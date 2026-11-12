"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api, download, ItemT } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Empty } from "@/components/ui";

type Doc = { id: string; filename: string; kind: string; mime: string; author: string | null; doc_timestamp: string | null; sha256: string; extraction_method: string; text: string; item_list: ItemT[] };

function Viewer() {
  const { docId } = useParams<{ docId: string }>();
  const hl = useSearchParams().get("hl");
  const [doc, setDoc] = useState<Doc | null>(null);
  const markRef = useRef<HTMLElement>(null);
  useEffect(() => {
    api<Doc>(`/documents/${docId}`).then(setDoc);
  }, [docId]);
  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center" });
  }, [doc]);
  if (!doc) return <Empty>Loading…</Empty>;

  const [s, e] = (hl ?? "").split("-").map(Number);
  const valid = Number.isFinite(s) && Number.isFinite(e) && e > s;
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-base font-semibold">{doc.filename}</h1>
          <p className="text-2xs text-neutral-500">{doc.kind} · {doc.author ?? "unknown author"} · {fmtDateTime(doc.doc_timestamp)} · extracted by {doc.extraction_method} · {doc.item_list.length} item(s) · sha256 {doc.sha256}</p>
        </div>
        <button className="btn" onClick={() => download(`/documents/${doc.id}/file`, doc.filename)}>Download original</button>
      </div>
      <div className="card whitespace-pre-wrap p-3 font-mono text-[12px] leading-relaxed text-neutral-800">
        {valid ? (
          <>
            {doc.text.slice(0, s)}
            <mark ref={markRef} className="cite">{doc.text.slice(s, e)}</mark>
            {doc.text.slice(e)}
          </>
        ) : doc.text}
      </div>
    </div>
  );
}

export default function DocumentPage() {
  return <Suspense><Viewer /></Suspense>;
}
