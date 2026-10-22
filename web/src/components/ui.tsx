// Small presentational building blocks shared by every page.
import type { ReactNode } from "react";
import { BAND_COLOUR, BAND_RANGE, BANDS, type Band } from "@/lib/data";

export function PageTitle({ title, intro }: { title: string; intro?: ReactNode }) {
  return (
    <div className="mb-8 max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      {intro && <div className="mt-3 text-base leading-relaxed text-ink-2">{intro}</div>}
    </div>
  );
}

export function Section({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section className="mb-12">
      <h2 className="text-lg font-semibold">{title}</h2>
      {intro && <div className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-2">{intro}</div>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-raised p-5 ${className}`}>{children}</div>;
}

/** A single headline number with a label. Proportional figures, by design. */
export function StatTile({ value, label, note }: { value: ReactNode; label: string; note?: ReactNode }) {
  return (
    <Card>
      <div className="text-3xl font-semibold tracking-tight">{value}</div>
      <div className="mt-1 text-sm font-medium text-ink">{label}</div>
      {note && <div className="mt-1 text-sm text-ink-3">{note}</div>}
    </Card>
  );
}

/** A small swatch plus band name, so a band is never shown by colour alone. */
export function BandChip({ band, score }: { band: Band; score?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs font-medium text-ink">
      <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: BAND_COLOUR[band] }} />
      {band}
      {score !== undefined && <span className="tabular text-ink-3">{score}</span>}
    </span>
  );
}

export function BandLegend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {BANDS.map((band) => (
        <li key={band} className="flex items-center gap-1.5">
          <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: BAND_COLOUR[band] }} />
          <span className="text-ink">{band}</span>
          <span className="text-ink-3">({BAND_RANGE[band]})</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * A horizontal stacked bar of band counts. Segments are separated by a 2px
 * surface gap; each has a hover tooltip, and the numbers are always also
 * available in a table next to the chart.
 */
export function BandBar({ counts, label }: { counts: Record<Band, number>; label: string }) {
  const total = BANDS.reduce((sum, b) => sum + counts[b], 0);
  return (
    <div className="flex h-5 w-full gap-[2px]" role="img" aria-label={`${label}: ${BANDS.map((b) => `${counts[b]} ${b}`).join(", ")}`}>
      {BANDS.filter((b) => counts[b] > 0).map((band, i, shown) => (
        <div
          key={band}
          className={`group relative h-full ${i === 0 ? "rounded-l-[4px]" : ""} ${i === shown.length - 1 ? "rounded-r-[4px]" : ""}`}
          style={{ width: `${(100 * counts[band]) / total}%`, background: BAND_COLOUR[band] }}
        >
          <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1.5 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-raised px-2 py-1 text-xs text-ink shadow-sm group-hover:block">
            {band}: <span className="tabular">{counts[band]}</span> of {total}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Table({ head, rows, align }: { head: string[]; rows: ReactNode[][]; align?: ("left" | "right")[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-raised">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-ink-3">
            {head.map((h, i) => (
              <th key={h} className={`px-4 py-2.5 font-medium ${align?.[i] === "right" ? "text-right" : ""}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-hairline last:border-0">
              {row.map((cell, i) => (
                <td key={i} className={`px-4 py-2.5 align-top ${align?.[i] === "right" ? "tabular text-right" : ""}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
