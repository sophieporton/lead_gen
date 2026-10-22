import Link from "next/link";
import { Card, Section, StatTile } from "@/components/ui";
import { data, pct, SITE } from "@/lib/data";

const f = data.funnel;
const e = data.evaluation;

const FUNNEL = [
  { value: f.active_north_east, label: "Active companies", note: "NE, SR, DH, TS and DL postcodes" },
  { value: f.eligible_small_companies, label: "Small, trading companies", note: "after accounts and SIC filters" },
  { value: f.sampled, label: "Sampled for this demo", note: "checked against the live register" },
  { value: f.website_found, label: "Possible website found", note: "via search, then checked" },
  { value: f.website_verified, label: "Website verified", note: "the LLM agrees it is theirs" },
  { value: f.new_leads, label: "New leads", note: `${f.already_in_crm} were already in the CRM` },
];

const STEPS = [
  ["Find companies", "Pulls active small companies from Companies House by area, size and industry."],
  ["Find their websites", "Companies House has no websites, so each company is searched for and the result checked against its company number and postcode."],
  ["Read the website", "Fetches the homepage and about page politely, respecting robots.txt."],
  ["Profile with an LLM", "Claude reads each site and returns a structured profile: what they sell, to whom, B2B or B2C, size and growth signals."],
  ["Score and draft", "Scores every lead against your ideal customer description, explains the score and drafts a short opening line."],
  ["Clean for your CRM", "Matches leads against your existing CRM, removes duplicates and exports a HubSpot-ready file."],
];

export default function Home() {
  return (
    <>
      <div className="mb-12 max-w-3xl">
        <p className="text-sm font-medium text-accent-ink">Working demo</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Find and qualify small-business leads, with the research done for you
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-2">
          This pipeline starts from public company records, finds each company&apos;s website, reads it with an
          LLM and scores how well it fits your ideal customer. The output is a de-duplicated, CRM-ready list
          with a reason for every score. Below it is run on {f.sampled} small companies in the North East of
          England.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/leads" className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
            Browse the scored leads
          </Link>
          <Link href="/evaluation" className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink hover:bg-accent-wash">
            See how accurate it is
          </Link>
        </div>
      </div>

      <Section title="From the whole region to a short list" intro="Each step narrows the list. Every number here comes from the real run.">
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FUNNEL.map((step, i) => (
            <li key={step.label}>
              <StatTile
                value={step.value.toLocaleString("en-GB")}
                label={`${i + 1}. ${step.label}`}
                note={step.note}
              />
            </li>
          ))}
        </ol>
        <p className="mt-3 max-w-3xl text-sm text-ink-3">
          Only {pct(f.website_verified, f.sampled)}% of sampled companies have a website that is verifiably
          theirs. Property companies almost never do ({f.property_verified} of {f.property_sampled}), so the
          leads page lets you hide them.
        </p>
      </Section>

      <Section title="Results at a glance">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            value={`${pct(e.website.agree, e.website.total)}%`}
            label="Website check agrees with a person"
            note={`${e.website.agree} of ${e.website.total} hand-checked companies`}
          />
          <StatTile
            value={`${pct(e.fit.within_one, e.fit.total)}%`}
            label="Fit scores within one band of a person"
            note={`up from ${pct(e.fit.before_fix.within_one, e.fit.before_fix.total)}% before a prompt fix`}
          />
          <StatTile
            value={`${data.crm.duplicate_pairs_found} of ${data.crm.duplicate_pairs_total}`}
            label="CRM duplicates caught"
            note={`${data.crm.false_merges} companies wrongly merged`}
          />
          <StatTile
            value={`$${data.costs.enrich_per_1000_companies.toFixed(2)}`}
            label="LLM cost per 1,000 companies"
            note={`whole project: $${data.costs.project_total_usd.toFixed(2)}`}
          />
        </div>
      </Section>

      <Section title="How it works">
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map(([title, text], i) => (
            <li key={title}>
              <Card className="h-full">
                <div className="text-sm font-medium text-accent-ink">Step {i + 1}</div>
                <div className="mt-1 font-semibold">{title}</div>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{text}</p>
              </Card>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="What I can build for you">
        <Card>
          <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
            <div className="space-y-3 text-sm leading-relaxed text-ink-2">
              <p>
                The same pipeline can be pointed at your market: a different region, industry or company size,
                scored against your own ideal customer.
              </p>
              <ul className="list-disc space-y-1 pl-5">
                <li>A list of qualified leads with the reasoning for each score</li>
                <li>Matching against your existing CRM, so you only get companies you don&apos;t already have</li>
                <li>A HubSpot-ready import file, or a CSV for any other CRM</li>
                <li>A short accuracy check against hand-labelled examples, so you know how far to trust it</li>
              </ul>
              <p>
                It uses company-level public data only, with no personal names, emails or phone numbers, which
                keeps it simple under UK GDPR.
              </p>
            </div>
            <div className="flex flex-col justify-center gap-3">
              <a href={SITE.contactUrl} className="rounded-lg bg-accent px-4 py-2 text-center text-sm font-medium text-white hover:opacity-90">
                {SITE.contactLabel}
              </a>
              <a href={SITE.githubUrl} className="rounded-lg border border-line px-4 py-2 text-center text-sm font-medium text-ink hover:bg-accent-wash">
                View the source code
              </a>
            </div>
          </div>
        </Card>
      </Section>
    </>
  );
}
