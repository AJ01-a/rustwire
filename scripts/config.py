"""Configuration for the TechPulse ingestion pipeline.

Every niche-specific value lives here: the five categories, the sources that
feed each one, fetch limits, and ranking weights. Retargeting the dashboard
is a config-only change.
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
# Categories — the spine of the dashboard
# ---------------------------------------------------------------------------
# `id` is the stable slug used in feed.json and CSS classes.  `label` and
# `accent` drive the frontend.  Order here is the display order.
CATEGORIES: list[dict[str, str]] = [
    {"id": "ai",          "label": "AI & ML",         "accent": "#a06bff"},
    {"id": "engineering", "label": "Engineering",     "accent": "#00d9ff"},
    {"id": "security",    "label": "Security",        "accent": "#ff3b6b"},
    {"id": "devops",      "label": "Cloud & DevOps",  "accent": "#00e6a8"},
    {"id": "industry",    "label": "Industry",        "accent": "#ffb648"},
]
CATEGORY_IDS: set[str] = {c["id"] for c in CATEGORIES}
DEFAULT_CATEGORY: str = "engineering"

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
USER_AGENT: str = "TechPulse/1.0 (+https://github.com/) tech-intel aggregator"
REQUEST_TIMEOUT: int = 20
MAX_RETRIES: int = 3

# ---------------------------------------------------------------------------
# Reddit — subreddit -> category
# ---------------------------------------------------------------------------
REDDIT_SUBS: dict[str, str] = {
    # AI
    "MachineLearning": "ai",
    "LocalLLaMA":      "ai",
    # Engineering
    "programming":     "engineering",
    "ExperiencedDevs": "engineering",
    "rust":            "engineering",
    # Security
    "netsec":          "security",
    "cybersecurity":   "security",
    # Cloud & DevOps
    "devops":          "devops",
    "kubernetes":      "devops",
    # Industry
    "technology":      "industry",
}
REDDIT_FETCH_PER_SUB: int = 15
REDDIT_TIME_WINDOW: str = "day"

# ---------------------------------------------------------------------------
# Lobsters — tag -> category
# ---------------------------------------------------------------------------
LOBSTERS_TAGS: dict[str, str] = {
    "ai":          "ai",
    "programming": "engineering",
    "security":    "security",
    "devops":      "devops",
}

# ---------------------------------------------------------------------------
# RSS / Atom feeds — explicit category on each
# ---------------------------------------------------------------------------
RSS_FEEDS: list[dict[str, str]] = [
    # AI
    {"name": "Simon Willison",   "url": "https://simonwillison.net/atom.xml",
     "subsource": "simonwillison.net", "category": "ai"},
    {"name": "Hugging Face",     "url": "https://huggingface.co/blog/feed.xml",
     "subsource": "huggingface.co", "category": "ai"},
    # Engineering
    {"name": "GitHub Blog",      "url": "https://github.blog/feed/",
     "subsource": "github.blog", "category": "engineering"},
    {"name": "Stack Overflow Blog", "url": "https://stackoverflow.blog/feed/",
     "subsource": "stackoverflow.blog", "category": "engineering"},
    # Security
    {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/",
     "subsource": "krebsonsecurity.com", "category": "security"},
    {"name": "The Hacker News",   "url": "https://feeds.feedburner.com/TheHackersNews",
     "subsource": "thehackernews.com", "category": "security"},
    # Cloud & DevOps
    {"name": "AWS What's New",    "url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
     "subsource": "aws.amazon.com", "category": "devops"},
    {"name": "Kubernetes Blog",   "url": "https://kubernetes.io/feed.xml",
     "subsource": "kubernetes.io", "category": "devops"},
    # Industry
    {"name": "Ars Technica",      "url": "https://feeds.arstechnica.com/arstechnica/index/",
     "subsource": "arstechnica.com", "category": "industry"},
    {"name": "The Register",      "url": "https://www.theregister.com/headlines.atom",
     "subsource": "theregister.com", "category": "industry"},
]

# ---------------------------------------------------------------------------
# Hacker News — broad fetch, categorized by title keywords
# ---------------------------------------------------------------------------
HN_SEARCH_URL: str = "https://hn.algolia.com/api/v1/search"
HN_MIN_POINTS: int = 100        # tight threshold; HN volume is huge
HN_HOURS_BACK: int = 48

# Keyword -> category mappings.  First match wins; falls back to DEFAULT_CATEGORY.
HN_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("ai",       ["llm", "gpt", "claude", "gemini", "neural", "deep learning",
                  "machine learning", "ai model", "openai", "anthropic", "hugging face"]),
    ("security", ["cve-", "vulnerability", "exploit", "ransomware", "0day",
                  "0-day", "breach", "zero-day", "rce", "malware", "phishing"]),
    ("devops",   ["kubernetes", "k8s ", "terraform", "docker", "aws ", " aws",
                  "azure ", "gcp ", "cloudflare", "serverless", "observability"]),
    ("industry", ["layoffs", "ipo", "acquires", "acquisition", "antitrust",
                  "lawsuit", "merger", "funding round", "valuation"]),
    # engineering is the default fallback
]

# ---------------------------------------------------------------------------
# Ranking / output limits
# ---------------------------------------------------------------------------
MAX_PER_CATEGORY: int = 12      # items shown in each category section
TLDR_PER_CATEGORY: int = 1      # AI-summarized hero items per category

# Per-source recency cutoff. Reddit/HN move fast; RSS feeds (Krebs, AWS,
# K8s) are slower and need a longer window or they never appear.
RECENCY_WINDOW_HOURS: dict[str, int] = {
    "reddit":     48,
    "hackernews": 72,
    "lobsters":   96,
    "rss":        168,
}
RECENCY_DEFAULT_HOURS: int = 72

SOURCE_WEIGHTS: dict[str, float] = {
    "reddit":     1.0,
    "hackernews": 1.15,
    "lobsters":   1.05,
    "rss":        0.9,
}

# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = "gemini-2.5-flash"
GEMINI_MAX_INPUT_CHARS: int = 8000
