"""Export a company-level snapshot of the results for the web dashboard.

The dashboard is a static website: it has no database and makes no LLM or
API calls. Everything it shows comes from one JSON file written here, from
the pipeline's DuckDB database.

Only company-level data goes into the file: Companies House details, what
each company's website says about the business, and the pipeline's scores.

Run on its own with:

    python -m lead_gen.export_dashboard

Re-run it, then rebuild the site, whenever the pipeline results change.
"""

import csv
import json
from datetime import date

from lead_gen import config
from lead_gen.crm_clean import (
    clean_display_name, clean_domain, clean_record, clean_town, group_duplicates, score_against_answer_key,
)
from lead_gen.synthetic_crm import CRM_EXPORT
from lead_gen.db import connect
from lead_gen.evaluate import score_to_band
from lead_gen.find_companies import eligible_candidates, latest_bulk_csv, load_north_east

DASHBOARD_JSON = config.PROJECT_ROOT / "web" / "src" / "data" / "dashboard.json"

# Short labels for the example customer descriptions, and the words a
# visitor might type into the demo's search box to find each one.
DESCRIPTION_META = {
    "it_support": ("Managed IT support",
                   ["it support", "managed it", "it services", "computer", "cyber", "microsoft", "365", "tech support", "it"]),
    "van_leasing": ("Van leasing for trades",
                    ["van", "vans", "vehicle", "vehicles", "fleet", "lease", "leasing"]),
    "card_payments": ("Card payments for local shops",
                      ["card machine", "card", "payment", "payments", "till", "epos", "pos", "terminal"]),
    "packaging": ("Packaging and warehouse supplies",
                  ["packaging", "pallet", "boxes", "warehouse", "shipping", "wrap", "consumables"]),
    "safety_training": ("Health and safety training",
                        ["health and safety", "safety", "first aid", "training", "manual handling"]),
    "commercial_cleaning": ("Commercial cleaning",
                            ["cleaning", "cleaner", "cleaners", "office cleaning", "janitorial"]),
    "web_marketing": ("Websites and local marketing",
                      ["website", "websites", "web design", "seo", "marketing", "social media", "digital"]),
    "bookkeeping": ("Bookkeeping and payroll",
                    ["bookkeeping", "accounting", "accountancy", "accounts", "payroll", "accountant", "tax", "vat"]),
    "workwear": ("Workwear and PPE",
                 ["workwear", "uniform", "uniforms", "ppe", "clothing", "hi vis", "embroidery"]),
    "ev_charging": ("EV charge points",
                    ["ev", "electric vehicle", "charging", "charge point", "charge points", "charger", "chargers"]),
}

def funnel(con) -> dict:
    """Counts at each stage, from all NE companies down to new leads."""
    load_north_east(con, latest_bulk_csv())
    active = con.execute("SELECT count(*) FROM ne_companies").fetchone()[0]
    eligible = len(eligible_candidates(con))
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "active_north_east": active,
        "eligible_small_companies": eligible,
        "sampled": one("SELECT count(*) FROM companies WHERE status = 'active'"),
        "website_found": one("SELECT count(*) FROM websites WHERE match_status IN ('confirmed', 'likely', 'ambiguous')"),
        "website_verified": one("SELECT count(*) FROM enrichments WHERE website_matches_company = 'yes'"),
        "already_in_crm": one("SELECT count(*) FROM lead_crm_matches WHERE crm_group_id IS NOT NULL"),
        "new_leads": one("SELECT count(*) FROM lead_crm_matches WHERE crm_group_id IS NULL"),
        "property_sampled": one("SELECT count(*) FROM companies WHERE status = 'active' AND sic_codes[1] LIKE '68%'"),
        "property_verified": one(
            "SELECT count(*) FROM enrichments e JOIN companies c USING (company_number) "
            "WHERE e.website_matches_company = 'yes' AND c.sic_codes[1] LIKE '68%'"
        ),
    }


