"""Orchestrator for the TechPulse ingestion pipeline.

Usage (from project root):
    python -m scripts.main

Pipeline stages:
  1. Pull items from every configured source (Reddit, RSS, HN, Lobsters).
  2. De-duplicate by canonical URL (highest score wins).
  3. Filter by per-source recency window.
  4. Rank within each category (HN-style age decay).
  5. Send the top item from every category to the AI summarizer.
  6. Write data/feed.json atomically.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from . import config, summarizer
from .sources import hackernews, lobsters, reddit, rss
from .utils import Timer, build_session, iso, now_utc

logger = logging.getLogger("rustwire")

# Public fields that go into feed.json on each item.
_OUT_FIELDS_DISCUSSION: tuple[str, ...] = (
    "source", "subsource", "category", "title", "url", "discuss_url",
    "score", "comments", "author", "published",
)
_OUT_FIELDS_TLDR: tuple[str, ...] = _OUT_FIELDS_DISCUSSION + ("bullets",)


def _canonical_url(url: str) -> str:
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


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_recent(item: dict[str, Any]) -> bool:
    dt = _parse_iso(item.get("published"))
    if dt is None:
        return True
    hours = config.RECENCY_WINDOW_HOURS.get(item["source"], config.RECENCY_DEFAULT_HOURS)
    return (now_utc() - dt) <= timedelta(hours=hours)


def _rank(item: dict[str, Any]) -> float:
    score = float(item.get("score") or 0)
    comments = float(item.get("comments") or 0)
    weight = config.SOURCE_WEIGHTS.get(item["source"], 1.0)

    age_hours = 1.0
    dt = _parse_iso(item.get("published"))
    if dt is not None:
        age_hours = max(1.0, (now_utc() - dt).total_seconds() / 3600.0)

    engagement = math.log1p(score) + 0.6 * math.log1p(comments)
    return (engagement * weight) / math.pow(age_hours + 2.0, 0.8)


def _group_by_category(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in config.CATEGORIES}
    for item in items:
        buckets.setdefault(item.get("category") or config.DEFAULT_CATEGORY, []).append(item)
    return buckets


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


def _project(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: item.get(f) for f in fields}


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
                all_items.extend(fn(session))
            except Exception as exc:  # noqa: BLE001 — one source failing shouldn't kill the run
                logger.exception("Source %s crashed: %s", name, exc)

    logger.info("Total raw items: %d", len(all_items))
    deduped = _deduplicate(all_items)
    logger.info("After dedupe: %d", len(deduped))
    recent = [i for i in deduped if _is_recent(i)]
    logger.info("After recency filter: %d", len(recent))

    # Per-category ranking + truncation
    by_cat = _group_by_category(recent)
    ranked_by_cat: dict[str, list[dict[str, Any]]] = {}
    for cat_id, bucket in by_cat.items():
        ranked = sorted(bucket, key=_rank, reverse=True)
        ranked_by_cat[cat_id] = ranked[: config.MAX_PER_CATEGORY]
        logger.info("Category %s: %d items (kept %d)",
                    cat_id, len(bucket), len(ranked_by_cat[cat_id]))

    # TL;DR candidates: top-N per category
    tldr_input: list[dict[str, Any]] = []
    for cat in config.CATEGORIES:
        tldr_input.extend(ranked_by_cat.get(cat["id"], [])[: config.TLDR_PER_CATEGORY])

    with Timer("summarize"):
        tldr_items = summarizer.summarize(tldr_input)

    # Build output
    discussions: list[dict[str, Any]] = []
    for cat in config.CATEGORIES:
        for item in ranked_by_cat.get(cat["id"], []):
            discussions.append(_project(item, _OUT_FIELDS_DISCUSSION))

    payload = {
        "updated_at": iso(now_utc()),
        "generator": "techpulse-pipeline/1.0",
        "niche": "Tech professionals",
        "categories": config.CATEGORIES,
        "tldr": [_project(i, _OUT_FIELDS_TLDR) for i in tldr_items],
        "discussions": discussions,
    }

    _atomic_write_json(config.FEED_PATH, payload)
    logger.info("Wrote %s — %d tldr / %d discussions",
                config.FEED_PATH, len(payload["tldr"]), len(payload["discussions"]))
    return 0


if __name__ == "__main__":
    sys.exit(run())
