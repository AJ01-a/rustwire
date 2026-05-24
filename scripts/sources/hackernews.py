"""Fetch high-engagement HN stories and categorize each by title keywords."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .. import categorizer, config
from ..utils import ResponseTooLargeError, normalize_item, parse_epoch, safe_get

logger = logging.getLogger("rustwire.hn")


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    cutoff = int(time.time()) - 60 * 60 * config.HN_HOURS_BACK
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff},points>={config.HN_MIN_POINTS}",
        "hitsPerPage": 50,
    }
    try:
        resp = safe_get(session, config.HN_SEARCH_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ResponseTooLargeError, ValueError) as exc:
        logger.warning("HN fetch failed: %s", exc)
        return []

    hits = payload.get("hits", [])
    items: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}
    dropped = 0
    for hit in hits:
        title = hit.get("title") or hit.get("story_title") or ""
        if not title:
            continue
        category = categorizer.for_hn_title(title)
        if category is None:
            # No keyword matched — drop rather than dump into a default bucket
            # (kept "Toxic chemical leak..." out of Engineering).
            dropped += 1
            continue
        story_id = hit.get("objectID")
        external_url = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        discuss_url = f"https://news.ycombinator.com/item?id={story_id}"
        bucket_counts[category] = bucket_counts.get(category, 0) + 1
        items.append(
            normalize_item(
                source="hackernews",
                subsource="news.ycombinator.com",
                category=category,
                title=title,
                url=external_url,
                discuss_url=discuss_url,
                score=hit.get("points"),
                comments=hit.get("num_comments"),
                author=hit.get("author"),
                published=parse_epoch(hit.get("created_at_i")),
                summary=hit.get("story_text") or "",
            )
        )
    logger.info("HN: %d items kept, %d dropped (uncategorized) — %s",
                len(items), dropped, bucket_counts)
    return items
