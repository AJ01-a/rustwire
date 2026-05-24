"""Fetch top posts from each configured subreddit, tagged with its category."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .. import categorizer, config
from ..utils import ResponseTooLargeError, normalize_item, parse_epoch, safe_get

logger = logging.getLogger("rustwire.reddit")


def _fetch_subreddit(session: requests.Session, sub: str, category: str) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{sub}/top.json"
    params = {"t": config.REDDIT_TIME_WINDOW, "limit": config.REDDIT_FETCH_PER_SUB}
    try:
        resp = safe_get(session, url, params=params)
        resp.raise_for_status()
    except (requests.RequestException, ResponseTooLargeError) as exc:
        logger.warning("Reddit fetch failed for r/%s: %s", sub, exc)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("Reddit returned non-JSON for r/%s: %s", sub, exc)
        return []

    children = payload.get("data", {}).get("children", [])
    items: list[dict[str, Any]] = []
    for child in children:
        d = child.get("data") or {}
        if d.get("stickied") or d.get("over_18"):
            continue
        title = d.get("title") or ""
        permalink = d.get("permalink") or ""
        external_url = d.get("url_overridden_by_dest") or d.get("url") or ""
        discuss_url = f"https://www.reddit.com{permalink}" if permalink else external_url
        if d.get("is_self"):
            external_url = discuss_url
        items.append(
            normalize_item(
                source="reddit",
                subsource=f"r/{sub}",
                category=categorizer.coerce(category),
                title=title,
                url=external_url or discuss_url,
                discuss_url=discuss_url,
                score=d.get("score"),
                comments=d.get("num_comments"),
                author=d.get("author"),
                published=parse_epoch(d.get("created_utc")),
                summary=d.get("selftext") or "",
            )
        )
    logger.info("Reddit r/%s [%s]: %d items", sub, category, len(items))
    return items


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sub, category in config.REDDIT_SUBS.items():
        out.extend(_fetch_subreddit(session, sub, category))
    return out
