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

_Hit rate, match status split and spot-check results go here._

## Stage 3: scraping

_Fetch success rate, robots.txt blocks and errors go here._
