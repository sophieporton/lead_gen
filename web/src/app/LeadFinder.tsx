"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import LeadCard from "@/components/LeadCard";
import { BandBar, BandLegend, Card } from "@/components/ui";
import { bandCounts, BANDS, data, type Band, type Description, type Lead } from "@/lib/data";

const f = data.funnel;
const STEP_MS = 650;

/**
 * Match what the visitor typed to the closest example search, by counting
 * keyword hits. Short keywords ("it", "ev") must match a whole word.
 */
function matchDescription(text: string): Description | null {
  const q = ` ${text.toLowerCase().replace(/[^a-z0-9 ]/g, " ")} `;
  let best: Description | null = null;
  let bestScore = 0;
  for (const d of data.descriptions) {
    const words = [d.label.toLowerCase(), ...d.keywords];
    const score = words.reduce(
      (sum, w) => sum + (w.length <= 3 ? (q.includes(` ${w} `) ? 1 : 0) : q.includes(w) ? w.split(" ").length : 0),
      0,
    );
    if (score > bestScore) [best, bestScore] = [d, score];
  }
  return best;
}

function pipelineSteps(label: string) {
  return [
    { title: "Searching Companies House", detail: `${f.active_north_east.toLocaleString("en-GB")} active companies in NE, SR, DH, TS and DL postcodes` },
    { title: "Filtering to small, trading companies", detail: `${f.eligible_small_companies.toLocaleString("en-GB")} file small company accounts` },
    { title: "Checking the live register", detail: `${f.sampled} sampled and confirmed still active` },
    { title: "Finding and verifying websites", detail: `${f.website_verified} have a website that is verifiably theirs` },
    { title: "Reading websites and scoring fit", detail: `Scoring ${f.website_verified} companies for “${label}”` },
    { title: "Checking your CRM", detail: `${f.already_in_crm} already in your CRM, flagged so you don't contact them twice` },
  ];
}

