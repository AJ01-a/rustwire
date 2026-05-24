"""Orchestrator for the Rustwire ingestion pipeline.

Usage (from project root):
    python -m scripts.main

The script:
  1. Pulls items from every configured source (Reddit, RSS, HN, Lobsters).
  2. De-duplicates by canonical URL.
  3. Filters out anything older than RECENT_WINDOW_HOURS.
  4. Ranks the merged list.
  5. Sends the top TLDR_COUNT items to the summarizer.
  6. Writes data/feed.json atomically.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import tempfile
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from . import config, summarizer
from .sources import hackernews, lobsters, reddit, rss
from .utils import Timer, build_session, iso, now_utc

logger = logging.getLogger("rustwire")


def _canonical_url(url: str) -> str:
    """Strip query/fragment so the same story isn't counted twice across sources."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{path}".lower()


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the highest-scoring item for each canonical URL."""
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _canonical_url(item.get("url") or "") or item.get("discuss_url") or item["title"]
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            continue
        if (item.get("score") or 0) > (existing.get("score") or 0):
            by_key[key] = item
    return list(by_key.values())


def _is_recent(item: dict[str, Any]) -> bool:
    pub = item.get("published")
    if not pub:
        return True  # err on the side of inclusion
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
    except ValueError:
        return True
    hours = config.RECENCY_WINDOW_HOURS.get(item["source"], config.RECENCY_DEFAULT_HOURS)
    return (now_utc() - dt) <= timedelta(hours=hours)


def _rank(item: dict[str, Any]) -> float:
    """Hacker-News-style decay so fresh items float to the top."""
    score = float(item.get("score") or 0)
    comments = float(item.get("comments") or 0)
    weight = config.SOURCE_WEIGHTS.get(item["source"], 1.0)

    age_hours = 1.0
    if item.get("published"):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(item["published"].replace("Z", "+00:00"))
            age_hours = max(1.0, (now_utc() - dt).total_seconds() / 3600.0)
        except ValueError:
            pass

    # log1p so a couple of strong comments aren't dwarfed by a giant score
    engagement = math.log1p(score) + 0.6 * math.log1p(comments)
    return (engagement * weight) / math.pow(age_hours + 2.0, 0.8)


def _atomic_write_json(path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=".feed-",
        suffix=".json.tmp",
    ) as tmp:
        json.dump(payload, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    session = build_session()
    all_items: list[dict[str, Any]] = []

    fetchers = [
        ("reddit", reddit.fetch),
        ("rss", rss.fetch),
        ("hackernews", hackernews.fetch),
        ("lobsters", lobsters.fetch),
    ]

    for name, fn in fetchers:
        with Timer(f"fetch:{name}"):
            try:
                items = fn(session)
                all_items.extend(items)
            except Exception as exc:  # noqa: BLE001 — one source failing shouldn't kill the run
                logger.exception("Source %s crashed: %s", name, exc)

    logger.info("Total raw items: %d", len(all_items))
    deduped = _deduplicate(all_items)
    logger.info("After dedupe: %d", len(deduped))
    recent = [i for i in deduped if _is_recent(i)]
    logger.info("After recency filter: %d", len(recent))

    ranked = sorted(recent, key=_rank, reverse=True)
    discussions = ranked[: config.MAX_DISCUSSIONS]

    with Timer("summarize"):
        tldr = summarizer.summarize(discussions)

    payload = {
        "updated_at": iso(now_utc()),
        "generator": "rustwire-pipeline/1.0",
        "niche": "Rust systems programming",
        "tldr": [
            {
                "source": i["source"],
                "subsource": i.get("subsource"),
                "title": i["title"],
                "url": i["url"],
                "discuss_url": i.get("discuss_url"),
                "score": i.get("score"),
                "comments": i.get("comments"),
                "author": i.get("author"),
                "bullets": i["bullets"],
            }
            for i in tldr
        ],
        "discussions": [
            {
                "source": i["source"],
                "subsource": i.get("subsource"),
                "title": i["title"],
                "url": i["url"],
                "discuss_url": i.get("discuss_url"),
                "score": i.get("score"),
                "comments": i.get("comments"),
                "author": i.get("author"),
                "published": i.get("published"),
            }
            for i in discussions
        ],
    }

    _atomic_write_json(config.FEED_PATH, payload)
    logger.info("Wrote %s", config.FEED_PATH)
    logger.info(
        "Summary: %d discussions, %d tldr cards", len(payload["discussions"]), len(payload["tldr"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
