"""Fetch entries from the configured RSS/Atom feeds, tagged with the feed's category."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests

from .. import categorizer, config
from ..utils import ResponseTooLargeError, normalize_item, safe_get, strip_html

logger = logging.getLogger("rustwire.rss")


def _struct_time_to_dt(st: time.struct_time | None) -> datetime | None:
    if st is None:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(st), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _fetch_feed(session: requests.Session, feed_cfg: dict[str, str]) -> list[dict[str, Any]]:
    url = feed_cfg["url"]
    try:
        resp = safe_get(session, url)
        resp.raise_for_status()
    except (requests.RequestException, ResponseTooLargeError) as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        logger.warning("RSS parse error for %s: %s", url, parsed.bozo_exception)
        return []

    category = categorizer.coerce(feed_cfg.get("category"))
    items: list[dict[str, Any]] = []
    for entry in parsed.entries[:20]:
        published = _struct_time_to_dt(
            getattr(entry, "published_parsed", None)
            or getattr(entry, "updated_parsed", None)
        )
        summary = ""
        if hasattr(entry, "summary"):
            summary = strip_html(entry.summary)
        elif hasattr(entry, "description"):
            summary = strip_html(entry.description)

        items.append(
            normalize_item(
                source="rss",
                subsource=feed_cfg["subsource"],
                category=category,
                title=getattr(entry, "title", "") or "",
                url=getattr(entry, "link", "") or "",
                discuss_url=getattr(entry, "link", "") or "",
                score=None,
                comments=None,
                author=getattr(entry, "author", None),
                published=published,
                summary=summary,
            )
        )
    logger.info("RSS %s [%s]: %d items", feed_cfg["name"], category, len(items))
    return items


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for feed_cfg in config.RSS_FEEDS:
        out.extend(_fetch_feed(session, feed_cfg))
    return out
