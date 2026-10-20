"""Stage 1: find small, active companies in the North East of England.

Steps:
1. Load the Companies House bulk CSV and keep active companies in the NE,
   SR, DH, TS and DL postcode areas that file small company accounts.
2. Print the accounts-category counts (the evidence for the filter above).
3. Draw a reproducible sample, split across postcode areas in proportion to
   how many companies each area has.
4. Check each sampled company against the live Companies House API and
   replace any that are no longer active.

Run on its own with:

    python -m lead_gen.find_companies

It is safe to re-run: companies already checked against the API are skipped.
"""

import math
import re
import time
from datetime import datetime
from pathlib import Path

import duckdb
import httpx
from tqdm import tqdm

from lead_gen import config
from lead_gen.db import connect

POSTCODE_AREA_REGEX = "^(" + "|".join(config.POSTCODE_AREAS) + ")[0-9]"


# --- Bulk file ---------------------------------------------------------------


def latest_bulk_csv() -> Path:
    """Return the newest Companies House bulk CSV in data/raw/."""
    files = sorted(config.RAW_DIR.glob(config.BULK_CSV_PATTERN))
    if not files:
        raise SystemExit(
            f"No bulk file found in {config.RAW_DIR}. Download it from "
            "https://download.companieshouse.gov.uk/en_output.html and unzip it there."
        )
    return files[-1]


def load_north_east(con: duckdb.DuckDBPyConnection, csv_path: Path) -> None:
    """Load active North East companies from the bulk CSV into a temp table.

    The bulk file has about 5.5 million rows, so we filter while reading and
    only keep the columns we need.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE ne_companies AS
        SELECT
            trim(companynumber)                          AS company_number,
            trim(companyname)                            AS name,
            trim(regaddressposttown)                     AS post_town,
            upper(trim(regaddresspostcode))              AS postcode,
            regexp_extract(upper(trim(regaddresspostcode)), '^[A-Z]+') AS postcode_area,
            companycategory                              AS company_category,
            accountsaccountcategory                      AS accounts_category,
            try_strptime(incorporationdate, '%d/%m/%Y')::DATE AS incorporation_date,
            -- SIC text looks like "62020 - Information technology consultancy".
            list_filter(
                [regexp_extract(siccodesictext_1, '^[0-9]+'),
                 regexp_extract(siccodesictext_2, '^[0-9]+'),
                 regexp_extract(siccodesictext_3, '^[0-9]+'),
                 regexp_extract(siccodesictext_4, '^[0-9]+')],
                code -> code <> ''
            )                                            AS sic_codes
        FROM read_csv(?, header = true, all_varchar = true, normalize_names = true)
        WHERE companystatus = 'Active'
          AND regexp_matches(upper(trim(regaddresspostcode)), '{POSTCODE_AREA_REGEX}')
        """,
        [str(csv_path)],
    )


def print_accounts_counts(con: duckdb.DuckDBPyConnection) -> None:
    """Print how many active NE companies file each type of accounts."""
    total = con.execute("SELECT count(*) FROM ne_companies").fetchone()[0]
    print(f"\nActive companies in {', '.join(config.POSTCODE_AREAS)}: {total:,}\n")
    rows = con.execute(
        """
        SELECT accounts_category, count(*) AS n
        FROM ne_companies GROUP BY 1 ORDER BY n DESC
        """
    ).fetchall()
    for category, n in rows:
        marker = "  <- included" if category in config.ACCOUNTS_CATEGORIES else ""
        print(f"  {category:<30} {n:>8,}{marker}")


