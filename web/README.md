# Dashboard

The public demo site for the lead research pipeline: a static Next.js app that reads one JSON snapshot of the pipeline's results. It has no database and makes no API or LLM calls.

## Update the data

From the project root, after re-running any pipeline stage:

```bash
python -m lead_gen.export_dashboard
```

This rewrites `src/data/dashboard.json` (company-level data only).

## Run locally

```bash
npm install
npm run dev
```

Then open http://localhost:3000.

## Deploy

Deployed on Vercel from the GitHub repo, with the project's Root Directory set to `web`. Every push to `main` redeploys.
