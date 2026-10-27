import type { Metadata } from "next";
import { BandBar, BandLegend, Card, PageTitle, Section, StatTile, Table } from "@/components/ui";
import { bandCounts, BANDS, data } from "@/lib/data";

export const metadata: Metadata = { title: "Pipeline and data quality | Lead Research Pipeline" };

/** Show counts as whole numbers and shares with one decimal place. */
function formatMeasure(measure: string, value: number) {
  return measure.includes("(%)") ? `${value.toFixed(1)}%` : Math.round(value).toLocaleString("en-GB");
}

export default function PipelinePage() {
  const { crm, costs } = data;
  const leads = data.leads.filter((l) => !l.is_property);

  return (
    <>
      <PageTitle
        title="Pipeline and data quality"
        intro={`How the leads are distributed across the ${data.descriptions.length} example searches, what cleaning did to a messy CRM export, and what the LLM calls cost.`}
      />

      <Section
        title="How well the leads fit each kind of customer"
        intro={`The same ${leads.length} leads (property companies excluded), scored against ${data.descriptions.length} different customer descriptions. Hover a segment for its count; the table below has every number.`}
      >
        <Card>
          <div className="mb-4">
            <BandLegend />
          </div>
          <div className="space-y-4">
            {data.descriptions.map((d) => (
              <div key={d.key} className="grid items-center gap-2 sm:grid-cols-[16rem_1fr]">
                <div className="text-sm text-ink">{d.label}</div>
                <BandBar counts={bandCounts(leads, d.key)} label={d.label} />
              </div>
            ))}
          </div>
        </Card>
        <div className="mt-4">
          <Table
            head={["Customer description", ...BANDS]}
            align={["left", "right", "right", "right", "right"]}
            rows={data.descriptions.map((d) => {
              const c = bandCounts(leads, d.key);
              return [d.label, ...BANDS.map((b) => c[b])];
            })}
          />
        </div>
      </Section>

      <Section
        title="Cleaning a messy CRM export"
        intro="The CRM data here is synthetic: 220 records made deliberately messy, with duplicates, typos, websites with and without www, postcodes in every format and free-text industries. The cleaned version is what new leads are matched against."
      >
        <Table
          head={["Measure", "Before cleaning", "After cleaning"]}
          align={["left", "right", "right"]}
          rows={crm.quality.map((q) => [q.measure.replace(" (%)", ""), formatMeasure(q.measure, q.before), formatMeasure(q.measure, q.after)])}
        />
        <p className="mt-3 max-w-3xl text-sm text-ink-3">
          Remaining gaps are values that were missing in every copy of a record, which cleaning cannot invent.
        </p>
      </Section>

      <Section
        title="Finding duplicates and existing leads"
        intro="Records count as the same company if they share a company number or website, or have the same cleaned name and postcode, or very similar names and the same postcode. Results are checked against an answer key."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <StatTile
            value={`${crm.duplicate_pairs_found} of ${crm.duplicate_pairs_total}`}
            label="Duplicate pairs found"
            note="the misses combine a typo with missing data"
          />
          <StatTile value={crm.false_merges} label="Companies wrongly merged" note="a stricter rule was kept on purpose" />
          <StatTile
            value={`${crm.existing_leads_found} of ${crm.existing_leads_total}`}
            label="Existing leads recognised"
            note={`${crm.false_existing} false matches`}
          />
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-2">
          A looser rule found 59 of 60 duplicate pairs but merged &ldquo;Tees Print &amp; Design&rdquo; with
          &ldquo;Bede Print &amp; Design&rdquo;. In a CRM, merging two real companies loses data, while a missed
          duplicate only leaves an extra row, so the stricter rule was kept.
        </p>
      </Section>

      <Section title="What the LLM calls cost" intro={`All LLM work uses ${costs.model}. Responses are cached, so re-running costs nothing.`}>
        <div className="grid gap-3 sm:grid-cols-3">
          <StatTile value={`$${costs.enrich_per_1000_companies.toFixed(2)}`} label="Per 1,000 companies profiled" />
          <StatTile value={`$${costs.score_per_1000_pairs.toFixed(2)}`} label="Per 1,000 fit scores" note="one company against one customer description" />
          <StatTile
            value={`$${costs.project_total_usd.toFixed(2)}`}
            label="Whole project so far"
            note={`${costs.project_total_calls} calls, including discarded prompt versions`}
          />
        </div>
      </Section>
    </>
  );
}
