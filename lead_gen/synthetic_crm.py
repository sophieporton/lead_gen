"""Stage 6a: generate a messy, synthetic CRM export to clean and match against.

Real CRM exports are messy: the same company entered twice with different
spellings, websites with and without "www", postcodes in any format, free
text where a dropdown should be. This module creates a fake export with
those problems on purpose, so the cleaning and matching stage has something
realistic to work on. No real client data is used.

The fake export contains:
- fictional companies, with made-up names and `.example` web domains so
  they cannot point at real businesses,
- some of our real leads (company-level public data only), as if the sales
  team had already added them, so matching has true matches to find,
- duplicate records of the same company with different mistakes.

Alongside the export it writes an answer key saying which rows are really
the same company, so the matching can be scored exactly.

Run on its own with:

    python -m lead_gen.synthetic_crm

The output is the same on every run (fixed random seed).
"""

import csv
import random
import re
from datetime import date, timedelta

from lead_gen import config
from lead_gen.db import connect

SYNTHETIC_DIR = config.DATA_DIR / "synthetic"
CRM_EXPORT = SYNTHETIC_DIR / "crm_export.csv"
CRM_ANSWER_KEY = SYNTHETIC_DIR / "crm_answer_key.csv"

N_FICTIONAL = 150        # fictional companies
N_EXISTING_LEADS = 20    # real leads that already "exist" in the CRM
DUPLICATE_RATE = 0.18    # share of companies entered more than once

PLACE_WORDS = ["Tyne", "Wear", "Tees", "Northern", "Coastal", "Pennine", "Cheviot", "Wansbeck",
               "Quayside", "Riverside", "Hadrian", "Durham", "Derwent", "Coquet", "Lindisfarne", "Bede"]
TRADE_WORDS = [("Joinery", "Construction"), ("Plumbing & Heating", "Construction"),
               ("Electrical Services", "Construction"), ("Roofing", "Construction"),
               ("Scaffolding", "Construction"), ("Engineering", "Manufacturing"),
               ("Fabrications", "Manufacturing"), ("Print & Design", "Marketing"),
               ("Signs", "Marketing"), ("IT Solutions", "IT services"), ("Software", "IT services"),
               ("Logistics", "Transport"), ("Couriers", "Transport"), ("Catering", "Hospitality"),
               ("Coffee House", "Hospitality"), ("Dental Care", "Healthcare"), ("Physio", "Healthcare"),
               ("Accountancy", "Professional services"), ("Recruitment", "Professional services"),
               ("Cleaning Services", "Facilities")]
SUFFIXES = ["Ltd", "Limited", "Services Ltd", "& Co Ltd", "Group Ltd", "(North East) Ltd"]

TOWNS = {
    "Newcastle upon Tyne": ("NE", ["Newcastle", "NEWCASTLE UPON TYNE", "Newcastle-upon-Tyne", "N'castle"]),
    "Sunderland": ("SR", ["SUNDERLAND", "sunderland", "Sunderland "]),
    "Durham": ("DH", ["DURHAM", "Durham City", "durham"]),
    "Middlesbrough": ("TS", ["MIDDLESBROUGH", "Middlesboro", "M'boro"]),
    "Darlington": ("DL", ["DARLINGTON", "darlington", "Darlo"]),
    "Gateshead": ("NE", ["GATESHEAD", "gateshead"]),
    "Hartlepool": ("TS", ["HARTLEPOOL", "H'pool"]),
}

INDUSTRY_VARIANTS = {
    "Construction": ["Construction", "construction", "Building & Construction", "Constr.", "Trades"],
    "Manufacturing": ["Manufacturing", "manufacturing", "Mfg", "Engineering/Manufacturing"],
    "Marketing": ["Marketing", "Print", "Marketing & Advertising", "marketing"],
    "IT services": ["IT", "IT Services", "Information Technology", "it services", "Tech"],
    "Transport": ["Transport", "Logistics", "Transport & Logistics", "haulage"],
    "Hospitality": ["Hospitality", "Food & Drink", "Restaurants", "hospitality"],
    "Healthcare": ["Healthcare", "Health", "Medical", "healthcare"],
    "Professional services": ["Professional Services", "Prof. services", "Business Services", "B2B services"],
    "Facilities": ["Facilities", "Cleaning", "Facilities Management", "FM"],
    "Other": ["Other", "Misc", "", "TBC"],
}

