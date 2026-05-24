"""Fetch latest stories from each configured Lobsters tag, tagged with its category."""

from __future__ import annotations

import logging
from typing import Any

import requests
from dateutil import parser as date_parser

from .. import categorizer, config
from ..utils import ResponseTooLargeError, normalize_item, safe_get

logger = logging.getLogger("rustwire.lobsters")


def _fetch_tag(session: requests.Session, tag: str, category: str) -> list[dict[str, Any]]:
    url = f"https://lobste.rs/t/{tag}.json"
    try:
        resp = safe_get(session, url)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ResponseTooLargeError, ValueError) as exc:
        logger.warning("Lobsters fetch failed for /t/%s: %s", tag, exc)
        return []

    items: list[dict[str, Any]] = []
    for story in payload[:25] if isinstance(payload, list) else []:
        published = None
        if story.get("created_at"):
            try:
                published = date_parser.isoparse(story["created_at"])
            except (ValueError, TypeError):
                published = None
        external_url = story.get("url") or story.get("short_id_url") or ""
        discuss_url = story.get("short_id_url") or story.get("comments_url") or external_url
        submitter = story.get("submitter_user") or {}
        author = submitter.get("username") if isinstance(submitter, dict) else submitter
        items.append(
            normalize_item(
                source="lobsters",
                subsource=f"lobste.rs/{tag}",
                category=categorizer.coerce(category),
                title=story.get("title") or "",
                url=external_url or discuss_url,
                discuss_url=discuss_url,
                score=story.get("score"),
                comments=story.get("comment_count"),
                author=author,
                published=published,
                summary=story.get("description") or "",
            )
        )
    logger.info("Lobsters /t/%s [%s]: %d items", tag, category, len(items))
    return items


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tag, category in config.LOBSTERS_TAGS.items():
        out.extend(_fetch_tag(session, tag, category))
    return out
