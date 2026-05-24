"""Generate 3-bullet TL;DRs for the top discussions using Google Gemini.

The pipeline runs without a key — items simply pass through with a heuristic
fallback summary — so contributors can develop locally before wiring secrets.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from . import config
from .utils import strip_html, truncate

logger = logging.getLogger("rustwire.summarizer")

PROMPT_TEMPLATE = """You are a senior Rust systems engineer writing a 3-bullet
TL;DR for fellow experts. Produce exactly THREE short bullet points (max 22
words each) that capture the most technically substantive takeaways from the
material below. Avoid restating the title. No marketing fluff. If the content
has runnable code, mention the concrete pattern. If it's a release, name the
most consequential change. If the body content is empty or just a URL (a link
post), infer what the linked work is from the title and metadata and infer
likely technical content; never write filler like "open the link".
Respond with ONLY a JSON array of three strings — no preamble, no markdown
fences.

TITLE: {title}
SOURCE: {source} ({subsource})
COMMENTS: {comments}
SCORE: {score}

CONTENT:
{content}
"""


def _heuristic_bullets(item: dict[str, Any]) -> list[str]:
    """Fallback summarizer used when Gemini is unavailable or fails.

    Tries (in order): sentences from the body, then the title, then a metadata
    triplet. Avoids the "open the original" filler that earlier versions
    produced for link-only posts.
    """
    raw = strip_html(item.get("summary") or "")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]

    if len(sentences) >= 3:
        return [truncate(s, 180) for s in sentences[:3]]

    bullets = [truncate(s, 180) for s in sentences]

    # Pad with informative metadata-derived lines (not filler).
    title = (item.get("title") or "").strip()
    subsource = item.get("subsource") or item.get("source") or "source"
    score = item.get("score")
    comments = item.get("comments")
    author = item.get("author")

    pads: list[str] = []
    if title and (not bullets or title.lower() not in bullets[0].lower()):
        pads.append(truncate(title, 180))
    engagement: list[str] = []
    if isinstance(score, int):
        engagement.append(f"{score} points")
    if isinstance(comments, int):
        engagement.append(f"{comments} comments")
    if engagement:
        pads.append(f"Trending on {subsource} — {', '.join(engagement)}.")
    if author:
        pads.append(f"Submitted by {author} on {subsource}.")
    pads.append(f"Posted via {subsource}; full context at the source link.")

    for pad in pads:
        if len(bullets) >= 3:
            break
        if pad and pad not in bullets:
            bullets.append(pad)

    while len(bullets) < 3:
        bullets.append("(no further detail available)")
    return bullets


def _extract_json_array(text: str) -> list[str] | None:
    """Tolerate light formatting drift from the model."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip fenced code blocks (```json ... ``` or ``` ... ```)
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # Find first '[' .. matching ']'
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        arr = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(arr, list):
        return None
    bullets = [str(b).strip() for b in arr if str(b).strip()]
    return bullets or None


def _call_gemini(client, item: dict[str, Any]) -> list[str] | None:
    content = strip_html(item.get("summary") or "")
    if not content:
        content = item.get("title") or ""
    content = truncate(content, config.GEMINI_MAX_INPUT_CHARS)

    prompt = PROMPT_TEMPLATE.format(
        title=item.get("title") or "",
        source=item.get("source") or "",
        subsource=item.get("subsource") or "",
        comments=item.get("comments") or 0,
        score=item.get("score") or 0,
        content=content,
    )

    try:
        response = client.generate_content(prompt)
    except Exception as exc:  # noqa: BLE001 - SDK raises a variety of types
        logger.warning("Gemini call failed for %r: %s", item.get("title"), exc)
        return None

    text = getattr(response, "text", "") or ""
    bullets = _extract_json_array(text)
    if not bullets:
        logger.warning("Could not parse Gemini output for %r: %r", item.get("title"), text[:200])
        return None
    # Normalize to exactly 3 bullets
    bullets = bullets[:3]
    while len(bullets) < 3:
        bullets.append("(no additional detail)")
    return [truncate(b, 240) for b in bullets]


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set — using heuristic summaries")
        return None
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        logger.warning("google-generativeai not installed — using heuristic summaries")
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(config.GEMINI_MODEL)


def summarize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return up to TLDR_COUNT items enriched with a ``bullets`` field."""
    candidates = [i for i in items if (i.get("comments") or 0) >= config.TLDR_MIN_COMMENTS]
    candidates = candidates[: config.TLDR_COUNT] or items[: config.TLDR_COUNT]

    client = _get_client()
    summarized: list[dict[str, Any]] = []
    for item in candidates:
        bullets: list[str] | None = None
        if client is not None:
            bullets = _call_gemini(client, item)
        if bullets is None:
            bullets = _heuristic_bullets(item)
        summarized.append({**item, "bullets": bullets})
    logger.info("Summarized %d items (gemini=%s)", len(summarized), client is not None)
    return summarized
