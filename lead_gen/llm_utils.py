"""Shared LLM helper: one cached, cost-tracked, schema-validated Claude call.

Every LLM stage goes through `cached_parse`, which:
- returns a cached answer if this exact request was made before (free),
- otherwise calls Claude and validates the answer against a Pydantic model,
- logs every paid call's tokens and cost in the `llm_calls` table.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import TypeVar

import anthropic
import duckdb
from pydantic import BaseModel

from lead_gen import config

Model = TypeVar("Model", bound=BaseModel)


def make_client() -> anthropic.Anthropic:
    """Create an Anthropic client from the key in .env."""
    return anthropic.Anthropic(api_key=config.require_key("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY))


def request_hash(*parts: str) -> str:
    """A stable key for one exact request, used for caching."""
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Price one call at the configured per-million-token rates."""
    return (input_tokens * config.LLM_INPUT_PRICE_PER_MTOK
            + output_tokens * config.LLM_OUTPUT_PRICE_PER_MTOK) / 1_000_000


def cached_parse(
    client: anthropic.Anthropic,
    con: duckdb.DuckDBPyConnection,
    *,
    stage: str,
    prompt_version: str,
    company_number: str,
    system: str,
    user_message: str,
    output_model: type[Model],
) -> Model | None:
    """Get a validated answer from the cache or from Claude.

    Returns None if the call failed; the reason is logged in `llm_calls`.
    """
    key = request_hash(config.LLM_MODEL, prompt_version, output_model.__name__, system, user_message)
    cached = con.execute("SELECT response_json FROM llm_cache WHERE request_hash = ?", [key]).fetchone()
    if cached:
        return output_model.model_validate_json(cached[0])

    result: Model | None = None
    response = None
    error = None
    try:
        response = client.messages.parse(
            model=config.LLM_MODEL,
            max_tokens=config.LLM_MAX_TOKENS,
            output_config={"effort": config.LLM_EFFORT},
            system=system,
            messages=[{"role": "user", "content": user_message}],
            output_format=output_model,
        )
        if response.stop_reason != "end_turn":
            error = f"stopped early: {response.stop_reason}"
        elif response.parsed_output is None:
            error = "no structured output returned"
        else:
            result = response.parsed_output
    except anthropic.APIConnectionError as exc:
        error = f"connection error: {exc}"
    except anthropic.APIStatusError as exc:
        error = f"API error {exc.status_code}: {exc.message}"[:300]
    except ValueError as exc:  # the answer did not match the schema
        error = f"invalid output: {exc}"[:300]

    usage = response.usage if response else None
    con.execute(
        "INSERT INTO llm_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [company_number, stage, config.LLM_MODEL, prompt_version,
         usage.input_tokens if usage else None,
         usage.output_tokens if usage else None,
         cost_usd(usage.input_tokens, usage.output_tokens) if usage else None,
         response.stop_reason if response else None,
         error, datetime.now()],
    )
    if result is not None:
        con.execute("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?)", [key, result.model_dump_json(), datetime.now()])
    return result


# Phrases like "run by Jane Smith" or "director John Doe". A simple safety net
# on top of the prompt rules against naming individuals: it catches the
# common patterns, not every name.
POSSIBLE_NAME = re.compile(
    r"\b(?:by|owner|director|founder|manager|Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+"
)


def possible_personal_names(*texts: str) -> list[str]:
    """Return any phrases in LLM output that look like a named individual."""
    return POSSIBLE_NAME.findall(" ".join(texts))


def print_cost_summary(con: duckdb.DuckDBPyConnection, stage: str, prompt_version: str) -> None:
    """Print the total tokens and cost of a stage's paid calls."""
    calls, tokens_in, tokens_out, cost = con.execute(
        "SELECT count(*), sum(input_tokens), sum(output_tokens), sum(cost_usd) "
        "FROM llm_calls WHERE stage = ? AND prompt_version = ?",
        [stage, prompt_version],
    ).fetchone()
    if calls:
        print(f"\nPaid calls so far ({prompt_version}): {calls}, "
              f"{tokens_in or 0:,} input + {tokens_out or 0:,} output tokens, ${cost or 0:.4f} "
              f"(${(cost or 0) / calls * 1000:.2f} per 1,000 calls)")
