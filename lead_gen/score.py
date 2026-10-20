"""Stage 4b: score each lead against customer descriptions and draft an opener.

For every enriched company whose website the LLM confirmed, and for every
customer description in config.CUSTOMER_DESCRIPTIONS, one Claude Haiku call
returns:
- a fit score from 0 to 100,
- a one-line reason,
- a short, personalised outreach opener.

The call uses the short profile from stage 4a rather than the full page
text, which keeps it cheap. Responses are cached and every paid call is
logged with its cost.

Run on its own with:

    python -m lead_gen.score            # every company and description
    python -m lead_gen.score --limit 3  # try it on a few companies first

It is safe to re-run: pairs already scored with the current prompt version
are skipped.
"""

import argparse
from datetime import datetime

import duckdb
from pydantic import BaseModel, Field
from tqdm import tqdm

from lead_gen import config
from lead_gen.db import connect
from lead_gen.llm_utils import cached_parse, make_client, possible_personal_names, print_cost_summary


class FitScore(BaseModel):
    """How well one lead fits one customer description."""

    fit_score: int = Field(description="0 to 100, using the scale in the instructions.")
    fit_reason: str = Field(description="One sentence explaining the score, citing facts from the profile.")
    outreach_opener: str = Field(
        description="Two sentences, at most 40 words, opening a cold email to this company. "
        "An empty string if fit_score is below 50."
    )


SYSTEM_PROMPT = """You help a B2B sales team decide which small UK companies to contact.

You are given what the sales team sells and who their ideal customer is, followed by a profile of one company built from its website. Score how good a prospect the company is, explain why, and write the opening of a cold email.

Fit score scale:
- 80 to 100: clearly matches the ideal customer, with evidence in the profile.
- 50 to 79: plausibly a customer, but some evidence is missing.
- 20 to 49: a weak or partial match.
- 0 to 19: not a sensible prospect, or the profile is too thin to judge.

Rules:
- Base the score only on facts in the profile. Missing information lowers the score; do not assume.
- The reason is one sentence and should mention the specific facts that drove the score.
- Only write an opener if the fit score is 50 or more. Otherwise leave it as an empty string.
- The opener is two sentences and at most 40 words. The first mentions one specific fact from the profile; the second links it to what the sales team offers. Vary how it starts: do not begin with "I noticed". Plain and direct, no hype, no exclamation marks, no em dashes, and no greeting line.
- Every fact about the company in the reason or the opener must appear in the profile. Do not add praise, awards, reputation or guesses about how busy or successful they are.
- Never name individual people.
- Write in plain British English."""


def build_user_message(description: str, company: dict) -> str:
    """Combine one customer description with one company profile."""
    def listed(items: list[str] | None) -> str:
        return "; ".join(items) if items else "none stated"

    return "\n".join([
        "<what_we_sell>",
        description,
        "</what_we_sell>",
        "<company_profile>",
        f"Name: {company['name']}",
        f"Location: {company['post_town']}",
        f"Sector: {company['sector']}",
        f"What they sell: {company['what_they_sell']}",
        f"Products and services: {listed(company['products_services'])}",
        f"Who they sell to: {company['who_they_sell_to']}",
        f"Market: {company['market']}",
        f"Size signals: {listed(company['size_signals'])}",
        f"Growth signals: {listed(company['growth_signals'])}",
        "</company_profile>",
    ])


def pairs_to_score(con: duckdb.DuckDBPyConnection, limit: int | None) -> list[tuple[str, dict]]:
    """(description key, company) pairs not yet scored with the current prompt."""
    columns = ["company_number", "name", "post_town", "sector", "what_they_sell", "products_services",
               "who_they_sell_to", "market", "size_signals", "growth_signals"]
    rows = con.execute(
        """
        SELECT e.company_number, c.name, c.post_town, e.sector, e.what_they_sell, e.products_services,
               e.who_they_sell_to, e.market, e.size_signals, e.growth_signals
        FROM enrichments e JOIN companies c USING (company_number)
        WHERE e.website_matches_company = 'yes'
        ORDER BY e.company_number
        """
    ).fetchall()
    companies = [dict(zip(columns, row)) for row in rows]
    if limit:
        companies = companies[:limit]

    done = set(con.execute(
        "SELECT company_number, description_key FROM fit_scores WHERE prompt_version = ?",
        [config.SCORE_PROMPT_VERSION],
    ).fetchall())
    return [
        (key, company)
        for key in config.CUSTOMER_DESCRIPTIONS
        for company in companies
        if (company["company_number"], key) not in done
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="only score this many companies")
    args = parser.parse_args()

    client = make_client()
    with connect() as con:
        pairs = pairs_to_score(con, args.limit)
        print(f"{len(pairs)} company and description pairs to score ({config.SCORE_PROMPT_VERSION}).")
        failed = 0
        for key, company in tqdm(pairs, desc="Scoring"):
            result = cached_parse(
                client, con, stage="score", prompt_version=config.SCORE_PROMPT_VERSION,
                company_number=company["company_number"], system=SYSTEM_PROMPT,
                user_message=build_user_message(config.CUSTOMER_DESCRIPTIONS[key], company),
                output_model=FitScore,
            )
            if result is None:
                failed += 1
                continue
            score = max(0, min(100, result.fit_score))  # guard against out-of-range values
            # Openers are only worth having for plausible prospects. Enforce
            # the prompt rule here too, in case the model writes one anyway.
            opener = result.outreach_opener.strip() if score >= 50 else ""
            con.execute(
                "INSERT OR REPLACE INTO fit_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [company["company_number"], key, score, result.fit_reason, opener or None,
                 config.LLM_MODEL, config.SCORE_PROMPT_VERSION, datetime.now()],
            )
            for phrase in possible_personal_names(result.fit_reason, result.outreach_opener):
                tqdm.write(f"Check for a personal name in {company['name']} ({key}): '{phrase}'")
        if failed:
            print(f"\n{failed} pairs failed; see the error column in llm_calls. Re-run to retry.")

        print("\nAverage fit score by customer description:")
        for key, avg, strong in con.execute(
            "SELECT description_key, round(avg(fit_score)), count(*) FILTER (WHERE fit_score >= 80) "
            "FROM fit_scores WHERE prompt_version = ? GROUP BY 1 ORDER BY 1",
            [config.SCORE_PROMPT_VERSION],
        ).fetchall():
            print(f"  {key:<16} average {avg:>3.0f}, {strong} strong fits (80+)")

        print_cost_summary(con, "score", config.SCORE_PROMPT_VERSION)


if __name__ == "__main__":
    main()
