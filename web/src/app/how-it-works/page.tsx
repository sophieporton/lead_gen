import type { Metadata } from "next";
import { Card, PageTitle, Section, StatTile } from "@/components/ui";
import { data, pct, SITE } from "@/lib/data";

export const metadata: Metadata = { title: "How it works | Lead Research Pipeline" };

const f = data.funnel;
const c = data.costs;

const FUNNEL = [
  { value: f.active_north_east, label: "Active companies", note: "NE, SR, DH, TS and DL postcodes" },
  { value: f.eligible_small_companies, label: "Small, trading companies", note: "after accounts and industry filters" },
  { value: f.sampled, label: "Sampled for this demo", note: "checked against the live register" },
  { value: f.website_found, label: "Possible website found", note: "via web search, then checked" },
  { value: f.website_verified, label: "Website verified", note: "the LLM agrees it is theirs" },
  { value: f.new_leads, label: "New leads", note: `${f.already_in_crm} were already in the CRM` },
];

const STEPS: { title: string; what: string; how: string }[] = [
  {
    title: "Find companies",
    what: "Starts from the official register of UK companies, not a bought list.",
    how: "Companies House data is filtered by postcode area, company size (the accounts they file) and industry codes, dropping dormant and holding companies. Each sampled company is re-checked against the live register.",
  },
  {
    title: "Find their websites",
    what: "Companies House doesn't record websites, so the pipeline searches for each one.",
    how: "A web search for the company name and town. Directory and social media sites are removed, including any domain that turns up for several unrelated companies. Each remaining site is checked for the company's registered number and postcode.",
  },
  {
    title: "Read the website",
    what: "Fetches the homepage and about page, the way a researcher would.",
    how: "Respects each site's robots.txt, waits between requests and identifies itself. Email addresses and phone numbers are stripped before anything is stored.",
  },
  {
    title: "Profile each company with an LLM",
    what: `Claude (${c.model}) reads the page text and fills in a fixed form.`,
    how: "It decides whether the website really belongs to the company, then records what they sell, who they sell to, whether that is B2B or B2C, and any size or growth facts stated on the site. It is told to use only what the pages say and to leave fields empty rather than guess.",
  },
  {
    title: "Score fit and draft an opener",
    what: "Each profile is scored from 0 to 100 against your ideal customer.",
    how: "The score comes with a one-sentence reason citing the facts behind it. Leads scoring 50 or more get a two-sentence opening line for a cold email that mentions something specific about the company.",
  },
  {
    title: "Clean for your CRM",
    what: "Matches new leads against what you already have.",
    how: "Your CRM export is standardised (names, websites, postcodes, towns, dates) and de-duplicated, then each lead is matched by company number, website or name and postcode. New leads are exported as a HubSpot-ready file.",
  },
];

const PROFILE_FIELDS = [
  ["Website belongs to them", "yes, no or unsure, with a reason"],
  ["What they sell", "one plain sentence, plus up to five products or services"],
  ["Who they sell to", "one sentence on their customers"],
  ["Market", "B2B, B2C, both or unclear"],
  ["Sector", "a short label, e.g. roofing contractor"],
  ["Size and growth signals", "countable facts only, e.g. 3 branches, established 1891, hiring"],
];

const SCORE_BANDS = [
  ["80 to 100", "Strong", "clearly matches the ideal customer, with evidence"],
  ["50 to 79", "Possible", "plausibly a customer, some evidence missing"],
  ["20 to 49", "Weak", "a partial match"],
  ["0 to 19", "Not a fit", "not a sensible prospect, or too little to judge"],
];

