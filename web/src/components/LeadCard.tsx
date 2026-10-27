import { BandChip, Card } from "@/components/ui";
import type { Lead } from "@/lib/data";

/** One scored lead: score, reason, draft opener and an expandable profile. */
export default function LeadCard({ lead, descKey, rank }: { lead: Lead; descKey: string; rank?: number }) {
  const s = lead.scores[descKey];
  return (
    <li>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex gap-3">
            {rank !== undefined && <span className="tabular pt-0.5 text-sm text-ink-3">{rank}.</span>}
            <div>
              <div className="font-semibold">{lead.name}</div>
              <div className="mt-0.5 text-sm text-ink-3">
                {lead.sector} · {lead.town ?? lead.postcode_area} · {lead.market}
                {lead.in_crm && " · already in your CRM"}
              </div>
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
