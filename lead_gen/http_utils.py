"""Polite web fetching shared by the website-finding and scraping stages.

Every request:
- identifies itself with a clear user agent,
- checks the site's robots.txt first (cached per site),
- waits at least PER_DOMAIN_DELAY_SECONDS between requests to the same site,
  or longer if robots.txt sets a Crawl-delay,
- gives up on slow responses, non-HTML content and very large pages.

Failures are returned as data rather than raised, so one broken website
never stops a pipeline run.
"""

import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from lead_gen import config


@dataclass
class FetchResult:
    """The outcome of fetching one page."""

    url: str                     # final URL after redirects
    status: int | None = None    # HTTP status code, if we got a response
    html: str | None = None      # page HTML, if fetched successfully
    robots_allowed: bool = True
    error: str | None = None     # short description of what went wrong


def site_root(url: str) -> str:
    """Return the scheme and host of a URL, e.g. https://example.co.uk"""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class PoliteFetcher:
    """Fetches web pages while respecting robots.txt and rate limits."""

    def __init__(self) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        self.robots: dict[str, RobotFileParser | None] = {}
        self.last_request: dict[str, float] = {}

    def _wait_for_site(self, host: str, delay: float) -> None:
        """Sleep until it is polite to make another request to this host."""
        elapsed = time.monotonic() - self.last_request.get(host, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request[host] = time.monotonic()

    def _robots_for(self, root: str) -> RobotFileParser | None:
        """Download and cache robots.txt for a site.

        Returns None if the site has no robots.txt (everything allowed).
        Following the robots.txt standard (RFC 9309), a server error on
        robots.txt means we treat the whole site as off limits.
        """
        if root in self.robots:
            return self.robots[root]

        parser: RobotFileParser | None = RobotFileParser()
        host = urlsplit(root).netloc
        self._wait_for_site(host, config.PER_DOMAIN_DELAY_SECONDS)
        try:
            response = self.client.get(f"{root}/robots.txt")
            if response.status_code >= 500:
                parser.disallow_all = True
            elif response.status_code >= 400:
                parser = None
            else:
                parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            # Site unreachable: the page fetch will fail and record the error.
            parser = None
        self.robots[root] = parser
        return parser

    def fetch(self, url: str) -> FetchResult:
        """Fetch one HTML page politely. Never raises for network problems."""
        root = site_root(url)
        robots = self._robots_for(root)
        if robots and not robots.can_fetch(config.USER_AGENT, url):
            return FetchResult(url=url, robots_allowed=False, error="blocked by robots.txt")

        crawl_delay = (robots.crawl_delay(config.USER_AGENT) if robots else None) or 0
        self._wait_for_site(urlsplit(url).netloc, max(config.PER_DOMAIN_DELAY_SECONDS, float(crawl_delay)))

        try:
            with self.client.stream("GET", url) as response:
                result = FetchResult(url=str(response.url), status=response.status_code)
                if response.status_code >= 400:
                    result.error = f"HTTP {response.status_code}"
                    return result
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type:
                    result.error = f"not HTML ({content_type or 'no content type'})"
                    return result

                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > config.MAX_RESPONSE_BYTES:
                        result.error = "page too large"
                        return result
                result.html = body.decode(response.encoding or "utf-8", errors="replace")
                return result
        except httpx.HTTPError as exc:
            return FetchResult(url=url, error=f"{type(exc).__name__}: {exc}"[:200])