function downloadCsv(leads: Lead[], d: Description) {
  const cols = ["Company", "Town", "Sector", "Market", "Website", "Fit score", "Fit band", "Reason", "Draft opener", "Already in CRM", "Company number"];
  const esc = (v: string | number | boolean | null) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = leads.map((l) => {
    const s = l.scores[d.key];
    return [l.name, l.town, l.sector, l.market, l.website, s.score, s.band, s.reason, s.opener, l.in_crm ? "yes" : "no", l.company_number].map(esc).join(",");
  });
  const blob = new Blob(["﻿" + [cols.join(","), ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `leads-${d.key}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function LeadFinder() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<Description | null>(null);
  const [noMatch, setNoMatch] = useState(false);
  const [step, setStep] = useState(-1); // -1 idle; 0..n running; n done
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return data.descriptions;
    return data.descriptions.filter(
      (d) => d.label.toLowerCase().includes(q) || d.keywords.some((k) => k.startsWith(q) || q.includes(k)),
    );
  }, [query]);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  function run(d: Description) {
    setActive(d);
    setQuery(d.label);
    setOpen(false);
    setNoMatch(false);
    if (timer.current) clearInterval(timer.current);
    const steps = pipelineSteps(d.label).length;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      setStep(steps);
      return;
    }
    setStep(0);
    timer.current = setInterval(() => {
      setStep((s) => {
        if (s + 1 >= steps && timer.current) clearInterval(timer.current);
        return s + 1;
      });
    }, STEP_MS);
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const d = matchDescription(query);
    if (d) run(d);
    else {
      setNoMatch(true);
      setOpen(false);
    }
  }

  const steps = active ? pipelineSteps(active.label) : [];
  const done = active !== null && step >= steps.length;

  return (
    <div>
      <form onSubmit={submit} className="relative max-w-2xl">
        <label htmlFor="sell" className="text-sm font-medium">What does your company sell?</label>
        <div className="mt-2 flex gap-2">
          <input
            id="sell"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setOpen(true); setNoMatch(false); }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            placeholder="e.g. card machines, van leasing, office cleaning"
            autoComplete="off"
            role="combobox"
            aria-expanded={open}
            aria-controls="suggestions"
            className="w-full rounded-lg border border-line bg-raised px-4 py-3 text-base outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
          />
          <button type="submit" className="shrink-0 rounded-lg bg-accent px-5 py-3 text-sm font-medium text-white hover:opacity-90">
            Find leads
          </button>
        </div>
        {open && suggestions.length > 0 && (
          <ul id="suggestions" role="listbox" className="absolute z-20 mt-1 max-h-80 w-full overflow-auto rounded-lg border border-line bg-raised py-1 shadow-lg">
            {suggestions.map((d) => (
              <li key={d.key} role="option" aria-selected={active?.key === d.key}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => run(d)}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-accent-wash"
                >
                  <span className="font-medium text-ink">{d.label}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </form>

      <div className="mt-3 flex max-w-3xl flex-wrap gap-2">
        {data.descriptions.map((d) => (
          <button
            key={d.key}
            onClick={() => run(d)}
            className={`rounded-full border px-3 py-1 text-sm ${active?.key === d.key ? "border-accent bg-accent-wash text-ink" : "border-line text-ink-2 hover:bg-accent-wash"}`}
          >
            {d.label}
          </button>
        ))}
      </div>
      <p className="mt-3 max-w-2xl text-sm text-ink-3">
        This demo offers ten example searches. On a real project you describe your ideal customer in your own
        words, and the pipeline runs on your chosen region and company types.
      </p>

      {noMatch && (
        <Card className="mt-6 max-w-2xl">
          <p className="text-sm text-ink-2">
            That isn&apos;t one of the example searches in this demo. Try one of the options above, or{" "}
            <a href="/how-it-works#build" className="text-accent-ink underline">see what a full project covers</a>.
          </p>
        </Card>
      )}

      <div ref={resultsRef} className="scroll-mt-6">
        {active && (
          <Card className="mt-8">
            <div className="text-sm font-medium">Finding buyers for “{active.label}”</div>
            <ol className="mt-3 space-y-2">
              {steps.map((s, i) => {
                const state = step > i ? "done" : step === i ? "running" : "waiting";
                return (
                  <li key={s.title} className={`flex gap-3 text-sm ${state === "waiting" ? "opacity-40" : ""}`}>
                    <span aria-hidden className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line text-xs">
                      {state === "done" ? <span className="text-good">✓</span> : state === "running" ? <span className="h-2 w-2 animate-pulse rounded-full bg-accent" /> : ""}
                    </span>
                    <span>
                      <span className="font-medium text-ink">{s.title}</span>
                      {state !== "waiting" && <span className="text-ink-3"> · {s.detail}</span>}
                    </span>
                  </li>
                );
              })}
            </ol>
            <p className="mt-3 text-xs text-ink-3">
              Demo mode: these steps replay a run made in advance on a sample of {f.sampled} North East companies,
              so results appear in seconds. On a client project each step runs live.
            </p>
          </Card>
        )}
        {done && active && <Results description={active} />}
      </div>
    </div>
  );
}

function Results({ description }: { description: Description }) {
  const [hideProperty, setHideProperty] = useState(true);
  const [newOnly, setNewOnly] = useState(false);
  const [minBand, setMinBand] = useState<Band>("possible");
  const key = description.key;

  const pool = data.leads.filter((l) => (!hideProperty || !l.is_property) && (!newOnly || !l.in_crm) && l.scores[key]);
  const cutoff = BANDS.indexOf(minBand);
  const shown = pool
    .filter((l) => BANDS.indexOf(l.scores[key].band) <= cutoff)
    .sort((a, b) => b.scores[key].score - a.scores[key].score || a.name.localeCompare(b.name));
  const counts = bandCounts(pool, key);

  return (
    <div className="mt-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-3xl">
          <h2 className="text-xl font-semibold">
            {counts.strong + counts.possible} likely buyers for “{description.label}”
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-2">
            Scored against this customer description: “{description.text}”
          </p>
        </div>
        <button
          onClick={() => downloadCsv(shown, description)}
          className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-accent-wash"
        >
          Download CSV
        </button>
      </div>

      <div className="mt-5">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <div className="text-sm text-ink-2">Fit across all {pool.length} researched companies</div>
          <BandLegend />
        </div>
        <BandBar counts={counts} label={`Fit for ${description.label}`} />
        <div className="tabular mt-1.5 text-xs text-ink-3">{BANDS.map((b) => `${counts[b]} ${b}`).join(" · ")}</div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-y border-hairline py-3 text-sm">
        <label className="flex items-center gap-2">
          Show
          <select value={minBand} onChange={(e) => setMinBand(e.target.value as Band)} className="rounded-md border border-line bg-surface px-2 py-1">
            <option value="strong">Strong fits only</option>
            <option value="possible">Strong and possible</option>
            <option value="weak">Weak and above</option>
            <option value="not a fit">Everything</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={hideProperty} onChange={(e) => setHideProperty(e.target.checked)} />
          Hide property companies
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={newOnly} onChange={(e) => setNewOnly(e.target.checked)} />
          Hide companies already in my CRM
        </label>
        <span className="text-ink-3">{shown.length} shown</span>
      </div>

      <ul className="mt-4 space-y-3">
        {shown.map((lead, i) => (
          <LeadCard key={lead.company_number} lead={lead} descKey={key} rank={i + 1} />
        ))}
      </ul>
      {shown.length === 0 && (
        <p className="mt-4 text-sm text-ink-3">No leads at this level. Try showing weaker fits.</p>
      )}
    </div>
  );
}
