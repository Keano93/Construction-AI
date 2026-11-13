"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";
import { Ctx, ProjectT } from "@/components/project-context";

const NAV = [
  ["/inbox", "Review queue"],
  ["/deadlines", "Deadlines"],
  ["/events", "Event register"],
  ["/revisions", "Revisions"],
  ["/claims", "Claims"],
  ["/meeting", "Commercial meeting"],
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
    return <span className={`ml-auto rounded px-1.5 text-2xs font-semibold ${red ? "text-red-600" : "text-neutral-400"}`}>{n}</span>;
  };

  return (
    <Ctx.Provider value={{ project, reload, system }}>
      <div className="flex min-h-screen bg-neutral-50">
        <aside className="app-sidebar sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-neutral-200 bg-neutral-50">
          <div className="px-4 pb-3 pt-5">
            <Link href="/projects" className="text-xs font-semibold text-neutral-400 hover:text-neutral-700">Notice</Link>
            <div className="mt-1 truncate text-[14px] font-semibold text-neutral-900">{project?.name ?? "…"}</div>
            <div className="truncate text-xs text-neutral-500">{project?.location}</div>
          </div>
          <nav className="flex-1 space-y-px px-2">
            {NAV.map(([href, label]) => {
              const full = base + href;
              const active = pathname.startsWith(full);
              return (
                <Link key={href} href={full} className={`flex items-center rounded-md px-2 py-1.5 text-[13px] ${active ? "bg-neutral-200/70 font-medium text-neutral-900" : "text-neutral-600 hover:bg-neutral-100"}`}>
                  {label}
                  {badge(href)}
                </Link>
              );
            })}
          </nav>
          <div className="space-y-1 p-4 text-[11px] text-neutral-400">
            {system && (
              <div title="LLM provider used by agents">
                Agents: <span className="text-neutral-600">{system.llm_provider}</span> ({system.model})
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
