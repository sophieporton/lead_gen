"""Shared settings for every pipeline stage.

API keys are read from a local .env file (see .env.example). Everything else
lives here so each stage uses the same paths, limits and filters.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Paths -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "lead_gen.duckdb"
FINDINGS_PATH = PROJECT_ROOT / "docs" / "findings.md"

load_dotenv(PROJECT_ROOT / ".env")

# --- API keys ----------------------------------------------------------------

COMPANIES_HOUSE_API_KEY = os.getenv("COMPANIES_HOUSE_API_KEY", "")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")


def require_key(name: str, value: str) -> str:
    """Return an API key, or stop with a clear message if it is missing."""
    if not value:
        raise SystemExit(f"{name} is not set. Copy .env.example to .env and add it.")
    return value


# --- Stage 1: Companies House ------------------------------------------------

# North East England postcode areas. A postcode area is the letters before the
# first digit, so "NE1 4ST" is in area NE. Note that DL and TS also cover parts
# of North Yorkshire.
POSTCODE_AREAS = ["NE", "SR", "DH", "TS", "DL"]

COMPANIES_HOUSE_API_URL = "https://api.company-information.service.gov.uk"

# 600 requests per 5 minutes is 2 per second. Half a second between calls
# keeps us exactly at the limit, so we leave a little headroom.
COMPANIES_HOUSE_MIN_INTERVAL_SECONDS = 0.6

# Companies House bulk file pattern. The newest matching file in RAW_DIR is used.
BULK_CSV_PATTERN = "BasicCompanyDataAsOneFile-*.csv"

# Accounts categories that mean "small, trading company". Only 1,124 NE
# companies are labelled SMALL; most small firms file total exemption or
# abridged accounts instead (see docs/findings.md). Micro entities are left
# out because many are sole contractors with no website.
ACCOUNTS_CATEGORIES = [
    "TOTAL EXEMPTION FULL",
    "UNAUDITED ABRIDGED",
    "SMALL",
    "TOTAL EXEMPTION SMALL",
]

# Ordinary trading company types. Leaves out guarantee companies (mostly
# charities and clubs), partnerships and unlimited companies.
COMPANY_CATEGORIES = ["Private Limited Company", "Public Limited Company"]

# SIC codes that point to companies which do not trade.
EXCLUDED_SIC_CODES = {
    "99999",  # Dormant company
    "74990",  # Non-trading company
    "64209",  # Activities of other holding companies
}

SAMPLE_SIZE = 200
RANDOM_SEED = 42

# --- Stage 2: website finding ------------------------------------------------

SERPER_URL = "https://google.serper.dev/search"
# Store up to 10 results per search, then visit the top 5 that are not
# directories. Visiting fewer keeps the number of requests to websites low.
SEARCH_RESULTS_TO_KEEP = 10
CANDIDATES_TO_CHECK = 5

# A domain that comes up in the results for this many different companies is
# a directory, not a company's own website. This catches the many directory
# sites that are not on the fixed list below (e.g. doogal.co.uk, tracxn.com).
DIRECTORY_MIN_COMPANIES = 3

# Directory, registry and social sites that list companies but are never the
# company's own website.
BLOCKED_DOMAINS = {
    "find-and-update.company-information.service.gov.uk",
    "company-information.service.gov.uk",
    "gov.uk",
    "opencorporates.com",
    "endole.co.uk",
    "companycheck.co.uk",
    "checkcompany.co.uk",
    "bizdb.co.uk",
    "companieslist.co.uk",
    "company-check.co.uk",
    "companiesintheuk.co.uk",
    "ukcompanylist.co.uk",
    "company-information.co.uk",
    "companydatashop.com",
    "bizstats.co.uk",
    "dnb.com",
    "zoominfo.com",
    "kompass.com",
    "northdata.com",
    "northdata.de",
    "globaldatabase.com",
    "cylex-uk.co.uk",
    "freeindex.co.uk",
    "hotfrog.co.uk",
    "scoot.co.uk",
    "yell.com",
    "thomsonlocal.com",
    "192.com",
    "google.com",
    "bing.com",
    "indeed.com",
    "glassdoor.co.uk",
    "rightmove.co.uk",
    "zoopla.co.uk",
    "ratedpeople.com",
    "mybuilder.com",
    "bark.com",
    "nhs.uk",
    "cqc.org.uk",
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "threads.com",
    "yelp.com",
    "wheree.com",
    "trustpilot.com",
    "checkatrade.com",
    "yelp.co.uk",
    "tripadvisor.co.uk",
    "wikipedia.org",
}

# --- Stage 3: scraping -------------------------------------------------------

USER_AGENT = "LeadGenPortfolioBot/0.1 (+https://github.com/sophieporton/lead_gen)"
REQUEST_TIMEOUT_SECONDS = 15
PER_DOMAIN_DELAY_SECONDS = 3.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGE_TEXT_CHARS = 20_000
