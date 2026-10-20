# Lead Gen: AI lead research pipeline

A pipeline that finds small businesses in the North East of England, uses an LLM to work out what they do and how well they fit a target customer, cleans the results against a CRM export, and shows everything in a dashboard.

**Status:** work in progress (Week 1 of 4).

## What it does

```
Companies House  ->  find websites  ->  scrape  ->  LLM enrichment  ->  evaluate  ->  CRM clean  ->  dashboard
(bulk data + API)    (Serper search)    (httpx)     (structured output)  (hand labels)  (dedupe)      (Streamlit)
```

1. **Find companies.** Active companies with a registered office in the NE, SR, DH, TS or DL postcode areas that file small company accounts.
2. **Find websites.** Companies House does not store websites, so each company is searched by name and town and the results are checked against the company number and postcode.
3. **Scrape.** The homepage and about page of each matched website, respecting robots.txt.
4. **Enrich.** _Week 2._
5. **Evaluate.** _Week 3._
6. **Clean for the CRM.** _Week 3._
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
```

## Results

_To follow. See [docs/findings.md](docs/findings.md) for running notes._
