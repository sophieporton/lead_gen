import type { Metadata } from "next";
import { BandChip, Card, PageTitle, Section, StatTile } from "@/components/ui";
import { BANDS, data, descriptionLabel, pct } from "@/lib/data";

export const metadata: Metadata = { title: "How accurate is it? | Lead Research Pipeline" };

/** A confusion table: hand labels down the side, LLM answers across the top. */
function Agreement({ pairs, values }: { pairs: Record<string, number>; values: readonly string[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-raised">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-hairline text-ink-3">
            <th className="px-3 py-2 text-left font-medium">Person ↓ · LLM →</th>
            {values.map((v) => (
              <th key={v} className="px-3 py-2 text-right font-medium">{v}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {values.map((human) => (
            <tr key={human} className="border-b border-hairline last:border-0">
              <th className="px-3 py-2 text-left font-medium">{human}</th>
              {values.map((llm) => {
                const n = pairs[`${human}|${llm}`] ?? 0;
                return (
                  <td
                    key={llm}
                    className={`tabular px-3 py-2 text-right ${human === llm && n ? "bg-accent-wash font-semibold" : ""} ${n ? "" : "text-ink-3"}`}
                  >
                    {n || "·"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EvaluationPage() {
  const e = data.evaluation;
  const fitLabel = descriptionLabel(e.description_key);

  return (
    <>
      <PageTitle
        title="How accurate is it?"
        intro={
          <>
            {e.labelled} companies were picked at random and checked by hand from their websites, without seeing
            the LLM&apos;s answers. This page compares the two, including every case where the fit score
            disagreed.
          </>
        }
      />

      <div className="mb-12 grid gap-3 sm:grid-cols-3">
        <StatTile
          value={`${pct(e.website.agree, e.website.total)}%`}
          label="Website belongs to the company"
          note={`${e.website.agree} of ${e.website.total} agree`}
        />
        <StatTile
          value={`${pct(e.market.agree, e.market.total)}%`}
          label="B2B, B2C or both"
          note={`${e.market.agree} of ${e.market.total} agree`}
        />
        <StatTile
          value={`${pct(e.fit.within_one, e.fit.total)}%`}
          label={`Fit within one band (${fitLabel.toLowerCase()})`}
          note={`${pct(e.fit.exact, e.fit.total)}% in exactly the same band`}
        />
      </div>

      <Section
        title="Does the website belong to the company?"
        intro="In every disagreement the LLM said unsure where the person said yes, so it never wrongly accepted or rejected a site. In one case it had a point: the website showed a company number one digit different from the registered one."
      >
        <div className="max-w-xl">
          <Agreement pairs={e.website.pairs} values={["yes", "no", "unsure"]} />
        </div>
      </Section>

      <Section
        title="B2B, B2C or both?"
        intro="Most disagreements involve 'both', for example a scaffolder that works on homes as well as commercial sites. Where that line falls is a judgement call, and a clearer definition would help both the person and the prompt."
      >
        <div className="max-w-xl">
          <Agreement pairs={e.market.pairs} values={["B2B", "B2C", "both", "unclear"]} />
        </div>
      </Section>

      <Section
        title={`Fit score: ${fitLabel.toLowerCase()}`}
        intro="The first version of the scoring prompt agreed badly with the person. Fixing one rule made a large difference."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Card>
            <div className="text-sm font-medium text-ink-3">First prompt</div>
            <div className="mt-1 text-2xl font-semibold">
              {pct(e.fit.before_fix.within_one, e.fit.before_fix.total)}% within one band
            </div>
            <p className="mt-2 text-sm leading-relaxed text-ink-2">
              The prompt said missing information should lower the score. Small company websites almost never
              say how many staff they have, so clearly physical businesses, like a forklift company and a
              bodyshop, were marked down.
            </p>
          </Card>
          <Card>
            <div className="text-sm font-medium text-ink-3">After the fix</div>
            <div className="mt-1 text-2xl font-semibold">{pct(e.fit.within_one, e.fit.total)}% within one band</div>
            <p className="mt-2 text-sm leading-relaxed text-ink-2">
              Now a missing headcount only counts against a company when its kind of work doesn&apos;t imply
              staff. This was tuned on the same {e.fit.total} labels it is measured against, so the true figure
              is probably a little lower.
            </p>
          </Card>
        </div>
        <div className="mt-4 max-w-2xl">
          <Agreement pairs={e.fit.pairs} values={BANDS} />
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-2">
          The largest remaining gap is about the brief rather than the model. The person treated any employer
          as a possible customer for health and safety training, which is true in law. The LLM took &ldquo;best
          fit: site-based or physical work&rdquo; literally, so office businesses scored low. A sharper customer
          description would close most of this.
        </p>
      </Section>

      <Section title="Every fit disagreement" intro="What the person said, what the LLM said, and the LLM's own reason.">
        <ul className="space-y-3">
          {e.fit_disagreements.map((d) => (
            <li key={d.name}>
              <Card>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <span className="font-semibold">{d.name}</span>
                  <span className="text-sm text-ink-3">Person</span>
                  <BandChip band={d.human} />
                  <span className="text-sm text-ink-3">LLM</span>
                  <BandChip band={d.llm} score={d.llm_score} />
                </div>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{d.llm_reason}</p>
              </Card>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
