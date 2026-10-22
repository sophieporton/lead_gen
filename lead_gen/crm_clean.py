"""Stage 6b: clean the CRM export, find duplicates, and match our leads to it.

Steps:
1. Standardise every field of the messy CRM export: company names,
   websites, postcodes, towns, industries, employee counts, company
   numbers, lead statuses and dates.
2. Group CRM rows that are the same company, and merge each group into one
   record that keeps the most complete values.
3. Check each of our new leads against the cleaned CRM, so the sales team
   only gets leads they do not already have.
4. Measure data quality before and after cleaning, and score the duplicate
   detection and lead matching against the synthetic answer key.

The matching rules are deliberately simple and explainable. Two records
are the same company if any of these hold:
- same company number,
- same website domain,
- same cleaned name, and the postcodes agree (or one is missing),
- very similar cleaned names (a typo or two) and the same postcode.

Run on its own with:

    python -m lead_gen.crm_clean
"""

import csv
import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

import duckdb

from lead_gen.db import connect
from lead_gen.synthetic_crm import CRM_ANSWER_KEY, CRM_EXPORT

# Legal suffixes and region tags that vary between records of the same company.
NAME_NOISE = r"\b(LIMITED|LTD|PLC|LLP|AND CO|CO|NORTH EAST|NE)\b"
FUZZY_NAME_THRESHOLD = 0.9

UK_POSTCODE = re.compile(r"^([A-Z]{1,2}[0-9][0-9A-Z]?)([0-9][A-Z]{2})$")

TOWN_ALIASES = {
    "NEWCASTLE": "Newcastle upon Tyne", "NEWCASTLE UPON TYNE": "Newcastle upon Tyne",
    "NEWCASTLE-UPON-TYNE": "Newcastle upon Tyne", "N'CASTLE": "Newcastle upon Tyne",
    "MIDDLESBORO": "Middlesbrough", "M'BORO": "Middlesbrough",
    "DARLO": "Darlington", "H'POOL": "Hartlepool", "DURHAM CITY": "Durham",
}

INDUSTRY_ALIASES = {
    "Construction": ["construction", "building & construction", "constr.", "trades"],
    "Manufacturing": ["manufacturing", "mfg", "engineering/manufacturing"],
    "Marketing": ["marketing", "print", "marketing & advertising"],
    "IT services": ["it", "it services", "information technology", "tech"],
    "Transport and logistics": ["transport", "logistics", "transport & logistics", "haulage"],
    "Hospitality": ["hospitality", "food & drink", "restaurants"],
    "Healthcare": ["healthcare", "health", "medical"],
    "Professional services": ["professional services", "prof. services", "business services", "b2b services"],
    "Facilities": ["facilities", "cleaning", "facilities management", "fm"],
}
INDUSTRY_LOOKUP = {alias: canonical for canonical, aliases in INDUSTRY_ALIASES.items() for alias in aliases}

LEAD_STATUS_LOOKUP = {
    "new": "NEW", "open": "OPEN", "in progress": "IN_PROGRESS", "attempted to contact": "ATTEMPTED_TO_CONTACT",
    "connected": "CONNECTED", "unqualified": "UNQUALIFIED", "bad timing": "BAD_TIMING",
}


# --- Cleaning one field at a time -------------------------------------------


def clean_name_key(name: str | None) -> str:
    """A comparison key for company names: "  Bede Dental Care & Co Ltd" -> "BEDE DENTAL CARE"."""
    if not name:
        return ""
    key = name.upper().replace("&", " AND ")
    key = re.sub(r"[^A-Z0-9 ]", " ", key)
    key = re.sub(NAME_NOISE, " ", key)
    return re.sub(r"\s+", " ", key).strip()


def clean_display_name(name: str | None) -> str | None:
    """A tidy version of the name for display: "  BEDE DENTAL CARE LTD." -> "Bede Dental Care Ltd"."""
    if not name or not name.strip():
        return None
    name = re.sub(r"\s+", " ", name.strip())
    if name.isupper() or name.islower():
        name = name.title()
        # Title case turns short acronyms into words: put them back.
        name = re.sub(r"\b(Ne|Uk|It|Llp|Cic|Plc)\b", lambda m: m.group(1).upper(), name)
    return re.sub(r"\b(ltd\.?|limited)$", "Ltd", name, flags=re.IGNORECASE)


