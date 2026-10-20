"""Stage 2: find each company's own website.

Companies House does not record websites, so for each company we:
1. Search for its name and town with the Serper.dev API.
2. Drop directory, registry and social media results.
3. Score each remaining result with simple, explainable checks. The
   strongest is the company number: UK companies must show it on their
   website, and a namesake company never has the same number.
4. Record the best match and how sure we are:
   - confirmed: company number found on the site
   - likely:    name in the domain, plus the postcode or full name on the site
   - ambiguous: some evidence, but not enough (checked by an LLM in stage 4)
   - not_found: no plausible website

Run on its own with:

    python -m lead_gen.find_websites

It is safe to re-run: searches are cached in the database and companies
that already have a result are skipped.
"""

import re
import time
from datetime import datetime
from urllib.parse import urlsplit

import duckdb
import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

from lead_gen import config
from lead_gen.db import connect
from lead_gen.http_utils import PoliteFetcher, site_root

# Words that appear in many company names and say nothing about which
# company it is.
NAME_STOPWORDS = {
    "LIMITED", "LTD", "PLC", "THE", "AND", "OF", "UK", "NE", "GROUP",
    "COMPANY", "CO", "SERVICES", "SOLUTIONS", "HOLDINGS", "INTERNATIONAL",
}

# Points for each piece of evidence. Kept simple so the reasons are easy to read.
SCORES = {
    "company_number_on_site": 5,
    "name_in_domain": 2,
    "postcode_on_site": 2,
    "name_on_site": 1,
    "name_in_title": 1,
}


# --- Name helpers ------------------------------------------------------------


def clean_name(name: str) -> str:
    """Strip legal suffixes and punctuation for searching.

    "J&J ELECTRICAL (NE) LTD" -> "J&J ELECTRICAL"
    """
    name = re.sub(r"\(.*?\)", " ", name.upper())
    name = re.sub(r"\b(LIMITED|LTD|PLC|L\.T\.D\.?)\b\.?", " ", name)
    name = re.sub(r"[^A-Z0-9&' -]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def name_tokens(name: str) -> list[str]:
    """Return the distinctive words in a company name, in upper case."""
    words = re.findall(r"[A-Z0-9]+", clean_name(name))
    return [w for w in words if w not in NAME_STOPWORDS and len(w) >= 2]


def domain_of(url: str) -> str:
    """Return the host of a URL without a leading www."""
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_blocked(domain: str) -> bool:
    """True if the domain is a directory or social site (or a subdomain of one)."""
    return any(domain == d or domain.endswith("." + d) for d in config.BLOCKED_DOMAINS)


# --- Search ------------------------------------------------------------------


def search(client: httpx.Client, name: str, town: str | None) -> list[dict]:
    """Search for a company with Serper and return the organic results."""
    query = f'"{clean_name(name)}" {town or ""}'.strip()
    # Retry a few times, as the connection to Serper occasionally times out.
    for attempt in range(1, 4):
        try:
            response = client.post(
                config.SERPER_URL,
                json={"q": query, "gl": "uk", "num": 10},
                headers={"X-API-KEY": config.require_key("SERPER_API_KEY", config.SERPER_API_KEY)},
            )
            response.raise_for_status()
            return response.json().get("organic", [])
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if attempt == 3 or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500):
                raise
            time.sleep(5 * attempt)
    return []


def store_candidates(con: duckdb.DuckDBPyConnection, company_number: str, results: list[dict]) -> None:
    """Keep the top results, one per site, skipping directories and social media."""
    seen: set[str] = set()
    rank = 0
    for result in results:
        domain = domain_of(result.get("link", ""))
        if not domain or is_blocked(domain) or domain in seen:
            continue
        seen.add(domain)
        rank += 1
        con.execute(
            "INSERT OR REPLACE INTO website_candidates VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
            [company_number, rank, result["link"], domain, result.get("title"), result.get("snippet")],
        )
        if rank >= config.SEARCH_RESULTS_TO_KEEP:
            break


# --- Scoring -----------------------------------------------------------------


