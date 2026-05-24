"""Shared utilities for the Rustwire ingestion pipeline."""

from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

logger = logging.getLogger("rustwire")


def build_session() -> requests.Session:
    """Return a requests.Session with retry + user-agent baked in."""
    session = requests.Session()
    retry = Retry(
        total=config.MAX_RETRIES,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": config.USER_AGENT})
    return session


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Render a datetime as ISO 8601 with a trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_epoch(seconds: int | float | None) -> datetime | None:
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    """Remove HTML tags, decode entities, and collapse whitespace.

    Uses ``html.unescape`` so hex/decimal numeric entities (``&#x2F;``,
    ``&#039;``) and named entities (``&hellip;``, ``&mdash;``) all decode,
    not just the small set Reddit/HN happen to emit most often.
    """
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def normalize_item(
    *,
    source: str,
    subsource: str,
    title: str,
    url: str,
    discuss_url: str | None,
    score: int | float | None,
    comments: int | None,
    author: str | None,
    published: datetime | None,
    summary: str = "",
) -> dict[str, Any]:
    """Produce the canonical dict shape the rest of the pipeline expects."""
    return {
        "source": source,
        "subsource": subsource,
        "title": (title or "").strip(),
        "url": url,
        "discuss_url": discuss_url or url,
        "score": int(score) if isinstance(score, (int, float)) else None,
        "comments": int(comments) if comments is not None else None,
        "author": author,
        "published": iso(published) if published else None,
        "summary": truncate(strip_html(summary), 1200),
    }


class Timer:
    """Tiny context-manager timer for log breadcrumbs."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.start = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        elapsed = time.perf_counter() - self.start
        logger.info("%s done in %.2fs", self.label, elapsed)
