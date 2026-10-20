"""DuckDB storage for the pipeline.

Every stage reads from and writes to one local DuckDB file. The tables are
created here so the schema is defined in one place. Run this module on its
own to create an empty database:

    python -m lead_gen.db
"""

import duckdb

from lead_gen.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    company_number     VARCHAR PRIMARY KEY,
    name               VARCHAR NOT NULL,
    post_town          VARCHAR,
    postcode           VARCHAR,
    postcode_area      VARCHAR,
    sic_codes          VARCHAR[],
    accounts_category  VARCHAR,
    incorporation_date DATE,
    status             VARCHAR,
    api_refreshed_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS website_candidates (
    company_number VARCHAR NOT NULL,
    rank           INTEGER NOT NULL,
    url            VARCHAR NOT NULL,
    domain         VARCHAR,
    title          VARCHAR,
    snippet        VARCHAR,
    match_score    INTEGER,
    match_reasons  VARCHAR[],
    PRIMARY KEY (company_number, rank)
);

CREATE TABLE IF NOT EXISTS websites (
    company_number VARCHAR PRIMARY KEY,
    url            VARCHAR,
    match_status   VARCHAR NOT NULL,  -- confirmed / likely / ambiguous / not_found
    checked_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pages (
    company_number VARCHAR NOT NULL,
    page_type      VARCHAR NOT NULL,  -- home / about
    url            VARCHAR,
    http_status    INTEGER,
    robots_allowed BOOLEAN,
    text           VARCHAR,
    fetched_at     TIMESTAMP,
    error          VARCHAR,
    PRIMARY KEY (company_number, page_type)
);

-- Every LLM response, keyed by a hash of the exact request, so re-running a
-- stage with an unchanged prompt costs nothing.
CREATE TABLE IF NOT EXISTS llm_cache (
    request_hash  VARCHAR PRIMARY KEY,
    response_json VARCHAR NOT NULL,
    created_at    TIMESTAMP
);

-- One row per paid LLM call, for cost tracking.
CREATE TABLE IF NOT EXISTS llm_calls (
    company_number VARCHAR,
    stage          VARCHAR NOT NULL,   -- e.g. enrich
    model          VARCHAR NOT NULL,
    prompt_version VARCHAR NOT NULL,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    cost_usd       DOUBLE,
    stop_reason    VARCHAR,
    error          VARCHAR,
    created_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS enrichments (
    company_number          VARCHAR PRIMARY KEY,
    website_matches_company VARCHAR,   -- yes / no / unsure
    website_match_reason    VARCHAR,
    what_they_sell          VARCHAR,
    products_services       VARCHAR[],
    who_they_sell_to        VARCHAR,
    market                  VARCHAR,   -- B2B / B2C / both / unclear
    sector                  VARCHAR,
    size_signals            VARCHAR[],
    growth_signals          VARCHAR[],
    confidence              VARCHAR,   -- high / medium / low
    model                   VARCHAR,
    prompt_version          VARCHAR,
    enriched_at             TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fit_scores (
    company_number  VARCHAR NOT NULL,
    description_key VARCHAR NOT NULL,  -- key in config.CUSTOMER_DESCRIPTIONS
    fit_score       INTEGER,           -- 0 to 100
    fit_reason      VARCHAR,
    outreach_opener VARCHAR,
    model           VARCHAR,
    prompt_version  VARCHAR,
    scored_at       TIMESTAMP,
    PRIMARY KEY (company_number, description_key)
);
"""


def connect() -> duckdb.DuckDBPyConnection:
    """Open the project database, creating the file and tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(SCHEMA)
    return con


if __name__ == "__main__":
    with connect() as con:
        tables = [row[0] for row in con.execute("SHOW TABLES").fetchall()]
    print(f"Database ready at {DB_PATH}")
    print("Tables:", ", ".join(tables))
