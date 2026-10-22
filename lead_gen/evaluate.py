"""Stage 5: evaluate the LLM against hand labels.

Step 1 creates a spreadsheet of companies to label by hand:

    python -m lead_gen.evaluate sheet

The sheet shows only each company's name, town and website. It does not
show the LLM's answers, so the labels are not influenced by them. Fill in
the yellow columns using the dropdowns, then save the file.

Step 2 compares the labels with the LLM's answers and reports accuracy,
including every case where they disagree:

    python -m lead_gen.evaluate report

The report is printed and saved to eval/results.md.
"""

import argparse
from collections import Counter

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from lead_gen import config
from lead_gen.db import connect

# Columns the labeller fills in, with the allowed values for each dropdown
# (None means free text).
LABEL_COLUMNS: list[tuple[str, list[str] | None, str]] = [
    ("website_is_theirs", ["yes", "no", "unsure"], "Does this website belong to this company?"),
    ("market", ["B2B", "B2C", "both", "unclear"], "Who do they mainly sell to?"),
    *[
        (f"fit_{key}", [band for band, _ in config.FIT_BANDS], f"Fit for the '{key}' description")
        for key in config.EVAL_DESCRIPTIONS
    ],
    ("notes", None, "Anything odd or worth mentioning"),
]

YELLOW = PatternFill("solid", fgColor="FFF2CC")
BOLD = Font(bold=True)


def sample_companies() -> list[tuple]:
    """A fixed random sample of enriched companies to label."""
    with connect() as con:
        return con.execute(
            """
            SELECT c.company_number, c.name, c.post_town, w.url
            FROM enrichments e
            JOIN companies c USING (company_number)
            JOIN websites w USING (company_number)
            ORDER BY hash(c.company_number || ?::VARCHAR)
            LIMIT ?
            """,
            [config.RANDOM_SEED, config.EVAL_SAMPLE_SIZE],
        ).fetchall()


