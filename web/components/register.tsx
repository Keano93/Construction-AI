"use client";

/** Register pages: a calm list with a few columns, and a document-style side panel for the selected row. */

export function RegisterLayout({ title, description, actions, filters, children, panel, onClose }: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  filters?: React.ReactNode;
  children: React.ReactNode;
  panel?: React.ReactNode;
  onClose?: () => void;
}) {
  return (
    <div className="flex h-screen">
      <div className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-5xl px-8 pb-16 pt-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-[22px] font-semibold tracking-tight text-neutral-900">{title}</h1>
              {description && <p className="mt-0.5 max-w-2xl text-[13.5px] text-neutral-500">{description}</p>}
            </div>
            {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
          </div>
          {filters && <div className="mt-4 flex flex-wrap items-center gap-3">{filters}</div>}
          <div className="mt-4">{children}</div>
        </div>
      </div>
      {panel && (
        <aside className="h-screen w-[480px] shrink-0 overflow-auto border-l border-neutral-200 bg-white">
          <div className="sticky top-0 flex justify-end bg-white/90 px-4 pt-3 backdrop-blur">
            <button className="text-sm text-neutral-400 hover:text-neutral-900" onClick={onClose} aria-label="Close panel">Close ✕</button>
          </div>
          <div className="px-7 pb-10">{panel}</div>
        </aside>
      )}
    </div>
  );
}

/** A quiet text-only filter: "Show: All · Overdue · This week". */
export function Segments<T extends string>({ label, value, options, onChange }: {
  label?: string; value: T; options: [T, string][]; onChange: (v: T) => void;
}) {
  return (
    <div className="flex items-center gap-1 text-[13px]">
      {label && <span className="mr-1 text-neutral-400">{label}</span>}
      {options.map(([v, text]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`rounded-md px-2 py-0.5 ${value === v ? "bg-neutral-200/70 text-neutral-900" : "text-neutral-500 hover:text-neutral-900"}`}>
          {text}
        </button>
      ))}
    </div>
  );
}

export function RegisterTable({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <table className="w-full">
      <thead><tr>{head.map((h, i) => <th key={i} className="th">{h}</th>)}</tr></thead>
      <tbody>{children}</tbody>
    </table>
  );
}

export function rowClass(selected: boolean) {
  return `cursor-pointer ${selected ? "bg-neutral-100" : "hover:bg-neutral-50"}`;
}

export function PanelTitle({ kicker, title, children }: { kicker?: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="space-y-1 pb-4">
      {kicker && <div className="text-[13px] text-neutral-500">{kicker}</div>}
      <h2 className="text-[20px] font-semibold leading-snug tracking-tight text-neutral-900">{title}</h2>
      {children}
    </div>
  );
}

export function PanelSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5 border-t border-neutral-100 py-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-neutral-400">{label}</h3>
      <div className="text-[14px] leading-relaxed text-neutral-800">{children}</div>
    </section>
  );
}
