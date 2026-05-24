"""Fetch the latest stories tagged ``rust`` on Lobsters."""

from __future__ import annotations

import logging
from typing import Any

import requests
from dateutil import parser as date_parser

from .. import config
from ..utils import normalize_item

logger = logging.getLogger("rustwire.lobsters")


def fetch(session: requests.Session) -> list[dict[str, Any]]:
    try:
        resp = session.get(config.LOBSTERS_TAG_URL, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Lobsters fetch failed: %s", exc)
        return []

    items: list[dict[str, Any]] = []
    for story in payload[:30] if isinstance(payload, list) else []:
        published = None
        if story.get("created_at"):
            try:
                published = date_parser.isoparse(story["created_at"])
            except (ValueError, TypeError):
                published = None
        external_url = story.get("url") or story.get("short_id_url") or ""
        discuss_url = story.get("short_id_url") or story.get("comments_url") or external_url
        author = (story.get("submitter_user") or {}).get("username")
        if isinstance(story.get("submitter_user"), str):
            author = story.get("submitter_user")
        items.append(
            normalize_item(
                source="lobsters",
                subsource="lobste.rs",
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
    logger.info("Lobsters: %d items", len(items))
    return items
