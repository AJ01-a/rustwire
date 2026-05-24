"""Fetch HN stories matching the niche keyword via the Algolia search API."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .. import config
from ..utils import normalize_item, parse_epoch

logger = logging.getLogger("rustwire.hn")


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    cutoff = int(time.time()) - 60 * 60 * 24 * 2  # last 48h
    params = {
        "query": config.HN_QUERY,
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff},points>={config.HN_MIN_POINTS}",
        "hitsPerPage": 30,
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
    for hit in hits:
        title = hit.get("title") or hit.get("story_title") or ""
        if not _is_rust_relevant(title):
            continue
        story_id = hit.get("objectID")
        external_url = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        discuss_url = f"https://news.ycombinator.com/item?id={story_id}"
        items.append(
            normalize_item(
                source="hackernews",
                subsource="news.ycombinator.com",
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
    logger.info("HN: %d items", len(items))
    return items


def _is_rust_relevant(title: str) -> bool:
    """Coarse filter: 'rust' as a standalone token (not 'trust', 'crusty', etc.)."""
    if not title:
        return False
    tokens = [tok.strip(".,:;!?()[]{}\"'").lower() for tok in title.split()]
    return any(
        tok == "rust" or tok.startswith(("rust-", "rust:", "rust/"))
        for tok in tokens
    )