def clean_domain(website: str | None) -> str | None:
    """The bare domain of a website: "HTTPS://www.Example.co.uk/contact" -> "example.co.uk"."""
    if not website or not website.strip():
        return None
    domain = re.sub(r"^https?://", "", website.strip().lower())
    domain = domain.removeprefix("www.").split("/")[0]
    return domain or None


def clean_postcode(postcode: str | None) -> str | None:
    """A valid, consistently formatted UK postcode, or None: "dl31 9wg" -> "DL31 9WG"."""
    if not postcode:
        return None
    compact = re.sub(r"\s+", "", postcode.upper())
    match = UK_POSTCODE.match(compact)
    return f"{match.group(1)} {match.group(2)}" if match else None


def clean_town(town: str | None) -> str | None:
    """A consistent town name: "Darlo" -> "Darlington", "GATESHEAD" -> "Gateshead"."""
    if not town or not town.strip():
        return None
    upper = re.sub(r"\s+", " ", town.strip().upper())
    return TOWN_ALIASES.get(upper, upper.title().replace(" Upon ", " upon ").replace(" On ", " on "))


def clean_industry(industry: str | None) -> str | None:
    """Map free-text industries onto a fixed list."""
    if not industry or not industry.strip():
        return None
    return INDUSTRY_LOOKUP.get(industry.strip().lower(), "Other")


def clean_employees(value: str | None) -> int | None:
    """A single number from "approx 20", "15-25", "20+" or "20"."""
    numbers = [int(n) for n in re.findall(r"\d+", value or "")]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers))


def clean_company_number(value: str | None) -> str | None:
    """Companies House numbers are 8 characters: "7819273" -> "07819273"."""
    if not value or not value.strip():
        return None
    value = value.strip().upper()
    return value.zfill(8) if value.isdigit() else value


def clean_lead_status(value: str | None) -> str | None:
    """Map lead statuses onto HubSpot's internal values."""
    return LEAD_STATUS_LOOKUP.get((value or "").strip().lower())


