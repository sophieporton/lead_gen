"""Stage 6c: export new leads as a HubSpot-ready company import file.

Writes one row per verified lead that is not already in the CRM (see
stage 6b), with:
- HubSpot's default company properties, using the column names HubSpot's
  importer maps automatically (name, domain, city, postcode and so on),
- custom properties for the enrichment and fit scores. These must be
  created in HubSpot (Settings > Properties > Company properties) before
  importing, with the internal names used as column headers here.

Run on its own with:

    python -m lead_gen.hubspot_export
"""

import csv

from lead_gen import config
from lead_gen.crm_clean import clean_display_name, clean_domain, clean_town
from lead_gen.db import connect

EXPORT_DIR = config.DATA_DIR / "exports"
HUBSPOT_CSV = EXPORT_DIR / "hubspot_companies.csv"

# Default HubSpot company properties, by the labels its importer recognises.
DEFAULT_COLUMNS = [
    "Company name", "Company Domain Name", "Website URL", "City", "Postal Code",
    "Country/Region", "Description", "Lifecycle Stage", "Type",
]

# Custom properties to create in HubSpot first (internal names).
CUSTOM_COLUMNS = [
    "companies_house_number", "sector", "market", "size_signals", "growth_signals",
    *[f"fit_score_{key}" for key in config.CUSTOMER_DESCRIPTIONS],
    "best_fit_description", "best_fit_score", "best_fit_reason", "outreach_opener",
]


def new_leads() -> list[dict]:
    """Verified leads not already in the CRM, with their best-fitting description."""
    with connect() as con:
        rows = con.execute(
            """
            WITH best AS (
                SELECT company_number, description_key, fit_score, fit_reason, outreach_opener,
                       row_number() OVER (PARTITION BY company_number ORDER BY fit_score DESC, description_key) AS rank
                FROM fit_scores
                WHERE prompt_version = ?
            ),
            scores AS (
                SELECT company_number, map(list(description_key), list(fit_score)) AS by_description
                FROM fit_scores WHERE prompt_version = ? GROUP BY 1
            )
            SELECT c.company_number, c.name, w.url, c.post_town, c.postcode,
                   e.what_they_sell, e.sector, e.market, e.size_signals, e.growth_signals,
                   s.by_description, b.description_key, b.fit_score, b.fit_reason, b.outreach_opener
            FROM enrichments e
            JOIN companies c USING (company_number)
            JOIN websites w USING (company_number)
            JOIN lead_crm_matches m USING (company_number)
            JOIN scores s USING (company_number)
            JOIN best b ON b.company_number = c.company_number AND b.rank = 1
            WHERE e.website_matches_company = 'yes' AND m.crm_group_id IS NULL
            ORDER BY b.fit_score DESC, c.name
            """,
            [config.SCORE_PROMPT_VERSION, config.SCORE_PROMPT_VERSION],
        ).fetchall()

    leads = []
    for (number, name, url, town, postcode, sells, sector, market, size, growth,
         by_description, best_key, best_score, best_reason, opener) in rows:
        domain = clean_domain(url)
        leads.append({
            "Company name": clean_display_name(name),
            "Company Domain Name": domain,
            "Website URL": url,
            "City": clean_town(town),
            "Postal Code": postcode,
            "Country/Region": "United Kingdom",
            "Description": sells,
            "Lifecycle Stage": "lead",
            "Type": "PROSPECT",
            "companies_house_number": number,
            "sector": sector,
            "market": market,
            "size_signals": "; ".join(size or []),
            "growth_signals": "; ".join(growth or []),
            **{f"fit_score_{key}": by_description.get(key) for key in config.CUSTOMER_DESCRIPTIONS},
            "best_fit_description": best_key,
            "best_fit_score": best_score,
            "best_fit_reason": best_reason,
            "outreach_opener": opener or "",
        })
    return leads


def main() -> None:
    leads = new_leads()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    # utf-8-sig adds a byte-order mark so Excel and HubSpot read accents correctly.
    with open(HUBSPOT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=DEFAULT_COLUMNS + CUSTOM_COLUMNS)
        writer.writeheader()
        writer.writerows(leads)
    print(f"Wrote {len(leads)} new leads to {HUBSPOT_CSV}")
    print("Create these custom company properties in HubSpot before importing:")
    print("  " + ", ".join(CUSTOM_COLUMNS))


if __name__ == "__main__":
    main()
