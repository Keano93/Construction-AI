"use client";

/**
 * Small, quiet charts for the commercial pack.
 * One series each (no legend; the title names it), one neutral hue, red only for the "overdue" status row
 * (always with its text label). Thin marks, 4px rounded data-ends, hover/focus tooltips, and a table view.
 */

import { useState } from "react";

const BAR = "#525252"; // neutral-600
const URGENT = "#dc2626"; // red-600, status only
const GRID = "#e5e5e5";

export function ChartCard({ title, subtitle, table, children }: { title: string; subtitle?: string; table: React.ReactNode; children: React.ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className="rounded-lg bg-white p-4 ring-1 ring-neutral-200">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span>
          <span className="text-[14px] font-medium text-neutral-900">{title}</span>
          {subtitle && <span className="block text-xs text-neutral-500">{subtitle}</span>}
        </span>
        <button className="text-xs text-neutral-500 underline decoration-neutral-300 underline-offset-2 hover:text-neutral-900" onClick={() => setAsTable(!asTable)}>
          {asTable ? "Chart" : "Table"}
        </button>
      </figcaption>
      <div className="mt-3">{asTable ? table : children}</div>
    </figure>
  );
}

/** Columns over time (weeks). Columns <= 24px, rounded top, square at the baseline, tooltip on hover/focus. */
export function Columns({ data, label, unit = "item" }: { data: { key: string; label: string; value: number; detail?: string }[]; label: string; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 360, H = 150, padL = 26, padB = 22, padT = 10;
  const max = Math.max(1, ...data.map((d) => d.value));
  const niceMax = max <= 4 ? max : Math.ceil(max / 2) * 2;
  const plotW = W - padL - 4, plotH = H - padB - padT;
  const slot = plotW / Math.max(data.length, 1);
  const bw = Math.min(24, slot * 0.5);
  const y = (v: number) => padT + plotH - (v / niceMax) * plotH;
  const ticks = niceMax <= 4 ? Array.from({ length: niceMax + 1 }, (_, i) => i) : [0, niceMax / 2, niceMax];
  const every = Math.ceil(data.length / 8); // keep x labels from colliding

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - 4} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 3.5} textAnchor="end" fontSize="10" fill="#737373">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = padL + slot * i + slot / 2;
          const h = (d.value / niceMax) * plotH;
          const top = padT + plotH - h, r = Math.min(4, h);
          const path = h > 0
            ? `M${cx - bw / 2},${padT + plotH} V${top + r} Q${cx - bw / 2},${top} ${cx - bw / 2 + r},${top} H${cx + bw / 2 - r} Q${cx + bw / 2},${top} ${cx + bw / 2},${top + r} V${padT + plotH} Z`
            : "";
          return (
            <g key={d.key} tabIndex={0} aria-label={`${d.label}: ${d.value}`} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)} onBlur={() => setHover(null)} className="outline-none">
              <rect x={cx - slot / 2} y={padT} width={slot} height={plotH} fill="transparent" />
              {path && <path d={path} fill={BAR} opacity={hover === null || hover === i ? 1 : 0.55} />}
              {i % every === 0 && <text x={cx} y={H - 6} textAnchor="middle" fontSize="10" fill="#737373">{d.label}</text>}
            </g>
          );
        })}
      </svg>
      {hover !== null && data[hover] && (
        <div className="pointer-events-none absolute top-0 rounded-md bg-white px-2.5 py-1.5 text-xs shadow-md ring-1 ring-neutral-200"
          style={(() => {
            const pct = ((padL + slot * hover + slot / 2) / W) * 100; // anchor proportionally so the tooltip stays inside the card
            return { left: `${pct}%`, transform: `translateX(-${pct}%)` };
          })()}>
          <div className="whitespace-nowrap text-[13px] font-semibold text-neutral-900">{data[hover].value} {unit}{data[hover].value === 1 ? "" : "s"}</div>
          <div className="whitespace-nowrap text-neutral-500">{data[hover].detail ?? data[hover].label}</div>
        </div>
      )}
    </div>
  );
}

/** Meter list: name, bar, figure per row; bars share one scale. Ranked by the caller. */
export function BarList({ rows, format = (v) => String(v) }: {
  rows: { key: string; label: string; value: number; urgent?: boolean; note?: string }[];
  format?: (v: number) => string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-3 text-[13px]" title={`${r.label}: ${format(r.value)}`}>
          <span className={r.urgent && r.value > 0 ? "text-red-600" : "text-neutral-600"}>{r.label}</span>
          <span className="h-2 rounded-full bg-neutral-100">
            {r.value > 0 && <span className="block h-2 rounded-full" style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: r.urgent ? URGENT : BAR }} />}
          </span>
          <span className="text-right tabular-nums text-neutral-900">{format(r.value)}</span>
        </li>
      ))}
    </ul>
  );
}

export function MiniTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="w-full text-[13px]">
      <thead><tr>{head.map((h, i) => <th key={i} className={`pb-1 text-left text-xs font-normal text-neutral-400 ${i === head.length - 1 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={`border-t border-neutral-100 py-1 ${j === r.length - 1 ? "text-right tabular-nums" : ""}`}>{c}</td>)}</tr>)}</tbody>
    </table>
  );
}
