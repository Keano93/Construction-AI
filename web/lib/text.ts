/** Find `quote` in `text` ignoring case, whitespace runs and curly quotes. Returns [start, end) in `text`. */
export function findSpan(text: string, quote: string): [number, number] | null {
  const norm = (c: string) => (c === "‘" || c === "’" ? "'" : c === "“" || c === "”" ? '"' : c.toLowerCase());
  const chars: string[] = [];
  const idx: number[] = [];
  let prevSpace = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      if (prevSpace) continue;
      chars.push(" ");
      idx.push(i);
      prevSpace = true;
    } else {
      chars.push(norm(ch));
      idx.push(i);
      prevSpace = false;
    }
  }
  const q = quote.replace(/\s+/g, " ").trim().split("").map(norm).join("").replace(/^["'.\s]+|["'.\s]+$/g, "");
  if (q.length < 8) return null;
  const pos = chars.join("").indexOf(q);
  if (pos < 0) return null;
  return [idx[pos], idx[pos + q.length - 1] + 1];
}

/** Remove agent prefixes and the project name from titles: "Potential change: Riverside - Block B ..." -> "Block B ...". */
export function cleanTitle(title: string, projectName?: string): string {
  let t = title.replace(/^(Potential change|Delay|Instruction|Disruption|Revision|Check: possibly notifiable -|Claim CL-\d+):\s*/i, "");
  const first = projectName?.split(" ")[0];
  if (first) t = t.replace(new RegExp(`^${first}\\s*-\\s*`, "i"), "");
  return t.trim();
}

export const CATEGORY_LABEL: Record<string, string> = {
  change: "Potential change",
  delay: "Delay",
  instruction: "Instruction to confirm",
  disruption: "Disruption",
  noise: "Possible event",
};