def write_instructions(wb: Workbook) -> None:
    """Add a sheet explaining how to label."""
    ws = wb.create_sheet("How to label")
    lines = [
        ("How to label", BOLD),
        ("For each company on the 'Labels' sheet, open the website and fill in the yellow columns.", None),
        ("Judge from the website itself (homepage and about page), the same pages the LLM read.", None),
        ("Use the dropdowns. If you can't tell, choose 'unsure' or 'unclear' rather than guessing.", None),
        ("Aim for 2 minutes per company, so about an hour in total. You can split it across sessions.", None),
        ("", None),
        ("website_is_theirs", BOLD),
        ("yes: clearly this company (name, number, address or trading name). no: a directory, a namesake "
         "or another business. unsure: can't tell.", None),
        ("", None),
        ("Fit bands", BOLD),
        ("strong: clearly matches the ideal customer, with evidence on the site.", None),
        ("possible: plausibly a customer, but some evidence is missing.", None),
        ("weak: a weak or partial match.", None),
        ("not a fit: not a sensible prospect, or too little information to judge.", None),
        ("If the website is not theirs, judge fit from what you can tell about the company, or choose 'not a fit'.", None),
        ("", None),
    ]
    for key in config.EVAL_DESCRIPTIONS:
        lines += [(f"fit_{key}", BOLD), (config.CUSTOMER_DESCRIPTIONS[key], None), ("", None)]
    for row, (text, font) in enumerate(lines, start=1):
        cell = ws.cell(row=row, column=1, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if font:
            cell.font = font
    ws.column_dimensions["A"].width = 110


def sheet_has_labels() -> bool:
    """True if the existing labelling sheet has any label filled in."""
    ws = load_workbook(config.LABELLING_SHEET)["Labels"]
    return any(
        value not in (None, "")
        for row in ws.iter_rows(min_row=3, min_col=5, values_only=True)
        for value in row
    )


def make_sheet() -> None:
    """Create the labelling spreadsheet, refusing to overwrite existing labels.

    A blank sheet (no labels filled in yet) may be replaced, e.g. after
    changing the sample size or columns.
    """
    if config.LABELLING_SHEET.exists() and sheet_has_labels():
        raise SystemExit(
            f"{config.LABELLING_SHEET} already has labels in it. Move or rename it first if you "
            "really want a new blank sheet, so no labels are lost."
        )
    companies = sample_companies()

    wb = Workbook()
    ws = wb.active
    ws.title = "Labels"
    headers = ["company_number", "name", "town", "website"] + [name for name, _, _ in LABEL_COLUMNS]
    ws.append(headers)
    ws.append(["", "", "", ""] + [hint for _, _, hint in LABEL_COLUMNS])
    for number, name, town, url in companies:
        ws.append([number, name, town, url])
        ws.cell(row=ws.max_row, column=4).hyperlink = url
        ws.cell(row=ws.max_row, column=4).style = "Hyperlink"

    first, last = 3, ws.max_row
    for col, (name, options, _) in enumerate(LABEL_COLUMNS, start=5):
        letter = ws.cell(row=1, column=col).column_letter
        for row in range(first, last + 1):
            ws.cell(row=row, column=col).fill = YELLOW
        if options:
            dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
            dv.add(f"{letter}{first}:{letter}{last}")
            ws.add_data_validation(dv)
        ws.column_dimensions[letter].width = 34 if name == "notes" else 22

    for cell in ws[1]:
        cell.font = BOLD
    for cell in ws[2]:
        cell.font = Font(italic=True, color="808080")
        cell.alignment = Alignment(wrap_text=True)
    for letter, width in zip("ABCD", [12, 40, 20, 40]):
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "C3"

    write_instructions(wb)
    config.EVAL_DIR.mkdir(exist_ok=True)
    wb.save(config.LABELLING_SHEET)
    print(f"Wrote {len(companies)} companies to {config.LABELLING_SHEET}")


# --- Step 2: the report -------------------------------------------------------

RESULTS_MD = config.EVAL_DIR / "results.md"
BAND_ORDER = [band for band, _ in config.FIT_BANDS]  # strong, possible, weak, not a fit


def score_to_band(score: int | None) -> str | None:
    """Turn a 0 to 100 fit score into its band name."""
    if score is None:
        return None
    return next(band for band, floor in config.FIT_BANDS if score >= floor)


def read_labels() -> list[dict]:
    """Labelled rows from the sheet. Rows with no labels at all are skipped."""
    ws = load_workbook(config.LABELLING_SHEET)["Labels"]
    headers = [cell.value for cell in ws[1]]
    rows = []
    for values in ws.iter_rows(min_row=3, values_only=True):
        row = {h: (v.strip() if isinstance(v, str) else v) for h, v in zip(headers, values)}
        if row["company_number"] and any(row[name] for name, _, _ in LABEL_COLUMNS if name != "notes"):
            rows.append(row)
    return rows


def llm_answers(company_numbers: list[str]) -> dict[str, dict]:
    """The LLM's answers for the labelled companies."""
    key = config.EVAL_DESCRIPTIONS[0]
    with connect() as con:
        rows = con.execute(
            """
            SELECT e.company_number, e.website_matches_company, e.website_match_reason, e.market,
                   e.what_they_sell, f.fit_score, f.fit_reason
            FROM enrichments e
            LEFT JOIN fit_scores f
                   ON f.company_number = e.company_number AND f.description_key = ? AND f.prompt_version = ?
            WHERE e.company_number IN (SELECT unnest(?))
            """,
            [key, config.SCORE_PROMPT_VERSION, company_numbers],
        ).fetchall()
    columns = ["company_number", "website", "website_reason", "market", "sells", "fit_score", "fit_reason"]
    return {r[0]: dict(zip(columns, r)) for r in rows}


def agreement_table(pairs: list[tuple[str, str]], values: list[str]) -> list[str]:
    """A markdown table of human labels (rows) against LLM answers (columns)."""
    counts = Counter(pairs)
    lines = ["| You \\ LLM | " + " | ".join(values) + " |", "|---|" + "---:|" * len(values)]
    for human in values:
        lines.append(f"| **{human}** | " + " | ".join(str(counts[(human, llm)] or "") for llm in values) + " |")
    return lines


def make_report() -> str:
    """Compare hand labels with the LLM and return the report as markdown."""
    labels = read_labels()
    llm = llm_answers([row["company_number"] for row in labels])
    key = config.EVAL_DESCRIPTIONS[0]
    out = [
        "# Evaluation: LLM against hand labels",
        "",
        f"{len(labels)} companies labelled by hand from their websites, compared with Claude Haiku 5.5 "
        f"({config.ENRICH_PROMPT_VERSION}, {config.SCORE_PROMPT_VERSION}). The labeller did not see the "
        "LLM's answers. Generated by `python -m lead_gen.evaluate report`.",
        "",
    ]
    disagreements: list[str] = []

    # Website match.
    pairs = [(row["website_is_theirs"], llm[row["company_number"]]["website"]) for row in labels
             if row["website_is_theirs"]]
    agree = sum(h == m for h, m in pairs)
    out += ["## Does the website belong to the company?", "",
            f"Agreement: **{agree} of {len(pairs)}** ({100 * agree / len(pairs):.0f}%).", ""]
    out += agreement_table(pairs, ["yes", "no", "unsure"]) + [""]
    for row in labels:
        answer = llm[row["company_number"]]
        if row["website_is_theirs"] and row["website_is_theirs"] != answer["website"]:
            disagreements.append(
                f"- **{row['name']}**, website match: you said *{row['website_is_theirs']}*, the LLM said "
                f"*{answer['website']}*. LLM reason: \"{answer['website_reason']}\""
            )

    # Market.
    pairs = [(row["market"], llm[row["company_number"]]["market"]) for row in labels if row["market"]]
    agree = sum(h == m for h, m in pairs)
    out += ["## B2B or B2C?", "", f"Agreement: **{agree} of {len(pairs)}** ({100 * agree / len(pairs):.0f}%).", ""]
    out += agreement_table(pairs, ["B2B", "B2C", "both", "unclear"]) + [""]
    for row in labels:
        answer = llm[row["company_number"]]
        if row["market"] and row["market"] != answer["market"]:
            disagreements.append(
                f"- **{row['name']}**, market: you said *{row['market']}*, the LLM said *{answer['market']}*. "
                f"LLM summary: \"{answer['sells']}\""
            )

    # Fit band. The LLM only scored companies whose website it accepted.
    fit_col = f"fit_{key}"
    scored = [row for row in labels if row[fit_col] and llm[row["company_number"]]["fit_score"] is not None]
    unscored = [row for row in labels if row[fit_col] and llm[row["company_number"]]["fit_score"] is None]
    pairs = [(row[fit_col], score_to_band(llm[row["company_number"]]["fit_score"])) for row in scored]
    exact = sum(h == m for h, m in pairs)
    within_one = sum(abs(BAND_ORDER.index(h) - BAND_ORDER.index(m)) <= 1 for h, m in pairs)
    llm_lower = sum(BAND_ORDER.index(m) > BAND_ORDER.index(h) for h, m in pairs)
    out += [f"## Fit for the '{key}' description", "",
            f"> {config.CUSTOMER_DESCRIPTIONS[key]}", "",
            f"Same band: **{exact} of {len(pairs)}** ({100 * exact / len(pairs):.0f}%). "
            f"Within one band: **{within_one} of {len(pairs)}** ({100 * within_one / len(pairs):.0f}%). "
            f"Where they differ, the LLM scored lower {llm_lower} times and higher {len(pairs) - exact - llm_lower} times.",
            ""]
    if unscored:
        out += [f"Not compared: {len(unscored)} companies the LLM did not score because it was not sure the "
                "website was theirs (" + ", ".join(row["name"] for row in unscored) + ").", ""]
    out += agreement_table(pairs, BAND_ORDER) + [""]
    for row in scored:
        answer = llm[row["company_number"]]
        band = score_to_band(answer["fit_score"])
        if row[fit_col] != band:
            note = f" Your note: \"{row['notes']}\"" if row.get("notes") else ""
            disagreements.append(
                f"- **{row['name']}**, fit: you said *{row[fit_col]}*, the LLM said *{band}* "
                f"({answer['fit_score']}). LLM reason: \"{answer['fit_reason']}\"{note}"
            )

    out += ["## Every disagreement", ""] + (disagreements or ["None."]) + [""]
    skipped = [row for row in read_all_rows() if row not in labels]
    if skipped:
        out += ["## Not labelled", ""] + [f"- {row['name']}" for row in skipped] + [""]
    return "\n".join(out)


def read_all_rows() -> list[dict]:
    """Every company row in the sheet, labelled or not."""
    ws = load_workbook(config.LABELLING_SHEET)["Labels"]
    headers = [cell.value for cell in ws[1]]
    return [
        {h: (v.strip() if isinstance(v, str) else v) for h, v in zip(headers, values)}
        for values in ws.iter_rows(min_row=3, values_only=True)
        if values[0]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["sheet", "report"],
                        help="'sheet' creates the labelling spreadsheet; 'report' scores the LLM against it")
    args = parser.parse_args()
    if args.step == "sheet":
        make_sheet()
    else:
        report = make_report()
        RESULTS_MD.write_text(report, encoding="utf-8")
        print(report)
        print(f"\nSaved to {RESULTS_MD}")


if __name__ == "__main__":
    main()
