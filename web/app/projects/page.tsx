"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";
import { ErrorBox, Empty } from "@/components/ui";

type Project = { id: string; name: string; code: string | null; location: string | null; contract_form: string | null };

export default function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", location: "", contract_form: "PWC", holiday_region: "IE" });

  const load = () => api<Project[]>("/projects").then(setProjects).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/projects", { method: "POST", json: form });
      setForm({ ...form, name: "", location: "" });
      load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Projects</h1>
        <button className="btn" onClick={() => { setToken(null); location.href = "/login"; }}>Sign out</button>
      </header>
      <ErrorBox error={error} />
      <div className="card">
        {projects === null ? <Empty>Loading…</Empty> : projects.length === 0 ? <Empty>No projects yet.</Empty> : (
          <table className="w-full">
            <thead><tr><th className="th">Project</th><th className="th">Location</th><th className="th">Contract</th></tr></thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="td"><Link className="font-medium text-sky-800 hover:underline" href={`/projects/${p.id}/inbox`}>{p.name}</Link> <span className="text-slate-400">{p.code}</span></td>
                  <td className="td">{p.location}</td>
                  <td className="td">{p.contract_form}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <form onSubmit={create} className="card grid grid-cols-5 items-end gap-2 p-3">
        <label className="col-span-2 space-y-1"><span className="label">New project</span><input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
        <label className="space-y-1"><span className="label">Location</span><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label>
        <label className="space-y-1"><span className="label">Holidays</span>
          <select className="input" value={form.holiday_region} onChange={(e) => setForm({ ...form, holiday_region: e.target.value })}>
            <option value="IE">Ireland</option><option value="GB-NIR">Northern Ireland</option><option value="GB-ENG">England</option><option value="GB-SCT">Scotland</option><option value="GB-WLS">Wales</option>
          </select>
        </label>
        <button className="btn-primary justify-center">Create</button>
      </form>
    </main>
  );
}
