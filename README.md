# Lead Gen: AI lead research pipeline

A pipeline that finds small businesses in the North East of England, uses an LLM to work out what they do and how well they fit a target customer, cleans the results against a CRM export, and shows everything in a dashboard.

**Status:** work in progress (Week 3 of 4). The dashboard is still to come.

## What it does

```
Companies House  ->  find websites  ->  scrape  ->  LLM enrichment  ->  evaluate  ->  CRM clean  ->  dashboard
(bulk data + API)    (Serper search)    (httpx)     (structured output)  (hand labels)  (dedupe)      (Streamlit)
```

1. **Find companies.** Active companies with a registered office in the NE, SR, DH, TS or DL postcode areas that file small company accounts.
2. **Find websites.** Companies House does not store websites, so each company is searched by name and town and the results are checked against the company number and postcode.
3. **Scrape.** The homepage and about page of each matched website, respecting robots.txt.
4. **Enrich.** Claude Haiku 5.5 reads each site and returns a profile validated with Pydantic: what they sell, who to, B2B or B2C, size and growth signals, and whether the site really is theirs. It then scores each lead against example customer descriptions and drafts a short outreach opener. Every call is cached and costed.
5. **Evaluate.** Hand labels for 25 companies, compared with the LLM's answers, with every disagreement listed in [eval/results.md](eval/results.md).
6. **Clean for the CRM.** A synthetic, deliberately messy CRM export is cleaned, de-duplicated and matched against the new leads, and the new ones are exported as a HubSpot-ready CSV.
7. **Dashboard.** _Week 4._

## Data and GDPR

This project uses company-level public data only:

- Companies House records, which are published for public use.
- The public homepage and about page of each company's own website.

It does not collect names, emails or phone numbers of individuals (email addresses and phone numbers are stripped from scraped text before it is stored), and it does not scrape LinkedIn or other social networks. Keeping to company-level data means the pipeline does not process personal data about individuals in the first place, which is the simplest way to stay within UK GDPR. The CRM data used for matching is synthetic.

Scraping is polite: the pipeline checks robots.txt, waits between requests to the same site and identifies itself with a clear user agent.

## How to run

```bash
conda create -n leadgen python=3.12
conda activate leadgen
pip install -r requirements.txt
cp .env.example .env   # then add your API keys
```

Each stage can be run on its own and can be re-run safely:

```bash
python -m lead_gen.db              # create the database
python -m lead_gen.find_companies  # stage 1
python -m lead_gen.find_websites   # stage 2
python -m lead_gen.scrape          # stage 3
python -m lead_gen.enrich          # stage 4a (needs ANTHROPIC_API_KEY)
python -m lead_gen.score           # stage 4b
python -m lead_gen.evaluate sheet  # stage 5: create the labelling sheet
python -m lead_gen.synthetic_crm   # stage 6a: generate the synthetic CRM export
python -m lead_gen.crm_clean       # stage 6b: clean, de-duplicate and match
python -m lead_gen.hubspot_export  # stage 6c: HubSpot-ready CSV of new leads
```

## Results

Full results so far are in [docs/findings.md](docs/findings.md). In short:

- Of 200 sampled companies, 55 (27.5%) have a website the pipeline and the LLM agree is theirs. Property companies almost never do (1 of 33).
- LLM enrichment and scoring cost about $0.54 per 1,000 companies, plus $0.28 per 1,000 fit scores, with Claude Haiku 5.5. The whole project so far has cost $0.22 in LLM calls.
- The LLM caught wrong website matches the rules missed, such as a US company with a similar name.
- Against hand labels, the LLM's website check agreed 88% of the time. Fit scoring started at 14% exact agreement because the prompt penalised websites that don't state headcount; after fixing that, 76% of scores were within one band of the human label (likely optimistic, as the fix was tuned on the same labels).
- CRM matching found 56 of 60 duplicate pairs and all 20 existing leads, with no false merges.
