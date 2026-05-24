"""Configuration for the Rustwire ingestion pipeline.

All source URLs, fetch limits, and ranking weights live here so the niche
can be retargeted without touching pipeline code.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
FEED_PATH: Path = DATA_DIR / "feed.json"

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
# Reddit blocks default Python user-agents. Use a descriptive one.
USER_AGENT: str = "Rustwire/1.0 (+https://github.com/) niche-intel aggregator"
REQUEST_TIMEOUT: int = 20  # seconds
MAX_RETRIES: int = 3

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
REDDIT_SUBREDDITS: list[str] = [
    "rust",
    "rust_gamedev",
    "learnrust",
]
REDDIT_FETCH_PER_SUB: int = 25
REDDIT_TIME_WINDOW: str = "day"  # one of: hour, day, week, month, year, all

RSS_FEEDS: list[dict[str, str]] = [
    {
        "name": "This Week in Rust",
        "url": "https://this-week-in-rust.org/rss.xml",
        "subsource": "TWiR",
    },
    {
        "name": "Rust Blog",
        "url": "https://blog.rust-lang.org/feed.xml",
        "subsource": "rust-lang.org",
    },
    {
        "name": "Read Rust",
        "url": "https://readrust.net/all/feed.rss",
        "subsource": "readrust.net",
    },
    {
        "name": "Inside Rust",
        "url": "https://blog.rust-lang.org/inside-rust/feed.xml",
        "subsource": "inside-rust",
    },
]

LOBSTERS_TAG_URL: str = "https://lobste.rs/t/rust.json"

# Hacker News Algolia search API. We filter to last 24h and the keyword "rust".
HN_SEARCH_URL: str = "https://hn.algolia.com/api/v1/search"
HN_QUERY: str = "rust"
HN_MIN_POINTS: int = 20

# ---------------------------------------------------------------------------
# Ranking / output limits
# ---------------------------------------------------------------------------
MAX_DISCUSSIONS: int = 60      # items shown in the main feed
TLDR_COUNT: int = 5            # items receiving an AI summary
TLDR_MIN_COMMENTS: int = 5     # require some discussion before summarizing

# Per-source recency cutoff. Reddit/HN/Lobsters move fast; RSS feeds like
# This Week in Rust post weekly so they need a longer window or they'd never
# appear in the dashboard. Items with no `published` timestamp are always
# included (we err on the side of showing content).
RECENCY_WINDOW_HOURS: dict[str, int] = {
    "reddit":     36,
    "hackernews": 48,
    "lobsters":   72,
    "rss":        168,   # 7 days — covers This Week in Rust + slow blogs
}
RECENCY_DEFAULT_HOURS: int = 48

# Source weights when ranking the unified feed. Tweak to bias the dashboard.
SOURCE_WEIGHTS: dict[str, float] = {
    "reddit": 1.0,
    "hackernews": 1.1,
    "lobsters": 1.05,
    "rss": 0.85,
}

# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
# Pick a model that still has free-tier quota for your project.  As of 2026
# `gemini-2.0-flash` was migrated off the free tier; `gemini-2.5-flash` is the
# current free-tier Flash model.  Run the model-list snippet in doc 05 if you
# need to switch to a newer model later.
GEMINI_MODEL: str = "gemini-2.5-flash"
GEMINI_MAX_INPUT_CHARS: int = 8000  # truncate huge selftexts before prompting
