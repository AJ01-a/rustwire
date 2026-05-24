"""Fetch high-engagement HN stories and categorize each by title keywords."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .. import categorizer, config
from ..utils import normalize_item, parse_epoch

logger = logging.getLogger("rustwire.hn")


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    cutoff = int(time.time()) - 60 * 60 * config.HN_HOURS_BACK
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff},points>={config.HN_MIN_POINTS}",
        "hitsPerPage": 50,
    }
    try:
        resp = session.get(config.HN_SEARCH_URL, params=params, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("HN fetch failed: %s", exc)
        return []

    hits = payload.get("hits", [])
    items: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}
    for hit in hits:
        title = hit.get("title") or hit.get("story_title") or ""
        if not title:
            continue
        story_id = hit.get("objectID")
        external_url = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        discuss_url = f"https://news.ycombinator.com/item?id={story_id}"
        category = categorizer.for_hn_title(title)
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
    logger.info("HN: %d items (%s)", len(items), bucket_counts)
    return items