def clean_date(value: str | None) -> str | None:
    """Dates in any of the export's formats, as ISO (YYYY-MM-DD)."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime((value or "").strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def clean_record(raw: dict) -> dict:
    """Clean every field of one CRM row."""
    return {
        "record_id": int(raw["Record ID"]),
        "name": clean_display_name(raw["Company Name"]),
        "name_key": clean_name_key(raw["Company Name"]),
        "domain": clean_domain(raw["Website"]),
        "town": clean_town(raw["Town/City"]),
        "postcode": clean_postcode(raw["Post Code"]),
        "industry": clean_industry(raw["Industry"]),
        "employees": clean_employees(raw["No. of Employees"]),
        "company_number": clean_company_number(raw["Company Reg No"]),
        "lead_status": clean_lead_status(raw["Lead Status"]),
        "last_activity": clean_date(raw["Last Activity"]),
    }


# --- Matching ----------------------------------------------------------------


def same_company(a: dict, b: dict) -> str | None:
    """Return the rule that says two records are the same company, or None."""
    if a["company_number"] and a["company_number"] == b["company_number"]:
        return "company number"
    if a["domain"] and a["domain"] == b["domain"]:
        return "domain"
    postcodes_agree = not a["postcode"] or not b["postcode"] or a["postcode"] == b["postcode"]
    if a["name_key"] and a["name_key"] == b["name_key"] and postcodes_agree:
        return "name"
    # Similar names only count when both records have the same postcode.
    # Without that, "Tees Print & Design" and "Bede Print & Design" (90%
    # similar) were wrongly merged. A missed duplicate is cheaper to fix than
    # two companies merged into one, so this rule errs on the side of caution.
    if (a["name_key"] and b["name_key"] and a["postcode"] and a["postcode"] == b["postcode"]
            and SequenceMatcher(None, a["name_key"], b["name_key"]).ratio() >= FUZZY_NAME_THRESHOLD):
        return "similar name and postcode"
    return None


def group_duplicates(records: list[dict]) -> dict[int, int]:
    """Assign every record a group ID, joining records that are the same company.

    Uses union-find, so if A matches B and B matches C, all three end up in
    one group even if A and C do not match directly.
    """
    parent = {r["record_id"]: r["record_id"] for r in records}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if same_company(a, b):
                parent[find(b["record_id"])] = find(a["record_id"])
    return {r["record_id"]: find(r["record_id"]) for r in records}


def merge_group(records: list[dict]) -> dict:
    """Merge duplicate records, keeping the most complete value for each field.

    For each field, take the most common non-empty value; ties go to the
    most recently active record.
    """
    records = sorted(records, key=lambda r: r["last_activity"] or "", reverse=True)
    merged = {"record_ids": [r["record_id"] for r in records]}
    for field in ["name", "name_key", "domain", "town", "postcode", "industry", "employees",
                  "company_number", "lead_status", "last_activity"]:
        values = [r[field] for r in records if r[field] not in (None, "")]
        merged[field] = max(values, key=values.count) if values else None
    merged["last_activity"] = records[0]["last_activity"]
    return merged


def lead_records(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Our verified leads, in the same shape as cleaned CRM records."""
    rows = con.execute(
        """
        SELECT c.company_number, c.name, w.url, c.post_town, c.postcode
        FROM enrichments e
        JOIN companies c USING (company_number)
        JOIN websites w USING (company_number)
        WHERE e.website_matches_company = 'yes'
        """
    ).fetchall()
    return [{
        "company_number": number, "name": name, "name_key": clean_name_key(name),
        "domain": clean_domain(url), "town": clean_town(town), "postcode": clean_postcode(postcode),
    } for number, name, url, town, postcode in rows]


# --- Data quality ------------------------------------------------------------


def quality_report(raw: list[dict], clean: list[dict], merged: list[dict]) -> list[tuple]:
    """Field-by-field data quality, before and after cleaning."""
    def share(rows: list, test) -> float:
        return round(100 * sum(1 for r in rows if test(r)) / len(rows), 1)

    return [
        ("Rows", len(raw), len(merged)),
        ("Duplicate rows (%)", round(100 * (len(raw) - len(merged)) / len(raw), 1), 0.0),
        ("Valid, consistently formatted postcode (%)",
         share(raw, lambda r: (r["Post Code"] or "") == (clean_postcode(r["Post Code"]) or "#")),
         share(merged, lambda r: r["postcode"] is not None)),
        ("Website as a bare domain (%)",
         share(raw, lambda r: bool(r["Website"]) and r["Website"] == clean_domain(r["Website"])),
         share(merged, lambda r: r["domain"] is not None)),
        ("Distinct industry values", len({r["Industry"] for r in raw}), len({r["industry"] for r in merged})),
        ("Distinct town spellings", len({r["Town/City"] for r in raw}), len({r["town"] for r in merged})),
        ("Employee count usable as a number (%)",
         share(raw, lambda r: r["No. of Employees"].strip().isdigit()),
         share(merged, lambda r: r["employees"] is not None)),
        ("Dates in ISO format (%)",
         share(raw, lambda r: bool(re.match(r"^\d{4}-\d{2}-\d{2}$", r["Last Activity"]))),
         share(merged, lambda r: r["last_activity"] is not None)),
    ]


