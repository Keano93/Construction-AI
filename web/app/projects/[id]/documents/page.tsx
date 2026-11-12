"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Empty, ErrorBox } from "@/components/ui";
import { useProject } from "@/components/project-context";

type Doc = { id: string; kind: string; filename: string; author: string | null; doc_timestamp: string | null; extraction_method: string; items: number; sha256: string; size_bytes: number };
const KINDS = ["", "contract", "email", "whatsapp", "diary", "drawing_register", "spec", "drawing", "quote", "compliance", "other"];

export default function Documents() {
  const { id } = useParams<{ id: string }>();
  const { reload } = useProject();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [kind, setKind] = useState("");
  const [uploadKind, setUploadKind] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api<Doc[]>(`/projects/${id}/documents${kind ? `?kind=${kind}` : ""}`).then(setDocs), [id, kind]);
  useEffect(() => {
    load();
  }, [load]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    const files = fileRef.current?.files;
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    let created = 0, dup = 0;
    try {
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", f);
        if (uploadKind) fd.append("kind", uploadKind);
        const res = await api<{ created: boolean }>(`/projects/${id}/documents`, { method: "POST", body: fd });
        res.created ? created++ : dup++;
      }
      setMsg(`${created} uploaded${dup ? `, ${dup} already in the record (same content hash)` : ""}. Agents are processing them.`);
      if (fileRef.current) fileRef.current.value = "";
      load();
      reload();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 p-4">
      <h1 className="text-base font-semibold">Documents</h1>
      <form onSubmit={upload} className="card flex flex-wrap items-end gap-2 p-3">
        <label className="space-y-0.5"><span className="label">Files (PDF, DOCX, XLSX, EML, MSG, WhatsApp .txt, images)</span>
          <input ref={fileRef} type="file" multiple className="block text-xs" accept=".pdf,.docx,.xlsx,.eml,.msg,.txt,.md,.csv,.png,.jpg,.jpeg,.tif,.tiff" /></label>
        <label className="space-y-0.5"><span className="label">Type</span>
          <select className="input" value={uploadKind} onChange={(e) => setUploadKind(e.target.value)}>{KINDS.map((k) => <option key={k} value={k}>{k || "auto-detect"}</option>)}</select></label>
        <button className="btn-primary" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
        {msg && <span className="text-xs text-neutral-600">{msg}</span>}
      </form>
      <ErrorBox error={error} />
      <div className="flex justify-end">
        <select className="input w-48" value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k} value={k}>{k || "All types"}</option>)}</select>
      </div>
      <div className="card overflow-hidden">
        {docs === null ? <Empty>Loading…</Empty> : docs.length === 0 ? <Empty>No documents.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Document</th><th className="th">Type</th><th className="th">Author</th><th className="th">Dated</th><th className="th">Items</th><th className="th">Extraction</th><th className="th">SHA-256</th></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="hover:bg-neutral-50">
                  <td className="td"><Link className="font-medium text-neutral-900 underline decoration-neutral-300 underline-offset-2 hover:underline" href={`/projects/${id}/documents/${d.id}`}>{d.filename}</Link></td>
                  <td className="td">{d.kind}</td>
                  <td className="td truncate">{d.author ?? "—"}</td>
                  <td className="td whitespace-nowrap">{fmtDateTime(d.doc_timestamp)}</td>
                  <td className="td text-center">{d.items}</td>
                  <td className="td">{d.extraction_method}</td>
                  <td className="td font-mono text-2xs text-neutral-400" title={d.sha256}>{d.sha256.slice(0, 12)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
