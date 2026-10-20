# Findings

Running notes on what the data shows at each stage. These feed the README.

## Stage 1: Companies House

Source: Companies House bulk company data, 1 October 2026 snapshot.

120,104 active companies have a registered office in the NE, SR, DH, TS or DL postcode areas. Their latest accounts category:

| Accounts category | Companies |
|---|---:|
| MICRO ENTITY | 42,949 |
| NO ACCOUNTS FILED | 30,184 |
| TOTAL EXEMPTION FULL | 28,327 |
| DORMANT | 10,912 |
| UNAUDITED ABRIDGED | 3,462 |
| FULL | 1,546 |
| SMALL | 1,124 |
| AUDIT EXEMPTION SUBSIDIARY | 656 |
| GROUP | 595 |
| MEDIUM | 149 |
| ACCOUNTS TYPE NOT AVAILABLE | 59 |
| TOTAL EXEMPTION SMALL | 57 |
| FILING EXEMPTION SUBSIDIARY | 56 |
| AUDITED ABRIDGED | 27 |
| PARTIAL EXEMPTION | 1 |

Filtering on the "SMALL" category alone would return only 1,124 companies. Most small companies file under "TOTAL EXEMPTION FULL" or "UNAUDITED ABRIDGED" instead, and the very smallest file as "MICRO ENTITY". "NO ACCOUNTS FILED" is mostly companies less than about 21 months old that have not reached their first filing deadline.

### Filter and sample

- Included: TOTAL EXEMPTION FULL, UNAUDITED ABRIDGED, SMALL, TOTAL EXEMPTION SMALL. Micro entities are left out because many are sole contractors with no website.
- Private and public limited companies only. Excludes SIC codes 99999 (dormant), 74990 (non-trading) and 64209 (holding companies).
- 29,244 companies pass the filters.
- The 200-company sample is split by postcode area in proportion to size: NE 95, TS 43, DL 27, DH 22, SR 13.
- Checking against the live API: 1 of 201 sampled companies was in receivership and was replaced, so the bulk file is a reliable starting point.
- Real estate (SIC division 68) is the largest group in the sample at 34 of 200 (17%). Many of these will be property letting companies with no website.

## Stage 2: website finding

### First run (20 October 2026)

One Serper search per company (`"<name>" <town>`), keeping the top 5 results after removing a fixed list of directory and social sites. 197 of 200 companies completed; 3 hit connection errors and will be retried.

| Match status | Companies |
|---|---:|
| confirmed (company number on the site) | 18 |
| likely (name in domain, plus postcode or name on the site) | 36 |
| ambiguous | 16 |
| not_found | 127 |

So 54 of 197 companies (27%) have a confirmed or likely website after the first pass.

**What the spot check showed** (eyeballing 8 confirmed, 8 likely, all 16 ambiguous and 14 not_found):

- Confirmed and likely matches all look right. None of them is on a domain shared with another company.
- Directories crowd out real websites. Half of all stored results (49%) are on a domain that came up for 3 or more different companies, e.g. doogal.co.uk (48 companies), tracxn.com (32), tinytax.co.uk (31), qapital.ai (26), formationdata.co.uk (22). The fixed blocklist missed these. For many not_found companies, all 5 slots went to directories.
- Several ambiguous matches look like the real site (hygienicwallinstallation.co.uk, jjelectricalne.co.uk, westgatelabs.co.uk) but the homepage had no company number or postcode, often because the registered office is an accountant's address. Two "ambiguous" results were on wheree.com, another directory.
- 133 of 682 homepage checks failed to load (blocked, timed out or an HTTP error) and 50 were blocked by robots.txt. Those candidates could only be scored on their domain and title.
- Property companies (SIC division 68) almost never have a website: 1 match out of 32. IT companies (division 62) are the opposite: 8 out of 11.

### Second run, with directory detection (20 October 2026)

Changes: store all 10 results per search, search for every company before visiting any sites, and treat any domain that appears for 3 or more different companies as a directory. 42 domains were caught this way. At most 5 non-directory sites are visited per company.

| Match status | First run | Second run |
|---|---:|---:|
| confirmed | 18 | 19 |
| likely | 36 | 36 |
| ambiguous | 16 | 14 |
| not_found | 127 | 131 |
| total | 197 | 200 |

**What this shows:**

- Directories were not hiding many real websites. Removing them and looking further down the results found only one extra match. Tru-Blu Financial moved from a wheree.com listing to its own site, trublufinancial.co.uk. So most of the 131 not_found companies very likely have no website, rather than one we failed to find.
- 55 of 200 companies (27.5%) have a confirmed or likely website, and 14 more (7%) are ambiguous.
- Site visits that failed dropped from 133 to 66, and robots.txt blocks from 50 to 6, because far fewer directory sites were visited. Of 1,000-plus stored results, 361 were skipped as directories.
- No confirmed or likely website is shared by two companies, which is a good sign the matches are not directory pages.
- Two companies only had a dead site in their results. The pipeline now checks our own connection before deciding whether to retry later or record not_found.
- The 14 ambiguous matches mostly look like the real site (e.g. westgatelabs.co.uk, sabremh.co.uk, scotchcornercommercials.co.uk) but lack a company number or postcode on the homepage. They go to the LLM check in stage 4.

## Stage 3: scraping