LEAD_STATUSES = ["New", "new", "Open", "In progress", "In Progress", "Attempted to contact",
                 "Connected", "Unqualified", "Bad timing", ""]


# --- Making clean records ----------------------------------------------------


def slug(text: str) -> str:
    """Lower-case letters and digits only, for building fake domains."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def fake_postcode(rng: random.Random, area: str) -> str:
    """A correctly formatted postcode in the given postcode area."""
    return f"{area}{rng.randint(1, 39)} {rng.randint(1, 9)}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}{rng.choice('ABDEFGHJLNPQRSTUWXYZ')}"


def fictional_companies(rng: random.Random, n: int) -> list[dict]:
    """Clean records for made-up companies."""
    companies, seen = [], set()
    while len(companies) < n:
        place = rng.choice(PLACE_WORDS)
        trade, industry = rng.choice(TRADE_WORDS)
        # One company per place and trade, so no two fictional companies
        # share a name stem or a domain.
        if (place, trade) in seen:
            continue
        seen.add((place, trade))
        name = f"{place} {trade} {rng.choice(SUFFIXES)}"
        town = rng.choice(list(TOWNS))
        companies.append({
            "name": name,
            "domain": f"{slug(place + trade)}.example",
            "town": town,
            "postcode": fake_postcode(rng, TOWNS[town][0]),
            "industry": industry,
            "employees": rng.choice([2, 4, 6, 8, 12, 15, 20, 25, 35, 50, 80]),
            "company_number": None,  # fictional companies have no real number
        })
    return companies


def existing_leads(rng: random.Random, n: int) -> list[dict]:
    """Clean records for some of our real leads, as if already in the CRM."""
    with connect() as con:
        rows = con.execute(
            """
            SELECT c.company_number, c.name, c.post_town, c.postcode, w.url
            FROM enrichments e
            JOIN companies c USING (company_number)
            JOIN websites w USING (company_number)
            WHERE e.website_matches_company = 'yes'
            ORDER BY c.company_number
            """
        ).fetchall()
    chosen = rng.sample(rows, min(n, len(rows)))
    return [{
        "name": name,
        "domain": re.sub(r"^https?://(www\.)?", "", url).split("/")[0],
        "town": town,
        "postcode": postcode,
        "industry": "Other",
        "employees": None,
        "company_number": number,
    } for number, name, town, postcode, url in chosen]


# --- Making them messy -------------------------------------------------------


def messy_name(rng: random.Random, name: str) -> str:
    """The kind of variation people introduce when typing a company name."""
    if rng.random() < 0.4:
        name = re.sub(r"\b(Limited|Ltd)\b\.?", rng.choice(["Ltd", "Ltd.", "LIMITED", "limited", ""]), name)
    if rng.random() < 0.25:
        name = name.replace("&", "and") if "&" in name else name.replace(" and ", " & ")
    if rng.random() < 0.3:
        name = rng.choice([name.upper(), name.lower(), name.title()])
    if rng.random() < 0.15 and len(name) > 6:  # a typo: drop one letter
        i = rng.randrange(1, len(name) - 1)
        name = name[:i] + name[i + 1:]
    if rng.random() < 0.2:
        name = rng.choice([" ", "  "]) + name + rng.choice(["", " ", "  "])
    return re.sub(r" {3,}", "  ", name)


def messy_domain(rng: random.Random, domain: str) -> str:
    """Websites typed with and without protocol, www, paths and capitals."""
    if rng.random() < 0.15:
        return ""
    value = rng.choice(["", "www.", "http://", "https://", "https://www.", "http://www."]) + domain
    if rng.random() < 0.3:
        value += rng.choice(["/", "/contact", "/about-us/", "/home"])
    if rng.random() < 0.1:
        value = value.upper()
    return value


def messy_postcode(rng: random.Random, postcode: str) -> str:
    """Postcodes in lower case, without the space, or missing."""
    roll = rng.random()
    if roll < 0.12:
        return ""
    if roll < 0.3:
        return postcode.replace(" ", "")
    if roll < 0.45:
        return postcode.lower()
    if roll < 0.5:
        return postcode.replace(" ", "  ")
    return postcode


def messy_town(rng: random.Random, town: str) -> str:
    """Town names spelled several ways, or left blank."""
    roll = rng.random()
    if roll < 0.1:
        return ""
    variants = TOWNS.get(town, (None, [town.upper(), town.lower()]))[1]
    return rng.choice(variants) if roll < 0.55 else town


def messy_employees(rng: random.Random, employees: int | None) -> str:
    """Employee counts as numbers, ranges, rough text or blank."""
    if employees is None or rng.random() < 0.2:
        return ""
    return rng.choice([
        str(employees),
        f"{employees}",
        f"approx {employees}",
        f"{max(1, employees - 5)}-{employees + 5}",
        f"{employees}+",
    ])


def messy_date(rng: random.Random, when: date) -> str:
    """Last activity dates in three different formats."""
    return rng.choice([when.strftime("%d/%m/%Y"), when.isoformat(), when.strftime("%d %b %Y")])


def messy_record(rng: random.Random, company: dict, today: date) -> dict:
    """One CRM row for a company, with random mistakes."""
    number = company["company_number"]
    if number and rng.random() < 0.6:
        number = rng.choice([number, number.lstrip("0")])
    else:
        number = ""
    return {
        "Company Name": messy_name(rng, company["name"]),
        "Website": messy_domain(rng, company["domain"]),
        "Town/City": messy_town(rng, company["town"]),
        "Post Code": messy_postcode(rng, company["postcode"] or ""),
        "Industry": rng.choice(INDUSTRY_VARIANTS[company["industry"]]),
        "No. of Employees": messy_employees(rng, company["employees"]),
        "Company Reg No": number,
        "Lead Status": rng.choice(LEAD_STATUSES),
        "Last Activity": messy_date(rng, today - timedelta(days=rng.randint(1, 700))),
    }


def main() -> None:
    rng = random.Random(config.RANDOM_SEED)
    today = date(2026, 10, 20)  # fixed, so the output never changes

    entities = fictional_companies(rng, N_FICTIONAL) + existing_leads(rng, N_EXISTING_LEADS)
    rows, answers = [], []
    for entity_id, company in enumerate(entities, start=1):
        copies = 1
        if rng.random() < DUPLICATE_RATE:
            copies = rng.choice([2, 2, 2, 3])
        for _ in range(copies):
            rows.append((entity_id, company, messy_record(rng, company, today)))

    rng.shuffle(rows)
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Record ID"] + list(rows[0][2])
    with open(CRM_EXPORT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record_id, (_, _, record) in enumerate(rows, start=1001):
            writer.writerow({"Record ID": record_id, **record})
    with open(CRM_ANSWER_KEY, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "entity_id", "company_number"])
        for record_id, (entity_id, company, _) in enumerate(rows, start=1001):
            writer.writerow([record_id, entity_id, company["company_number"] or ""])

    duplicates = len(rows) - len(entities)
    print(f"Wrote {len(rows)} CRM rows for {len(entities)} companies ({duplicates} extra duplicate rows; "
          f"{N_EXISTING_LEADS} of the companies are our real leads) to {CRM_EXPORT}")
    print(f"Answer key: {CRM_ANSWER_KEY}")


if __name__ == "__main__":
    main()
