"use client";

/** Small neutral UI atoms. Colour is reserved for urgency (red). */

import { CATEGORY_LABEL } from "@/lib/text";

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  return <span className="text-xs text-neutral-500">{CATEGORY_LABEL[category] ?? category}</span>;
}

export function Confidence({ value, low }: { value: number; low?: boolean }) {
  const isLow = low ?? value < 0.7;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-neutral-500" title="Agent confidence after source verification">
      {isLow && <span className="h-2 w-2 rounded-full border border-neutral-400" />}
      {Math.round(value * 100)}%{isLow ? " · needs checking" : ""}
    </span>
  );
}

const STATUS_TEXT: Record<string, string> = {
  pending: "To review", proposed: "To approve", approved: "Approved", dismissed: "Dismissed", rejected: "Rejected",
  running: "Open", met: "Notice issued", cancelled: "Cancelled", open: "Open", notified: "Notified",
  overdue: "Overdue", due_today: "Due today", drafting: "Drafting…", ready: "Ready to review",
};

export function StatusPill({ status }: { status: string }) {
  const red = status === "overdue" || status === "due_today";
  return <span className={`text-xs ${red ? "text-red-600" : "text-neutral-500"}`}>{STATUS_TEXT[status] ?? status.replace("_", " ")}</span>;
}

export function DaysLeft({ days, status }: { days?: number; status?: string }) {
  if (days === undefined || (status && status !== "running")) return null;
  const red = days <= 3;
  const text = days < 0 ? `${-days} WD overdue` : days === 0 ? "due today" : `${days} WD left`;
  return <span className={red ? "text-red-600" : "text-neutral-500"}>{text}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="p-8 text-center text-sm text-neutral-400">{children}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <p className="text-sm text-red-600">{error}</p>;
}