def page_text(html: str) -> str:
    """Visible text of a page, upper-cased, for simple matching."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ").upper()


def score_candidate(company: dict, domain: str, title: str | None, html: str | None) -> list[str]:
    """Return the list of evidence that this site belongs to the company."""
    reasons: list[str] = []
    tokens = name_tokens(company["name"])
    domain_letters = re.sub(r"[^a-z0-9]", "", domain.split(".")[0]).upper()

    # Most of the distinctive name words appear in the domain, e.g.
    # "JMP BLADE TECH" -> jmpbladetech.co.uk
    if tokens and sum(t in domain_letters for t in tokens) / len(tokens) >= 0.5:
        reasons.append("name_in_domain")
    if tokens and title and sum(t in title.upper() for t in tokens) / len(tokens) >= 0.5:
        reasons.append("name_in_title")

    if html:
        text = page_text(html)
        # Company numbers are sometimes shown without leading zeros.
        number = company["company_number"].lstrip("0")
        if re.search(rf"\b0*{re.escape(number)}\b", text):
            reasons.append("company_number_on_site")
        if company["postcode"] and company["postcode"].replace(" ", "") in text.replace(" ", ""):
            reasons.append("postcode_on_site")
        if clean_name(company["name"]) in re.sub(r"\s+", " ", text):
            reasons.append("name_on_site")
    return reasons


def match_status(reasons: list[str]) -> str:
    """Turn a candidate's evidence into a confidence label."""
    if "company_number_on_site" in reasons:
        return "confirmed"
    if "name_in_domain" in reasons and ({"postcode_on_site", "name_on_site"} & set(reasons)):
        return "likely"
    if sum(SCORES.get(r, 0) for r in reasons) >= 2:
        return "ambiguous"
    return "not_found"


STATUS_ORDER = ["confirmed", "likely", "ambiguous", "not_found"]


def check_company(con: duckdb.DuckDBPyConnection, fetcher: PoliteFetcher, company: dict) -> str | None:
    """Score every stored candidate for one company and record the best one.

    Returns the match status, or None if every candidate site failed to load
    (most likely our own connection). Nothing is recorded in that case, so
    the company is retried on the next run instead of being marked not_found.
    """
    candidates = con.execute(
        "SELECT rank, url, domain, title FROM website_candidates WHERE company_number = ? ORDER BY rank",
        [company["company_number"]],
    ).fetchall()

    best_url, best_status, best_score = None, "not_found", -1
    failures = 0
    for rank, url, domain, title in candidates:
        # Check the homepage, where the company number usually sits in the footer.
        homepage = site_root(url) + "/"
        result = fetcher.fetch(homepage)
        reasons = score_candidate(company, domain, title, result.html)
        if not result.robots_allowed:
            reasons.append("robots_disallowed")
        elif result.error:
            reasons.append("fetch_failed")
            failures += result.status is None  # no response at all, not e.g. a 404
        score = sum(SCORES.get(r, 0) for r in reasons)
        con.execute(
            "UPDATE website_candidates SET match_score = ?, match_reasons = ? "
            "WHERE company_number = ? AND rank = ?",
            [score, reasons, company["company_number"], rank],
        )

        status = match_status(reasons)
        if (STATUS_ORDER.index(status), -score) < (STATUS_ORDER.index(best_status), -best_score):
            best_url = result.url if result.html else homepage
            best_status, best_score = status, score
        if best_status == "confirmed":
            break  # no need to visit the remaining sites

    if candidates and failures == len(candidates):
        return None

    con.execute(
        "INSERT OR REPLACE INTO websites VALUES (?, ?, ?, ?)",
        [company["company_number"], best_url if best_status != "not_found" else None,
         best_status, datetime.now()],
    )
    return best_status


def main() -> None:
    with connect() as con:
        companies = [
            dict(zip(["company_number", "name", "post_town", "postcode"], row))
            for row in con.execute(
                """
                SELECT c.company_number, c.name, c.post_town, c.postcode
                FROM companies c
                LEFT JOIN websites w USING (company_number)
                WHERE c.status = 'active' AND w.company_number IS NULL
                ORDER BY c.company_number
                """
            ).fetchall()
        ]
        print(f"{len(companies)} companies still need a website check.")

        searched = {r[0] for r in con.execute("SELECT DISTINCT company_number FROM website_candidates").fetchall()}
        fetcher = PoliteFetcher()
        with httpx.Client(timeout=config.REQUEST_TIMEOUT_SECONDS) as serper:
            skipped = 0
            for company in tqdm(companies, desc="Finding websites"):
                if company["company_number"] not in searched:
                    try:
                        results = search(serper, company["name"], company["post_town"])
                    except httpx.TransportError:
                        skipped += 1  # connection problem: retry on the next run
                        continue
                    store_candidates(con, company["company_number"], results)
                if check_company(con, fetcher, company) is None:
                    skipped += 1
        if skipped:
            print(f"\n{skipped} companies hit connection errors. Re-run to retry them.")

        print("\nMatch status:")
        for status, n in con.execute(
            "SELECT match_status, count(*) FROM websites GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall():
            print(f"  {status:<10} {n:>4}")


if __name__ == "__main__":
    main()