def eligible_candidates(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Return every company that passes the filters, in a fixed random order.

    Ordering by a hash of company number and seed gives the same "random"
    order on every run, so the sample is reproducible.
    """
    excluded_sic = list(config.EXCLUDED_SIC_CODES)
    return con.execute(
        """
        SELECT company_number, name, post_town, postcode, postcode_area,
               sic_codes, accounts_category, incorporation_date
        FROM ne_companies
        WHERE accounts_category IN (SELECT unnest(?))
          AND company_category IN (SELECT unnest(?))
          AND len(sic_codes) > 0
          AND NOT list_has_any(sic_codes, ?)
        ORDER BY hash(company_number || ?::VARCHAR)
        """,
        [config.ACCOUNTS_CATEGORIES, config.COMPANY_CATEGORIES, excluded_sic, config.RANDOM_SEED],
    ).fetchall()


def area_quotas(candidates: list[tuple], sample_size: int) -> dict[str, int]:
    """Split the sample across postcode areas in proportion to their size."""
    counts: dict[str, int] = {}
    for row in candidates:
        counts[row[4]] = counts.get(row[4], 0) + 1
    total = sum(counts.values())
    quotas = {area: math.floor(sample_size * n / total) for area, n in counts.items()}
    # Hand out any places lost to rounding to the largest areas first.
    for area in sorted(counts, key=counts.get, reverse=True):
        if sum(quotas.values()) >= sample_size:
            break
        quotas[area] += 1
    return quotas


# --- Companies House API -----------------------------------------------------


class CompaniesHouseClient:
    """Small Companies House API client that stays under the rate limit."""

    def __init__(self, api_key: str) -> None:
        # The API key is the username for HTTP basic auth; the password is blank.
        self.client = httpx.Client(
            base_url=config.COMPANIES_HOUSE_API_URL,
            auth=(api_key, ""),
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        self.last_call = 0.0

    def get_company(self, company_number: str) -> dict | None:
        """Fetch a company profile. Returns None if the company is not found."""
        while True:
            wait = config.COMPANIES_HOUSE_MIN_INTERVAL_SECONDS - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.monotonic()
            response = self.client.get(f"/company/{company_number}")
            if response.status_code == 429:
                print("Rate limited by Companies House, waiting 60 seconds...")
                time.sleep(60)
                continue
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()


def save_company(con: duckdb.DuckDBPyConnection, row: tuple, profile: dict | None) -> str:
    """Store a sampled company with its live status and return that status.

    The bulk file is up to a month old, so the live API status and
    registered office address take priority where they exist.
    """
    company_number, name, post_town, postcode, area, sic_codes, accounts, incorporated = row
    status = "not_found"
    if profile:
        status = profile.get("company_status", "unknown")
        name = profile.get("company_name", name)
        address = profile.get("registered_office_address", {})
        post_town = address.get("locality", post_town)
        postcode = (address.get("postal_code") or postcode).upper()
        area_match = re.match(r"^[A-Z]+", postcode)
        area = area_match.group(0) if area_match else area
        sic_codes = profile.get("sic_codes", sic_codes)

    con.execute(
        "INSERT OR REPLACE INTO companies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [company_number, name, post_town, postcode, area, sic_codes,
         accounts, incorporated, status, datetime.now()],
    )
    return status


def build_sample(con: duckdb.DuckDBPyConnection, candidates: list[tuple]) -> None:
    """Fill the companies table with up to SAMPLE_SIZE active companies.

    Works through each postcode area's candidates in their fixed random
    order, checking each against the API, until the area's quota of active
    companies is met. Companies already checked on an earlier run are skipped.
    """
    api = CompaniesHouseClient(config.require_key("COMPANIES_HOUSE_API_KEY", config.COMPANIES_HOUSE_API_KEY))
    quotas = area_quotas(candidates, config.SAMPLE_SIZE)
    already_checked = {r[0] for r in con.execute("SELECT company_number FROM companies").fetchall()}

    progress = tqdm(total=config.SAMPLE_SIZE, desc="Active companies")
    for area, quota in sorted(quotas.items()):
        active = con.execute(
            "SELECT count(*) FROM companies WHERE status = 'active' AND postcode_area = ?", [area]
        ).fetchone()[0]
        progress.update(min(active, quota))
        for row in (r for r in candidates if r[4] == area):
            if active >= quota:
                break
            if row[0] in already_checked:
                continue
            if save_company(con, row, api.get_company(row[0])) == "active":
                active += 1
                progress.update(1)
    progress.close()


def main() -> None:
    csv_path = latest_bulk_csv()
    print(f"Reading {csv_path.name} (this takes about 10 seconds)...")
    with connect() as con:
        load_north_east(con, csv_path)
        print_accounts_counts(con)

        candidates = eligible_candidates(con)
        print(f"\nEligible after filters: {len(candidates):,}")
        print("Sample quotas by postcode area:", area_quotas(candidates, config.SAMPLE_SIZE))

        build_sample(con, candidates)

        print("\nSample by postcode area and live status:")
        for area, status, n in con.execute(
            "SELECT postcode_area, status, count(*) FROM companies GROUP BY ALL ORDER BY ALL"
        ).fetchall():
            print(f"  {area:<4} {status:<12} {n:>4}")


if __name__ == "__main__":
    main()
