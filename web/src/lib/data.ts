// Typed access to the pipeline's results snapshot.
// The JSON is written by `python -m lead_gen.export_dashboard` and contains
// company-level data only.
import raw from "@/data/dashboard.json";

export type Band = "strong" | "possible" | "weak" | "not a fit";

export type Score = {
  score: number;
  band: Band;
  reason: string;
  opener: string | null;
};

export type Lead = {
  company_number: string;
  name: string;
  town: string | null;
  postcode_area: string;
  website: string;
  domain: string;
  sector: string;
  market: "B2B" | "B2C" | "both" | "unclear";
  what_they_sell: string;
  who_they_sell_to: string;
  products_services: string[];
  size_signals: string[];
  growth_signals: string[];
  is_property: boolean;
  in_crm: boolean;
  scores: Record<string, Score>;
};

export type Description = { key: string; label: string; text: string };

type Agreement = { agree: number; total: number; pairs: Record<string, number> };

export type Dashboard = {
  generated: string;
  descriptions: Description[];
  bands: { band: Band; min_score: number }[];
  funnel: Record<string, number>;
  leads: Lead[];
  crm: {
    quality: { measure: string; before: number; after: number }[];
    duplicate_pairs_total: number;
    duplicate_pairs_found: number;
    false_merges: number;
    existing_leads_total: number;
    existing_leads_found: number;
    false_existing: number;
  };
  costs: {
    model: string;
    enrich_per_1000_companies: number;
    score_per_1000_pairs: number;
    project_total_usd: number;
    project_total_calls: number;
  };
  evaluation: {
    labelled: number;
    description_key: string;
    website: Agreement;
    market: Agreement;
    fit: Agreement & {
      exact: number;
      within_one: number;
      before_fix: { exact: number; within_one: number; total: number };
    };
    fit_disagreements: { name: string; human: Band; llm: Band; llm_score: number; llm_reason: string }[];
  };
};

export const data = raw as unknown as Dashboard;

export const BANDS: Band[] = ["strong", "possible", "weak", "not a fit"];

/** CSS variable holding each band's colour. */
export const BAND_COLOUR: Record<Band, string> = {
  strong: "var(--band-strong)",
  possible: "var(--band-possible)",
  weak: "var(--band-weak)",
  "not a fit": "var(--band-none)",
};

export const BAND_RANGE: Record<Band, string> = {
  strong: "80 to 100",
  possible: "50 to 79",
  weak: "20 to 49",
  "not a fit": "0 to 19",
};

export function descriptionLabel(key: string): string {
  return data.descriptions.find((d) => d.key === key)?.label ?? key;
}

/** How many leads fall in each band for one customer description. */
export function bandCounts(leads: Lead[], key: string): Record<Band, number> {
  const counts: Record<Band, number> = { strong: 0, possible: 0, weak: 0, "not a fit": 0 };
  for (const lead of leads) {
    const s = lead.scores[key];
    if (s) counts[s.band] += 1;
  }
  return counts;
}

export const pct = (n: number, d: number) => (d ? Math.round((100 * n) / d) : 0);

/** Contact and source links shown on every page. */
export const SITE = {
  githubUrl: "https://github.com/sophieporton/lead_gen",
  // TODO: replace with your Upwork profile or another contact link.
  contactUrl: "https://github.com/sophieporton",
  contactLabel: "Get in touch",
};
