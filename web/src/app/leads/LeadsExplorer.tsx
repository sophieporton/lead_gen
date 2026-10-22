"use client";

import { useMemo, useState } from "react";
import { BandBar, BandChip, BandLegend, Card } from "@/components/ui";
import { bandCounts, BANDS, data, type Band, type Lead } from "@/lib/data";

type MarketFilter = "all" | "B2B" | "B2C" | "both";

/** Filters sit in one row above the results they scope. */
export default function LeadsExplorer() {
  const [descKey, setDescKey] = useState(data.descriptions[0].key);
  const [hideProperty, setHideProperty] = useState(true);
  const [newOnly, setNewOnly] = useState(false);
  const [market, setMarket] = useState<MarketFilter>("all");
  const [minBand, setMinBand] = useState<Band>("weak");

  const description = data.descriptions.find((d) => d.key === descKey)!;

  const filtered = useMemo(
    () =>
      data.leads.filter(
        (l) =>
          (!hideProperty || !l.is_property) &&
          (!newOnly || !l.in_crm) &&
          (market === "all" || l.market === market),
      ),
    [hideProperty, newOnly, market],
  );

  const shown = useMemo(() => {
    const cutoff = BANDS.indexOf(minBand);
    return filtered
      .filter((l) => l.scores[descKey] && BANDS.indexOf(l.scores[descKey].band) <= cutoff)
      .sort((a, b) => b.scores[descKey].score - a.scores[descKey].score || a.name.localeCompare(b.name));
  }, [filtered, descKey, minBand]);

  const counts = bandCounts(filtered, descKey);

  return (
    <div>
      <Card className="mb-6">
        <div className="text-sm font-medium">Who are you selling to?</div>
        <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Customer description">
          {data.descriptions.map((d) => (
            <button
              key={d.key}
              role="radio"
              aria-checked={d.key === descKey}
              onClick={() => setDescKey(d.key)}
              className={`rounded-full border px-3 py-1.5 text-sm ${
                d.key === descKey
                  ? "border-accent bg-accent-wash font-medium text-ink"
                  : "border-line text-ink-2 hover:bg-accent-wash"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-2">&ldquo;{description.text}&rdquo;</p>

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-hairline pt-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={hideProperty} onChange={(e) => setHideProperty(e.target.checked)} />
            Hide property companies
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={newOnly} onChange={(e) => setNewOnly(e.target.checked)} />
            Only leads not already in the CRM
          </label>
          <label className="flex items-center gap-2">
            Market
            <select value={market} onChange={(e) => setMarket(e.target.value as MarketFilter)}
              className="rounded-md border border-line bg-surface px-2 py-1">
              <option value="all">All</option>
              <option value="B2B">B2B</option>
              <option value="B2C">B2C</option>
              <option value="both">Both</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            Show
            <select value={minBand} onChange={(e) => setMinBand(e.target.value as Band)}
              className="rounded-md border border-line bg-surface px-2 py-1">
              <option value="strong">Strong only</option>
              <option value="possible">Strong and possible</option>
              <option value="weak">Weak and above</option>
              <option value="not a fit">Everything</option>
            </select>
          </label>
        </div>
      </Card>

      <div className="mb-6">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <div className="text-sm font-medium">
            Fit for &ldquo;{description.label}&rdquo; across {filtered.length} leads
          </div>
          <BandLegend />
        </div>
        <BandBar counts={counts} label={`Fit for ${description.label}`} />
        <div className="mt-1.5 text-xs text-ink-3 tabular">
          {BANDS.map((b) => `${counts[b]} ${b}`).join(" · ")}
        </div>
      </div>

      <div className="mb-3 text-sm text-ink-2">
        Showing {shown.length} of {filtered.length} leads, best fit first.
      </div>
      <ul className="space-y-3">
        {shown.map((lead) => (
          <LeadCard key={lead.company_number} lead={lead} descKey={descKey} />
        ))}
      </ul>
      {shown.length === 0 && <p className="text-sm text-ink-3">No leads match these filters.</p>}
    </div>
  );
}

function LeadCard({ lead, descKey }: { lead: Lead; descKey: string }) {
  const s = lead.scores[descKey];
  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-semibold">{lead.name}</div>
            <div className="mt-0.5 text-sm text-ink-3">
              {lead.sector} · {lead.town ?? lead.postcode_area} · {lead.market}
              {lead.in_crm && " · already in CRM"}
            </div>
          </div>
          <BandChip band={s.band} score={s.score} />
        </div>
        <p className="mt-3 text-sm leading-relaxed text-ink-2">{s.reason}</p>
        {s.opener && (
          <div className="mt-3 rounded-lg bg-accent-wash px-3 py-2 text-sm leading-relaxed">
            <span className="font-medium text-accent-ink">Draft opener: </span>
            {s.opener}
          </div>
        )}
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-ink-3 hover:text-ink">Company profile</summary>
          <dl className="mt-2 grid gap-x-4 gap-y-1.5 text-ink-2 sm:grid-cols-[10rem_1fr]">
            <dt className="text-ink-3">What they sell</dt>
            <dd>{lead.what_they_sell}</dd>
            <dt className="text-ink-3">Customers</dt>
            <dd>{lead.who_they_sell_to}</dd>
            {lead.size_signals.length > 0 && (
              <>
                <dt className="text-ink-3">Size signals</dt>
                <dd>{lead.size_signals.join("; ")}</dd>
              </>
            )}
            {lead.growth_signals.length > 0 && (
              <>
                <dt className="text-ink-3">Growth signals</dt>
                <dd>{lead.growth_signals.join("; ")}</dd>
              </>
            )}
            <dt className="text-ink-3">Website</dt>
            <dd>
              <a href={lead.website} className="text-accent-ink underline-offset-2 hover:underline" rel="noopener noreferrer" target="_blank">
                {lead.domain}
              </a>
            </dd>
            <dt className="text-ink-3">Company number</dt>
            <dd className="tabular">{lead.company_number}</dd>
          </dl>
        </details>
      </Card>
    </li>
  );
}
