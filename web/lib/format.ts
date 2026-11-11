export function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s.length === 10 ? `${s}T12:00:00` : s);
  return d.toLocaleDateString("en-IE", { day: "2-digit", month: "short", year: "numeric" });
}

export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("en-IE", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function period(value: number | null, unit: string | null): string {
  if (value === null || !unit) return "—";
  return `${value} ${unit.replace("_", " ")}`;
}

export const CATEGORY_STYLE: Record<string, string> = {
  change: "bg-violet-50 text-violet-800 border-violet-200",
  delay: "bg-orange-50 text-orange-800 border-orange-200",
  instruction: "bg-sky-50 text-sky-800 border-sky-200",
  disruption: "bg-rose-50 text-rose-800 border-rose-200",
  noise: "bg-slate-50 text-slate-600 border-slate-200",
};
