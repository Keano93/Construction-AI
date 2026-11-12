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

/** Plain-English notice compliance line from the claims agent's computed state. */
export function complianceText(c: { state: string; due_date: string; met_on?: string | null }): string {
  switch (c.state) {
    case "given_in_time": return `Given in time on ${fmtDate(c.met_on)}`;
    case "given_late": return `Given late on ${fmtDate(c.met_on)} — was due ${fmtDate(c.due_date)}`;
    case "not_given_overdue": return `Not given — was due ${fmtDate(c.due_date)}`;
    case "not_given_open": return `Not given yet — due ${fmtDate(c.due_date)}`;
    case "cancelled": return "Clock cancelled";
    default: return fmtDate(c.due_date);
  }
}
