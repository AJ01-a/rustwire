# Rustwire — Niche Intelligence for Rust Systems Programmers

A hyper-focused, auto-refreshing dashboard for the Rust systems-programming
community. The pipeline pulls from **r/rust**, **This Week in Rust**, the
**Rust** and **Inside Rust** blogs, **Lobsters**, and **Hacker News**, ranks the
results, and uses **Google Gemini** to distill the five most-discussed items
into 3-bullet TL;DRs.

```
┌───────────────────────────────────────────────────────────┐
│  GitHub Actions (cron: every 6h)                           │
│   └─► python -m scripts.main                               │
│         ├─ fetch: reddit / rss / hn / lobsters             │
│         ├─ dedupe + rank                                   │
│         ├─ Gemini → 3-bullet TL;DRs                        │
│         └─ write data/feed.json (committed)                │
│                       │                                    │
│                       ▼                                    │
│              Netlify rebuilds static site                  │
│                       │                                    │
│                       ▼                                    │
│              index.html fetches feed.json                  │
└───────────────────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. install deps
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt

# 2. (optional) set your Gemini key — pipeline falls back to heuristics without one
cp .env.example .env && $EDITOR .env

# 3. run the pipeline once
GEMINI_API_KEY=... python -m scripts.main

# 4. preview the dashboard
python -m http.server 8000
# open http://localhost:8000
```

## What lives where

| Path | Purpose |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | Static dashboard, deployed straight to Netlify. |
| `data/feed.json` | The live data file — regenerated and committed by Actions. |
| `scripts/` | Python ingestion pipeline. Each `sources/*.py` is a single fetcher. |
| `.github/workflows/update.yml` | The 6-hour cron + auto-commit job. |
| `netlify.toml` | Cache headers + zero-build static config. |

## Step-by-step setup

Walk through the docs at `Documentations/niche-intel-rust/` for:

1. Prerequisites and tooling
2. Local development
3. Pushing to GitHub
4. Getting a Gemini API key
5. Configuring GitHub Actions secrets
6. Deploying to Netlify
7. Customizing sources, niche, ranking
8. Troubleshooting

## Retargeting the niche

Everything niche-specific lives in `scripts/config.py`:

- `REDDIT_SUBREDDITS` — list of subreddits to crawl
- `RSS_FEEDS` — list of `{name, url, subsource}` dicts
- `HN_QUERY` — keyword passed to the HN Algolia API
- `LOBSTERS_TAG_URL` — Lobsters tag JSON endpoint
- `SOURCE_WEIGHTS` — bias toward/away from sources in the ranker

Change those four values and the dashboard is now about something else.
