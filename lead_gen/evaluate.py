"""Stage 5: evaluate the LLM against hand labels.

Step 1 creates a spreadsheet of companies to label by hand:

    python -m lead_gen.evaluate sheet

The sheet shows only each company's name, town and website. It does not
show the LLM's answers, so the labels are not influenced by them. Fill in
the yellow columns using the dropdowns, then save the file.

Step 2 (added once the labels exist) compares the labels with the LLM's
answers and reports accuracy, including the cases it got wrong.
"""

import argparse

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["sheet"], help="'sheet' creates the labelling spreadsheet")
    args = parser.parse_args()
    if args.step == "sheet":
        make_sheet()


if __name__ == "__main__":
    main()