def leads(con) -> list[dict]:
    """Every verified lead with its profile and all five fit scores."""
    rows = con.execute(
        """
        SELECT c.company_number, c.name, c.post_town, c.postcode_area, c.sic_codes, w.url,
               e.sector, e.market, e.what_they_sell, e.who_they_sell_to, e.products_services,
               e.size_signals, e.growth_signals, m.crm_group_id IS NOT NULL AS in_crm
        FROM enrichments e
        JOIN companies c USING (company_number)
        JOIN websites w USING (company_number)
        LEFT JOIN lead_crm_matches m USING (company_number)
        WHERE e.website_matches_company = 'yes'
        ORDER BY c.name
        """
    ).fetchall()
    scores: dict[str, dict] = {}
    for number, key, score, reason, opener in con.execute(
        "SELECT company_number, description_key, fit_score, fit_reason, outreach_opener "
        "FROM fit_scores WHERE prompt_version = ?",
        [config.SCORE_PROMPT_VERSION],
    ).fetchall():
        scores.setdefault(number, {})[key] = {
            "score": score, "band": score_to_band(score), "reason": reason, "opener": opener,
        }

    out = []
    for (number, name, town, area, sic, url, sector, market, sells, customers, products,
         size, growth, in_crm) in rows:
        out.append({
            "company_number": number,
            "name": clean_display_name(name),
            "town": clean_town(town),
            "postcode_area": area,
            "website": url,
            "domain": clean_domain(url),
            "sector": sector,
            "market": market,
            "what_they_sell": sells,
            "who_they_sell_to": customers,
            "products_services": products or [],
            "size_signals": size or [],
            "growth_signals": growth or [],
            "is_property": bool(sic) and sic[0].startswith("68"),
            "in_crm": bool(in_crm),
            "scores": scores.get(number, {}),
        })
    return out


def crm(con) -> dict:
    """CRM data quality before and after cleaning."""
    quality = [
        {"measure": m, "before": b, "after": a}
        for m, b, a in con.execute("SELECT measure, before_cleaning, after_cleaning FROM crm_quality").fetchall()
    ]
    # Re-run duplicate grouping and score it against the synthetic answer key.
    with open(CRM_EXPORT, encoding="utf-8") as f:
        records = [clean_record(r) for r in csv.DictReader(f)]
    groups = group_duplicates(records)
    lead_matches = dict(con.execute("SELECT company_number, crm_group_id FROM lead_crm_matches").fetchall())
    score = score_against_answer_key(groups, lead_matches)
    return {
        "quality": quality,
        "duplicate_pairs_total": score["duplicate_pairs"],
        "duplicate_pairs_found": score["duplicates_found"],
        "false_merges": score["false_duplicates"],
        "existing_leads_total": score["existing_leads"],
        "existing_leads_found": score["existing_found"],
        "false_existing": score["false_existing"],
    }


def costs(con) -> dict:
    """LLM cost per 1,000 records for the current prompts, and the project total."""
    def per_thousand(stage: str, version: str) -> float:
        calls, cost = con.execute(
            "SELECT count(*), sum(cost_usd) FROM llm_calls WHERE stage = ? AND prompt_version = ?",
            [stage, version],
        ).fetchone()
        return round(cost / calls * 1000, 2) if calls else 0.0

    total, calls = con.execute("SELECT sum(cost_usd), count(*) FROM llm_calls").fetchone()
    return {
        "model": config.LLM_MODEL,
        "enrich_per_1000_companies": per_thousand("enrich", config.ENRICH_PROMPT_VERSION),
        "score_per_1000_pairs": per_thousand("score", config.SCORE_PROMPT_VERSION),
        "project_total_usd": round(total, 2),
        "project_total_calls": calls,
    }


def main() -> None:
    with connect() as con:
        data = {
            "generated": date.today().isoformat(),
            "descriptions": [
                {"key": k, "label": DESCRIPTION_META[k][0], "keywords": DESCRIPTION_META[k][1], "text": text}
                for k, text in config.CUSTOMER_DESCRIPTIONS.items()
            ],
            "bands": [{"band": band, "min_score": floor} for band, floor in config.FIT_BANDS],
            "funnel": funnel(con),
            "leads": leads(con),
            "crm": crm(con),
            "costs": costs(con),
        }

    DASHBOARD_JSON.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(data['leads'])} leads and summary data to {DASHBOARD_JSON}")


if __name__ == "__main__":
    main()
