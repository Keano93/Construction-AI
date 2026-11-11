"use client";

import { CATEGORY_STYLE } from "@/lib/format";

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  return (
    <span className={`inline-block rounded border px-1.5 py-px text-2xs font-semibold uppercase tracking-wide ${CATEGORY_STYLE[category] ?? CATEGORY_STYLE.noise}`}>
      {category}
    </span>
  );
}

export function Confidence({ value, low }: { value: number; low?: boolean }) {
  const pct = Math.round(value * 100);
  const isLow = low ?? value < 0.7;
  return (
    <span
      title={isLow ? "Low confidence: check carefully before approving" : "Model confidence after source verification"}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-px text-2xs font-semibold ${isLow ? "bg-amber-100 text-amber-900" : "bg-emerald-50 text-emerald-800"}`}
    >
      <span className="inline-block h-1.5 w-8 overflow-hidden rounded bg-white/70">
        <span className={`block h-full ${isLow ? "bg-amber-500" : "bg-emerald-600"}`} style={{ width: `${pct}%` }} />
      </span>
      {pct}%{isLow ? " · low" : ""}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "bg-amber-50 text-amber-800",
    proposed: "bg-amber-50 text-amber-800",
    approved: "bg-emerald-50 text-emerald-800",
    dismissed: "bg-slate-100 text-slate-500",
    rejected: "bg-slate-100 text-slate-500",
    running: "bg-sky-50 text-sky-800",
    met: "bg-emerald-50 text-emerald-800",
    cancelled: "bg-slate-100 text-slate-500",
    open: "bg-sky-50 text-sky-800",
    notified: "bg-emerald-50 text-emerald-800",
    overdue: "bg-rose-100 text-rose-800",
    due_today: "bg-rose-50 text-rose-700",
  };
  return <span className={`rounded px-1.5 py-px text-2xs font-semibold ${map[status] ?? "bg-slate-100 text-slate-600"}`}>{status.replace("_", " ")}</span>;
}

export function DaysLeft({ days, status }: { days?: number; status?: string }) {
  if (days === undefined) return null;
  const cls = days < 0 ? "text-rose-700 font-semibold" : days <= 3 ? "text-orange-700 font-semibold" : "text-slate-700";
  const text = days < 0 ? `${-days} WD overdue` : days === 0 ? "due today" : `${days} WD left`;
  return <span className={cls}>{status === "running" || !status ? text : "—"}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="p-6 text-center text-xs text-slate-500">{children}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">{error}</div>;
}