def score_against_answer_key(groups: dict[int, int], lead_matches: dict[str, int | None]) -> dict:
    """Compare duplicate groups and lead matches with the synthetic answer key."""
    with open(CRM_ANSWER_KEY, encoding="utf-8") as f:
        key = list(csv.DictReader(f))
    true_entity = {int(k["record_id"]): k["entity_id"] for k in key}
    ids = sorted(true_entity)

    # Pairwise precision and recall for duplicate detection.
    tp = fp = fn = 0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            same_true = true_entity[a] == true_entity[b]
            same_pred = groups[a] == groups[b]
            tp += same_true and same_pred
            fp += same_pred and not same_true
            fn += same_true and not same_pred

    # Lead matching: which of our leads are really already in the CRM?
    in_crm = {k["company_number"] for k in key if k["company_number"]}
    lead_tp = sum(1 for n, g in lead_matches.items() if g is not None and n in in_crm)
    lead_fp = sum(1 for n, g in lead_matches.items() if g is not None and n not in in_crm)
    lead_fn = sum(1 for n, g in lead_matches.items() if g is None and n in in_crm)
    return {
        "duplicate_pairs": tp + fn, "duplicates_found": tp, "false_duplicates": fp,
        "existing_leads": lead_tp + lead_fn, "existing_found": lead_tp, "false_existing": lead_fp,
    }


def main() -> None:
    with open(CRM_EXPORT, encoding="utf-8") as f:
        raw = list(csv.DictReader(f))
    clean = [clean_record(r) for r in raw]

    groups = group_duplicates(clean)
    members = defaultdict(list)
    for record in clean:
        members[groups[record["record_id"]]].append(record)
    merged = [dict(merge_group(rs), group_id=gid) for gid, rs in members.items()]

    with connect() as con:
        leads = lead_records(con)
        lead_matches: dict[str, int | None] = {}
        match_rules: dict[str, str | None] = {}
        for lead in leads:
            hit = next(((m["group_id"], rule) for m in merged if (rule := same_company(lead, m))), (None, None))
            lead_matches[lead["company_number"]], match_rules[lead["company_number"]] = hit

        con.execute(
            """
            CREATE OR REPLACE TABLE crm_clean (
                group_id INTEGER, record_ids INTEGER[], name VARCHAR, domain VARCHAR, town VARCHAR,
                postcode VARCHAR, industry VARCHAR, employees INTEGER, company_number VARCHAR,
                lead_status VARCHAR, last_activity DATE
            )
            """
        )
        con.executemany(
            "INSERT INTO crm_clean VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [[m["group_id"], m["record_ids"], m["name"], m["domain"], m["town"], m["postcode"],
              m["industry"], m["employees"], m["company_number"], m["lead_status"], m["last_activity"]]
             for m in merged],
        )
        con.execute("CREATE OR REPLACE TABLE lead_crm_matches (company_number VARCHAR, crm_group_id INTEGER, match_rule VARCHAR)")
        con.executemany("INSERT INTO lead_crm_matches VALUES (?, ?, ?)",
                        [[n, g, match_rules[n]] for n, g in lead_matches.items()])

        quality = quality_report(raw, clean, merged)
        con.execute("CREATE OR REPLACE TABLE crm_quality (measure VARCHAR, before_cleaning DOUBLE, after_cleaning DOUBLE)")
        con.executemany("INSERT INTO crm_quality VALUES (?, ?, ?)", quality)

    print(f"CRM: {len(raw)} rows -> {len(merged)} companies after merging duplicates.\n")
    print(f"{'Data quality':<45} {'before':>8} {'after':>8}")
    for measure, before, after in quality:
        print(f"  {measure:<43} {before:>8} {after:>8}")

    new = sum(1 for g in lead_matches.values() if g is None)
    print(f"\nLeads: {len(leads)} verified, {len(leads) - new} already in the CRM, {new} new.")
    rules = defaultdict(int)
    for rule in match_rules.values():
        if rule:
            rules[rule] += 1
    print("  Matched by:", ", ".join(f"{rule} ({n})" for rule, n in rules.items()))

    score = score_against_answer_key(groups, lead_matches)
    print("\nAgainst the answer key:")
    print(f"  Duplicate pairs found: {score['duplicates_found']} of {score['duplicate_pairs']}, "
          f"with {score['false_duplicates']} false matches")
    print(f"  Existing leads found: {score['existing_found']} of {score['existing_leads']}, "
          f"with {score['false_existing']} false matches")


if __name__ == "__main__":
    main()
