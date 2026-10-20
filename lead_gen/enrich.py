"""Stage 4a: enrich each scraped company with an LLM.

For every company with scraped page text, one Claude Haiku call reads the
homepage and about page and returns a structured profile, validated with
Pydantic:
- whether the website really belongs to this company (this settles the
  "ambiguous" matches from stage 2),
- what they sell, who they sell to, and whether that is B2B or B2C,
- size and growth signals stated on the site.

Every response is cached by a hash of the exact request, and every paid call
is logged with its tokens and cost in the `llm_calls` table.

Run on its own with:

    python -m lead_gen.enrich            # all scraped companies
    python -m lead_gen.enrich --limit 5  # try it on a few first

It is safe to re-run: companies already enriched with the current prompt
version are skipped, and cached responses cost nothing.
"""

import argparse
from datetime import datetime
from typing import Literal

import duckdb
from pydantic import BaseModel, Field
from tqdm import tqdm

from lead_gen import config
from lead_gen.db import connect
from lead_gen.llm_utils import cached_parse, make_client, possible_personal_names, print_cost_summary


class CompanyProfile(BaseModel):
    """What the LLM extracts from a company's website."""

    website_matches_company: Literal["yes", "no", "unsure"] = Field(
        description="Whether this website belongs to the named company, rather than a namesake, "
        "a directory or another business."
    )
    website_match_reason: str = Field(description="One sentence explaining the match decision.")
    what_they_sell: str = Field(description="One plain sentence describing what the company sells or does.")
    products_services: list[str] = Field(description="Up to 5 main products or services, a few words each.")
    who_they_sell_to: str = Field(description="One sentence on their customers, e.g. 'homeowners in County Durham'.")
    market: Literal["B2B", "B2C", "both", "unclear"]
    sector: str = Field(description="A short sector label, e.g. 'electrical contractor' or 'IT support'.")
    size_signals: list[str] = Field(
        description="Countable facts about company size stated on the site: staff numbers, branches, "
        "sites, years trading, turnover or customer numbers, e.g. 'team of 25', '3 branches', "
        "'established 1891'. Not vague phrases like 'family business'. Empty if none."
    )
    growth_signals: list[str] = Field(
        description="Signs of growth stated on the site, e.g. 'hiring engineers', 'opened a second site'. "
        "Empty if none."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="How much useful information the pages gave."
    )


SYSTEM_PROMPT = """You research small UK companies for a B2B sales team.

You are given a company's official Companies House details and the text of a website that a web search linked to it. Read the website text and fill in the company profile.

Rules:
- Use only what the website text says. If something is not stated, say so or leave the list empty. Do not guess.
- First decide whether the website belongs to this company. Good evidence: the company name, company number, registered address or town on the site, or a trading name clearly tied to them. Signs it does not: a directory or listings site, a different business with a similar name, or a business in a different part of the country. If the website is not theirs, still fill the other fields from what can be learned, and set confidence to low.
- The registered address is often an accountant's office, so a different address on the site is not on its own evidence against a match.
- Describe the company only. Never write the name of an individual person anywhere in your answer, including in the match reason: refer to people by role instead, e.g. "the owner", "a director", "the author". Never include email addresses or phone numbers.
- Write in plain British English."""


def build_user_message(company: dict, home_text: str | None, about_text: str | None) -> str:
    """Put the company's details and page text into one message."""
    def page(label: str, text: str | None) -> str:
        if not text:
            return f"<{label}>Not available.</{label}>"
        return f"<{label}>\n{text[: config.LLM_PAGE_CHARS]}\n</{label}>"

    return "\n".join([
        "<company>",
        f"Registered name: {company['name']}",
        f"Company number: {company['company_number']}",
        f"Registered office: {company['post_town']}, {company['postcode']}",
        f"SIC codes: {', '.join(company['sic_codes'] or [])}",
        f"Website: {company['url']}",
        "</company>",
        page("homepage", home_text),
        page("about_page", about_text),
    ])


def save_profile(con: duckdb.DuckDBPyConnection, company_number: str, p: CompanyProfile) -> None:
    """Store one company's profile."""
    con.execute(
        "INSERT OR REPLACE INTO enrichments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [company_number, p.website_matches_company, p.website_match_reason, p.what_they_sell,
         p.products_services, p.who_they_sell_to, p.market, p.sector, p.size_signals,
         p.growth_signals, p.confidence, config.LLM_MODEL, config.ENRICH_PROMPT_VERSION, datetime.now()],
    )


def companies_to_enrich(con: duckdb.DuckDBPyConnection, limit: int | None) -> list[dict]:
    """Scraped companies not yet enriched with the current prompt version."""
    rows = con.execute(
        """
        SELECT c.company_number, c.name, c.post_town, c.postcode, c.sic_codes, w.url,
               max(p.text) FILTER (WHERE p.page_type = 'home')  AS home_text,
               max(p.text) FILTER (WHERE p.page_type = 'about') AS about_text
        FROM companies c
        JOIN websites w USING (company_number)
        JOIN pages p USING (company_number)
        LEFT JOIN enrichments e
               ON e.company_number = c.company_number AND e.prompt_version = ?
        WHERE e.company_number IS NULL
        GROUP BY ALL
        HAVING home_text IS NOT NULL OR about_text IS NOT NULL
        ORDER BY c.company_number
        """,
        [config.ENRICH_PROMPT_VERSION],
    ).fetchall()
    columns = ["company_number", "name", "post_town", "postcode", "sic_codes", "url", "home_text", "about_text"]
    companies = [dict(zip(columns, row)) for row in rows]
    return companies[:limit] if limit else companies


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="only enrich this many companies")
    args = parser.parse_args()

    client = make_client()

    with connect() as con:
        companies = companies_to_enrich(con, args.limit)
        print(f"{len(companies)} companies to enrich with {config.LLM_MODEL} ({config.ENRICH_PROMPT_VERSION}).")
        failed = 0
        for company in tqdm(companies, desc="Enriching"):
            message = build_user_message(company, company["home_text"], company["about_text"])
            profile = cached_parse(
                client, con, stage="enrich", prompt_version=config.ENRICH_PROMPT_VERSION,
                company_number=company["company_number"], system=SYSTEM_PROMPT,
                user_message=message, output_model=CompanyProfile,
            )
            if profile:
                save_profile(con, company["company_number"], profile)
                for phrase in possible_personal_names(
                    profile.website_match_reason, profile.what_they_sell, profile.who_they_sell_to,
                    *profile.products_services, *profile.size_signals, *profile.growth_signals,
                ):
                    tqdm.write(f"Check for a personal name in {company['name']}: '{phrase}'")
            else:
                failed += 1
        if failed:
            print(f"\n{failed} companies failed; see the error column in llm_calls. Re-run to retry.")

        print_cost_summary(con, "enrich", config.ENRICH_PROMPT_VERSION)


if __name__ == "__main__":
    main()