Scraped the 69 companies with a confirmed, likely or ambiguous website (20 October 2026). Ambiguous ones are included so the LLM can check them in stage 4.

| Page | Stored | With text | Average length |
|---|---:|---:|---:|
| Homepage | 69 | 65 (94%) | 4,799 characters |
| About page | 69 | 47 (68%) | 3,737 characters |

- 18 sites have no link that looks like an about page. Small sites often put everything on the homepage.
- 4 homepages failed: 2 refused with HTTP 403 (usually bot protection) and 2 disconnected without a response. None were blocked by robots.txt.
- One homepage (groundsix.com) has only 183 characters of text. It is probably built with JavaScript, which a simple fetcher does not run.
- Email addresses and phone numbers are removed from all stored text, because they often belong to individuals and no later stage needs them. 92 pages had at least one removed.
- The ambiguous matches need checking. For example lighthouseaccommodation.co.uk is a listings site for lighthouse stays, so it is probably not Seaham Lighthouse Ltd's own website.

## Stage 4a: LLM enrichment

Model: Claude Haiku 5.5 (`claude-haiku-5-5`) at low effort, with output validated against a Pydantic schema. 65 companies had scraped text (4 of the 69 scraped sites returned none). Run on 20 October 2026.

### Cost

| Prompt version | Calls | Input tokens | Output tokens | Cost |
|---|---:|---:|---:|---:|
| enrich-v1 | 65 | 241,365 | 21,205 | $0.035 |
| enrich-v2 | 65 | 246,435 | 21,232 | $0.035 |

About **$0.54 per 1,000 companies**, or roughly 3,800 input and 330 output tokens per company. Responses are cached, so re-running an unchanged prompt costs nothing.

### Website check

The LLM was also asked whether each website really belongs to the company. Compared with the stage 2 rules:

| Stage 2 status | LLM: yes | LLM: unsure | LLM: no |
|---|---:|---:|---:|
| confirmed | 19 | 0 | 0 |
| likely | 29 | 4 | 2 |
| ambiguous | 7 | 1 | 3 |

- It agreed with all 19 confirmed matches (company number on the site).
- It confirmed 7 of the 11 ambiguous matches with text, often by spotting the registered postcode in the about page, which stage 2 did not check.
- It caught 2 wrong "likely" matches that the rules could not: Nulite Ltd's match was a US lighting company, and Tru-Blu Financial's site belongs to a different company with a similar trading name.
- It rejected 3 ambiguous matches, including a lighthouse holiday listings site matched to Seaham Lighthouse Ltd and a travel blog matched to Durham Micropub Ltd.

That leaves **55 companies with a website the LLM agrees is theirs**: 25 B2B, 11 B2C, 15 both, 4 unclear. 49 of 65 profiles list at least one size signal and 26 a growth signal.

### Personal data

With prompt v1, 2 of 65 profiles named an individual (a blog author and a company director), despite an instruction not to. Prompt v2 says to refer to people by role only, and the pipeline now flags phrases that look like a named person after every run. v2 produced no flagged names. v2 also asks for countable size facts (staff, branches, years trading) rather than phrases like "family business".

## Stage 4b: fit scoring and outreach openers

Each of the 55 companies with a confirmed website was scored against 5 example customer descriptions (see `CUSTOMER_DESCRIPTIONS` in `lead_gen/config.py`), using the short stage 4a profile rather than the full page text. Run on 20 October 2026 with Claude Haiku 5.5.

| Customer description | Strong (80+) | Possible (50-79) | Weak (20-49) | Not a fit (<20) |
|---|---:|---:|---:|---:|
| Card payments for local shops | 4 | 4 | 11 | 36 |
| Managed IT support | 0 | 10 | 20 | 25 |
| Packaging and warehouse supplies | 1 | 4 | 7 | 43 |
| Health and safety training | 5 | 10 | 23 | 17 |
| Van leasing for trades | 0 | 11 | 14 | 30 |

The top leads look sensible. For card payments: an optician (92), a fish and chip shop (88) and a cafe (85). For safety training: an industrial plant maintenance firm (85), an M&E engineer (82) and a roofer (82). For van leasing: two refrigeration engineers and a roofer (72 to 75).

- Few companies score 80+ for IT support or van leasing, because most websites do not state staff numbers or vehicle use, and the prompt lowers the score when evidence is missing.
- The packaging supplier in the sample scored 12 for the packaging description: the model recognised it as a likely competitor rather than a customer.

### Prompt changes

score-v1 was tried on 3 companies first. Its openers were often pointless for poor fits ("this may not be a relevant fit"), sometimes added praise not in the profile ("recognised for their design"), and often started with "I noticed". score-v2 only writes an opener for scores of 50 or more (49 openers in total), caps them at about 40 words, and forbids facts that are not in the profile. Across v2: no opener starts with "I noticed", none use exclamation marks or em dashes, and the average length is 40 words (range 29 to 61, so the cap is not always kept).

Scores near a band boundary are not perfectly stable between prompt versions: on the same 3 companies, one score moved from 88 to 80 and another from 35 to 50. The evaluation should judge bands, not exact numbers.

### Cost

275 calls, 341,815 input and 64,263 output tokens: **$0.066**, or about $0.24 per 1,000 company and description pairs. Total LLM spend for the project so far, including discarded prompt versions: **$0.14**.
