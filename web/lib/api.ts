"use client";

const TOKEN_KEY = "notice.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = opts.body;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  const res = await fetch(`/api${path}`, { ...opts, headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    setToken(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export async function download(path: string, filename: string) {
  const token = getToken();
  const res = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({})))?.detail ?? res.statusText);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---- types --------------------------------------------------------------

export type Citation = {
  document_id: string;
  item_id: string | null;
  clause_ref: string | null;
  char_start: number;
  char_end: number;
  quote: string;
  label: string | null;
  verified: boolean;
};

export type DeadlineT = {
  id: string;
  event_id: string;
  rule_id: string;
  label: string;
  trigger_date: string;
  due_date: string;
  status: string;
  trace: {
    period: number;
    unit: string;
    explanation: string;
    skipped: { date: string; reason: string }[];
    rolled_from: string | null;
  };
  working_days_remaining?: number;
  urgency?: string;
  event?: { ref: string; title: string; category: string };
  condition_precedent?: boolean;
  review_item_id?: string | null;
};

export type ReviewItemT = {
  id: string;
  agent: string;
  kind: string;
  category: string | null;
  title: string;
  summary: string;
  confidence: number;
  low_confidence: boolean;
  status: string;
  priority_date: string | null;
  event_id: string | null;
  draft_id: string | null;
  source_item_id: string | null;
  citations: Citation[];
  payload: any;
  created_at: string;
  draft?: { id: string; subject: string; recipient: string; body: string; version: number; status: string };
  event?: { ref: string; status: string; trigger_date: string; category: string };
  deadlines?: DeadlineT[];
  source_item?: ItemT;
  related_items?: ItemT[];
  actions?: { action: string; comment: string | null; created_at: string }[];
};

export type ItemT = {
  id: string;
  document_id: string;
  kind: string;
  author: string | null;
  subject: string | null;
  timestamp: string | null;
  text: string;
  char_start: number;
  char_end: number;
};

export type RuleT = {
  id: string;
  rule_type: string;
  clause_ref: string;
  title: string;
  summary: string;
  trigger_event: string | null;
  event_categories: string[];
  period_value: number | null;
  period_unit: string | null;
  recipient: string | null;
  required_form: string | null;
  condition_precedent: boolean;
  details: Record<string, any>;
  source_quote: string;
  source_char_start: number | null;
  source_char_end: number | null;
  confidence: number;
  status: string;
  edited: boolean;
};
