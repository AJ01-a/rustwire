"""Generate 3-bullet TL;DRs for the top story in each category using Google Gemini.

The pipeline runs without a key — items pass through with a heuristic
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

PROMPT_TEMPLATE = """You are a senior technologist writing a 3-bullet TL;DR for
working professionals (engineers, security analysts, DevOps, AI practitioners,
industry watchers). Read the material below and produce exactly THREE short
bullet points (max 22 words each) capturing the most substantive takeaways for
someone in the "{category}" space. Avoid restating the title. No marketing
fluff. Name concrete technologies, vendors, CVEs, model versions, or numbers
when present. If the body is empty or just a URL (link post), infer likely
technical content from the title and metadata — never write filler like "open
the link". Respond with ONLY a JSON array of three strings — no preamble,
no markdown fences.

CATEGORY: {category}
TITLE: {title}
SOURCE: {source} ({subsource})
COMMENTS: {comments}
SCORE: {score}

CONTENT:
{content}
"""


def _heuristic_bullets(item: dict[str, Any]) -> list[str]:
    """Fallback summarizer used when Gemini is unavailable or fails."""
    raw = strip_html(item.get("summary") or "")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]

    if len(sentences) >= 3:
        return [truncate(s, 180) for s in sentences[:3]]

    bullets = [truncate(s, 180) for s in sentences]

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
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
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
    content = strip_html(item.get("summary") or "") or item.get("title") or ""
    content = truncate(content, config.GEMINI_MAX_INPUT_CHARS)

    prompt = PROMPT_TEMPLATE.format(
        category=item.get("category") or "engineering",
        title=item.get("title") or "",
        source=item.get("source") or "",
        subsource=item.get("subsource") or "",
        comments=item.get("comments") or 0,
        score=item.get("score") or 0,
        content=content,
    )

    try:
        response = client.generate_content(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini call failed for %r: %s", item.get("title"), exc)
        return None

    text = getattr(response, "text", "") or ""
    bullets = _extract_json_array(text)
    if not bullets:
        logger.warning("Could not parse Gemini output for %r: %r", item.get("title"), text[:200])
        return None
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
    """Return each item enriched with a ``bullets`` field.

    Callers (``main.py``) decide which items to summarize — typically the
    top item in each category.  We just process whatever we're handed.
    """
    client = _get_client()
    summarized: list[dict[str, Any]] = []
    for item in items:
        bullets: list[str] | None = None
        if client is not None:
            bullets = _call_gemini(client, item)
        if bullets is None:
            bullets = _heuristic_bullets(item)
        summarized.append({**item, "bullets": bullets})
    logger.info("Summarized %d items (gemini=%s)", len(summarized), client is not None)
    return summarized
