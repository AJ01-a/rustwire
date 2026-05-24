"""Fetch top posts from configured Rust subreddits via Reddit's public JSON API."""

from __future__ import annotations

import logging
from typing import Any

import requests

from .. import config
from ..utils import normalize_item, parse_epoch

logger = logging.getLogger("rustwire.reddit")


def _fetch_subreddit(session: requests.Session, sub: str) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{sub}/top.json"
    params = {"t": config.REDDIT_TIME_WINDOW, "limit": config.REDDIT_FETCH_PER_SUB}
    try:
        resp = session.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
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
        # For self-posts the link target is the discussion itself.
        if d.get("is_self"):
            external_url = discuss_url
        items.append(
            normalize_item(
                source="reddit",
                subsource=f"r/{sub}",
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
    logger.info("Reddit r/%s: %d items", sub, len(items))
    return items


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sub in config.REDDIT_SUBREDDITS:
        out.extend(_fetch_subreddit(session, sub))
    return out
