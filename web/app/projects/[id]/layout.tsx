"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";
import { Ctx, ProjectT } from "@/components/project-context";

const NAV = [
  ["", "Overview"],
  ["/inbox", "Review queue"],
  ["/deadlines", "Deadlines"],
  ["/events", "Event register"],
  ["/revisions", "Revisions"],
  ["/claims", "Claims"],
  ["/contract", "Contract rules"],
  ["/documents", "Documents"],
  ["/audit", "Audit log"],
] as const;

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const [project, setProject] = useState<ProjectT | null>(null);
  const [system, setSystem] = useState<any>(null);
  const reload = useCallback(() => {
    api<ProjectT>(`/projects/${id}`).then(setProject).catch(() => {});
  }, [id]);
  useEffect(() => {
    reload();
    api("/system").then(setSystem).catch(() => {});
  }, [reload]);

  const base = `/projects/${id}`;
  const badge = (key: string) => {
    if (!project) return null;
    const n = key === "/inbox" ? project.stats.review_pending : key === "/contract" ? project.stats.rules_proposed : key === "/deadlines" ? project.stats.deadlines_overdue : 0;
    if (!n) return null;
    const red = key === "/deadlines";
    return <span className={`ml-auto rounded px-1.5 text-2xs font-semibold ${red ? "bg-rose-600 text-white" : "bg-slate-200 text-slate-700"}`}>{n}</span>;
  };

  return (
    <Ctx.Provider value={{ project, reload, system }}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-3 py-3">
            <Link href="/projects" className="text-2xs font-semibold uppercase tracking-wider text-emerald-700">Notice</Link>
            <div className="mt-1 truncate text-sm font-semibold">{project?.name ?? "…"}</div>
            <div className="truncate text-2xs text-slate-500">{project?.contract_form}</div>
          </div>
          <nav className="flex-1 space-y-px p-2">
            {NAV.map(([href, label]) => {
              const full = base + href;
              const active = href === "" ? pathname === base : pathname.startsWith(full);
              return (
                <Link key={href} href={full} className={`flex items-center rounded px-2 py-1.5 text-xs ${active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}>
                  {label}
                  {badge(href)}
                </Link>
              );
            })}
          </nav>
          <div className="space-y-1 border-t border-slate-200 p-3 text-2xs text-slate-500">
            {system && (
              <div title="LLM provider used by agents">
                Agents: <span className={`font-semibold ${system.llm_provider === "offline" ? "text-amber-700" : "text-emerald-700"}`}>{system.llm_provider}</span> ({system.model})
              </div>
            )}
            <div>Drafts only. Nothing is sent from Notice.</div>
            <button className="hover:underline" onClick={() => { setToken(null); location.href = "/login"; }}>Sign out</button>
          </div>
        </aside>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </Ctx.Provider>
  );
}
