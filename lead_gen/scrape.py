"""Stage 3: scrape each matched company's homepage and about page.

For every company with a confirmed, likely or ambiguous website (ambiguous
ones are scraped so the LLM can check them in stage 4), we:
1. Fetch the homepage politely (robots.txt, rate limit, clear user agent).
2. Look for an about page among the homepage's links to the same site.
3. Fetch the about page, if there is one.
4. Store the visible text of each page in the `pages` table.

Pages that are blocked by robots.txt or fail to load are stored as rows
with an error, so they show up in the findings rather than disappearing.

Run on its own with:

    python -m lead_gen.scrape

It is safe to re-run: companies that already have pages stored are skipped.
"""

import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import duckdb
from bs4 import BeautifulSoup
from tqdm import tqdm

from lead_gen import config
from lead_gen.db import connect
from lead_gen.http_utils import FetchResult, PoliteFetcher

# Link text or URL fragments that usually point to an about page, best first.
ABOUT_HINTS = ["about", "who-we-are", "who we are", "our-story", "our story", "our-company", "company"]

# Tags whose text is code, styling or menus rather than page content.
NON_CONTENT_TAGS = ["script", "style", "noscript", "nav", "svg", "iframe", "template"]


EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# UK phone numbers such as 0191 123 4567, +44 (0)191 1234567 or 07700 900123.
PHONE_PATTERN = re.compile(r"(?:\+44\s?(?:\(0\)\s?)?|\b0)\d(?:[\s-]?\d){8,9}\b")


def redact_contact_details(text: str) -> str:
    """Remove email addresses and phone numbers.

    The project only keeps company-level data. Contact details on a page
    often belong to an individual (an owner's mobile, a named email), and
    no later stage needs them, so they are never stored.
    """
    text = EMAIL_PATTERN.sub("[email removed]", text)
    return PHONE_PATTERN.sub("[phone removed]", text)


def visible_text(html: str) -> str:
    """Return the readable text of a page, one block per line.

    Keeps line breaks between blocks so the text stays readable for the LLM,
    removes contact details, and caps the length so one huge page cannot
    dominate costs later.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NON_CONTENT_TAGS):
        tag.decompose()
    lines = (re.sub(r"\s+", " ", line).strip() for line in soup.get_text("\n").splitlines())
    text = "\n".join(line for line in lines if line)
    return redact_contact_details(text)[: config.MAX_PAGE_TEXT_CHARS]


def same_site(url_a: str, url_b: str) -> bool:
    """True if two URLs are on the same host, ignoring a leading www."""
    def host(url: str) -> str:
        netloc = urlsplit(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc

    return host(url_a) == host(url_b)


def find_about_link(html: str, page_url: str) -> str | None:
    """Find the most likely about page linked from a homepage."""
    soup = BeautifulSoup(html, "html.parser")
    best: tuple[int, str] | None = None
    for link in soup.find_all("a", href=True):
        url = urljoin(page_url, link["href"]).split("#")[0]
        if not url.startswith("http") or not same_site(url, page_url) or url.rstrip("/") == page_url.rstrip("/"):
            continue
        haystack = (link.get_text(" ") + " " + urlsplit(url).path).lower()
        for priority, hint in enumerate(ABOUT_HINTS):
            if hint in haystack:
                if best is None or priority < best[0]:
                    best = (priority, url)
                break
    return best[1] if best else None


def save_page(con: duckdb.DuckDBPyConnection, company_number: str, page_type: str,
              result: FetchResult | None, error: str | None = None) -> None:
    """Store one page, or the reason it could not be fetched."""
    text = visible_text(result.html) if result and result.html else None
    con.execute(
        "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [company_number, page_type,
         result.url if result else None,
         result.status if result else None,
         result.robots_allowed if result else None,
         text, datetime.now(),
         error or (result.error if result else None)],
    )


def scrape_company(con: duckdb.DuckDBPyConnection, fetcher: PoliteFetcher,
                   company_number: str, url: str) -> bool:
    """Scrape one company's homepage and about page.

    Returns False, storing nothing, if the homepage failed because our own
    connection is down, so the company is retried on the next run.
    """
    home = fetcher.fetch(url)
    if home.status is None and home.robots_allowed and not fetcher.is_online():
        return False
    save_page(con, company_number, "home", home)

    if not home.html:
        save_page(con, company_number, "about", None, error="homepage not available")
        return True

    about_url = find_about_link(home.html, home.url)
    if about_url is None:
        save_page(con, company_number, "about", None, error="no about page found")
    else:
        save_page(con, company_number, "about", fetcher.fetch(about_url))
    return True


def main() -> None:
    with connect() as con:
        to_scrape = con.execute(
            """
            SELECT w.company_number, w.url
            FROM websites w
            WHERE w.match_status IN ('confirmed', 'likely', 'ambiguous')
              AND w.company_number NOT IN (SELECT company_number FROM pages)
            ORDER BY w.company_number
            """
        ).fetchall()
        print(f"{len(to_scrape)} companies to scrape.")

        fetcher = PoliteFetcher()
        skipped = sum(
            not scrape_company(con, fetcher, number, url)
            for number, url in tqdm(to_scrape, desc="Scraping")
        )
        if skipped:
            print(f"\n{skipped} companies hit connection errors. Re-run to retry them.")

        print("\nPages by type:")
        for page_type, total, with_text, avg_chars in con.execute(
            """
            SELECT page_type, count(*), count(text), round(avg(length(text)))
            FROM pages GROUP BY 1 ORDER BY 1 DESC
            """
        ).fetchall():
            print(f"  {page_type:<6} {total:>4} stored, {with_text:>4} with text, avg {avg_chars or 0:,.0f} chars")

        print("\nProblems:")
        for error, n in con.execute(
            "SELECT error, count(*) FROM pages WHERE error IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall():
            print(f"  {n:>4}  {error}")


if __name__ == "__main__":
    main()
