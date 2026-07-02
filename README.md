# TechPulse — A working briefing for tech professionals

An AI-summarized, auto-refreshing dashboard for working technologists.
Pulls from Reddit, Hacker News, Lobsters, and major engineering / security /
cloud blogs; ranks within five categories; uses **Google Gemini** to distill
the top story in each category into a 3-bullet TL;DR.

**Categories:** AI & ML · Engineering · Security · Cloud & DevOps · Industry

Live at **https://aj01-a.github.io/rustwire/** — hosted on GitHub Pages,
refreshed and deployed by the same GitHub Actions workflow. No third-party
hosting, no manual steps.

```
┌───────────────────────────────────────────────────────────┐
│  GitHub Actions (cron: every 6h, push to main, manual)     │
│   └─► python -m scripts.main                               │
│         ├─ fetch:  reddit / rss / hn / lobsters            │
│         ├─ classify (per-source map + HN title keywords)   │
│         ├─ dedupe + per-source recency + rank-per-category │
│         ├─ Gemini → 3-bullet TL;DR (top of each category)  │
│         └─ write data/feed.json (committed)                │
│                       │                                    │
│                       ▼                                    │
│         deploy to GitHub Pages (same workflow run)         │
│                       │                                    │
│                       ▼                                    │
│              index.html fetches feed.json                  │
└───────────────────────────────────────────────────────────┘
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
cp .env.example .env && $EDITOR .env       # add GEMINI_API_KEY (optional)

GEMINI_API_KEY=... python -m scripts.main  # runs the pipeline once

python -m http.server 8000                  # preview at http://localhost:8000
```

## What lives where

| Path | Purpose |
| --- | --- |
| `index.html`, `styles.css`, `app.js`, `favicon.svg` | Static dashboard; zero build step. |
| `data/feed.json` | Live data, regenerated and committed by the workflow. |
| `scripts/config.py` | **All niche-specific values** — categories, sources, ranking. |
| `scripts/categorizer.py` | Maps items to categories (Reddit/Lobsters/RSS by source; HN by title). |
| `scripts/sources/*.py` | One module per source; each returns `list[dict]` normalized via `utils.normalize_item`. |
| `scripts/main.py` | Orchestrator — fetch → dedupe → rank → summarize → write. |
| `scripts/summarizer.py` | Gemini caller + heuristic fallback. |
| `.github/workflows/update.yml` | 6-hour cron: refresh feed, commit, deploy to GitHub Pages. |

## Retargeting

All niche logic is in **`scripts/config.py`**:

| Constant | Effect |
| --- | --- |
| `CATEGORIES` | Section names, ids, and accent colors. |
| `REDDIT_SUBS` | Map of `subreddit -> category`. |
| `LOBSTERS_TAGS` | Map of `tag -> category`. |
| `RSS_FEEDS` | List of `{name, url, subsource, category}`. |
| `HN_CATEGORY_KEYWORDS` | Title keywords that route HN stories into a category. |
| `MAX_PER_CATEGORY`, `TLDR_PER_CATEGORY` | Volume knobs. |
| `RECENCY_WINDOW_HOURS` | Per-source max age. |
| `SOURCE_WEIGHTS` | Source bias in the ranker. |
| `GEMINI_MODEL` | Defaults to `gemini-2.5-flash`. |

To swap the dashboard to a totally different audience, edit those constants
and push. The frontend reflects the new categories automatically.

## Setup docs

End-to-end walkthrough lives at `Documentations/niche-intel-rust/`. Start at
`README.md` and work through the numbered files.
