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


# Defense-in-depth: cap every upstream response so a malicious / misconfigured
# feed can't OOM the Actions runner.  RSS and Reddit JSON for the sources we
# use are all comfortably under 1 MB; 5 MB is generous.
MAX_RESPONSE_BYTES: int = 5 * 1024 * 1024


class ResponseTooLargeError(Exception):
    """Raised when a remote response exceeds MAX_RESPONSE_BYTES."""


def safe_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """``session.get`` with a hard cap on response body size.

    Streams the body in chunks and aborts as soon as we see more than
    ``MAX_RESPONSE_BYTES``.  Returns a response object whose ``.content``
    is preloaded so downstream ``.json()`` / ``.text`` keeps working.
    """
    kwargs.setdefault("timeout", config.REQUEST_TIMEOUT)
    kwargs["stream"] = True
    resp = session.get(url, **kwargs)
    # Cheap early reject if the server advertises an oversized body.
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
        resp.close()
        raise ResponseTooLargeError(
            f"{url}: Content-Length {declared} > cap {MAX_RESPONSE_BYTES}"
        )
    body = bytearray()
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            resp.close()
            raise ResponseTooLargeError(
                f"{url}: body exceeded cap {MAX_RESPONSE_BYTES} mid-stream"
            )
    resp._content = bytes(body)          # noqa: SLF001 — populate so .json() works
    resp._content_consumed = True        # noqa: SLF001
    return resp


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
    category: str,
) -> dict[str, Any]:
    """Produce the canonical dict shape the rest of the pipeline expects.

    ``category`` is required: source fetchers must classify their items
    before handing them upstream.  Use ``categorizer.coerce`` to snap a
    suspect value back into the known set.
    """
    return {
        "source": source,
        "subsource": subsource,
        "category": category,
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