export default function HowItWorksPage() {
  return (
    <>
      <PageTitle
        title="How it works"
        intro="The pipeline does the research a sales team would do by hand: find companies, find their websites, read them, decide who is worth contacting and why. This page explains each step and how the LLM is used."
      />

      <Section title="From the whole region to a short list" intro="The numbers from the run behind this demo.">
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FUNNEL.map((step, i) => (
            <li key={step.label}>
              <StatTile value={step.value.toLocaleString("en-GB")} label={`${i + 1}. ${step.label}`} note={step.note} />
            </li>
          ))}
        </ol>
        <p className="mt-3 max-w-3xl text-sm text-ink-3">
          Only {pct(f.website_verified, f.sampled)}% of sampled companies have a website that is verifiably theirs.
          Property companies almost never do ({f.property_verified} of {f.property_sampled}), which is why the
          demo hides them by default.
        </p>
      </Section>

      <Section title="The six steps">
        <ol className="grid gap-3 md:grid-cols-2">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <Card className="h-full">
                <div className="text-sm font-medium text-accent-ink">Step {i + 1}</div>
                <div className="mt-1 font-semibold">{s.title}</div>
                <p className="mt-1.5 text-sm font-medium leading-relaxed text-ink">{s.what}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{s.how}</p>
              </Card>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        title="How the LLM is used"
        intro="The model never browses or searches on its own. It only reads text the pipeline has already collected, and it must answer in a fixed format that is checked before anything is saved."
      >
        <div className="grid gap-3 lg:grid-cols-2">
          <Card>
            <div className="font-semibold">Call 1: company profile</div>
            <p className="mt-1 text-sm text-ink-2">One call per company, reading its homepage and about page.</p>
            <dl className="mt-3 space-y-2 text-sm">
              {PROFILE_FIELDS.map(([field, desc]) => (
                <div key={field} className="grid gap-x-3 sm:grid-cols-[11rem_1fr]">
                  <dt className="font-medium text-ink">{field}</dt>
                  <dd className="text-ink-2">{desc}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card>
            <div className="font-semibold">Call 2: fit score</div>
            <p className="mt-1 text-sm text-ink-2">
              One call per company and customer type, reading the short profile rather than the whole website,
              which keeps it cheap.
            </p>
            <table className="mt-3 w-full text-sm">
              <tbody>
                {SCORE_BANDS.map(([range, band, desc]) => (
                  <tr key={band} className="border-b border-hairline last:border-0">
                    <td className="tabular py-1.5 pr-3 text-ink-3">{range}</td>
                    <td className="py-1.5 pr-3 font-medium">{band}</td>
                    <td className="py-1.5 text-ink-2">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-sm text-ink-2">Plus a one-sentence reason, and an opener for scores of 50 or more.</p>
          </Card>
        </div>

        <Card className="mt-3">
          <div className="font-semibold">Rules the model works to</div>
          <ul className="mt-2 grid list-disc gap-x-8 gap-y-1.5 pl-5 text-sm leading-relaxed text-ink-2 md:grid-cols-2">
            <li>Use only what the website says; leave a field empty rather than guess.</li>
            <li>A different address on the site is not on its own evidence against a match, because many small firms register at their accountant&apos;s office.</li>
            <li>Never name individual people; refer to them by role. Output is also checked automatically for names after every run.</li>
            <li>Don&apos;t lower a fit score just because a website doesn&apos;t state headcount, when the kind of work clearly implies staff.</li>
            <li>Openers must only mention facts from the profile: no praise, awards or guesses about how successful a company is.</li>
            <li>Every answer is validated against a fixed schema before it is stored, and every call is logged with its token count and cost.</li>
          </ul>
        </Card>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <StatTile value={`$${c.enrich_per_1000_companies.toFixed(2)}`} label="Per 1,000 companies profiled" />
          <StatTile value={`$${c.score_per_1000_pairs.toFixed(2)}`} label="Per 1,000 fit scores" />
          <StatTile value={`$${c.project_total_usd.toFixed(2)}`} label="LLM cost of this whole project" note="including discarded prompt versions" />
        </div>
      </Section>

      <div id="build" className="scroll-mt-6">
        <Section title="What I can build for you">
          <Card>
            <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
              <div className="space-y-3 text-sm leading-relaxed text-ink-2">
                <p>
                  The same pipeline, pointed at your market: your region, industries and company sizes, scored
                  against your ideal customer in your own words.
                </p>
                <ul className="list-disc space-y-1 pl-5">
                  <li>A list of qualified leads with the reasoning for each score</li>
                  <li>Matching against your existing CRM, so you only get companies you don&apos;t already have</li>
                  <li>A HubSpot-ready import file, or a CSV for any other CRM</li>
                  <li>An accuracy check against hand-labelled examples, so you know how far to trust it</li>
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
      </div>
    </>
  );
}
