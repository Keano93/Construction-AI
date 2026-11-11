"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "demo@brennock.example", password: "riverside-demo", name: "", organisation: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      const res = await api<{ token: string }>(`/auth/${mode}`, { method: "POST", json: body });
      setToken(res.token);
      router.push("/projects");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-3 p-5">
        <div>
          <h1 className="text-lg font-semibold">Notice</h1>
          <p className="text-xs text-slate-500">Commercial assistant for contractors. Agents draft, humans approve.</p>
        </div>
        {mode === "register" && (
          <>
            <label className="block space-y-1"><span className="label">Organisation</span><input className="input" value={form.organisation} onChange={set("organisation")} required /></label>
            <label className="block space-y-1"><span className="label">Your name</span><input className="input" value={form.name} onChange={set("name")} required /></label>
          </>
        )}
        <label className="block space-y-1"><span className="label">Email</span><input className="input" type="email" value={form.email} onChange={set("email")} required /></label>
        <label className="block space-y-1"><span className="label">Password</span><input className="input" type="password" value={form.password} onChange={set("password")} required minLength={8} /></label>
        <ErrorBox error={error} />
        <button className="btn-primary w-full justify-center py-1.5" disabled={busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="w-full text-center text-2xs text-slate-500 hover:underline" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New organisation? Create an account" : "Have an account? Sign in"}
        </button>
        {mode === "login" && <p className="text-center text-2xs text-slate-400">Demo: demo@brennock.example / riverside-demo</p>}
      </form>
    </main>
  );
}
