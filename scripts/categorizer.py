"""Assign a category to every ingested item.

Reddit / Lobsters / RSS items already know their category from config.
Hacker News items are classified by title-keyword scan, falling back to
the default category.
"""

from __future__ import annotations

from . import config


def for_hn_title(title: str) -> str:
    """Return the category id for a HN story based on its title."""
    if not title:
        return config.DEFAULT_CATEGORY
    t = f" {title.lower()} "
    for category_id, keywords in config.HN_CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in t:
                return category_id
    return config.DEFAULT_CATEGORY


def coerce(category: str | None) -> str:
    """Snap an unknown / missing category to a known one."""
    if category in config.CATEGORY_IDS:
        return category  # type: ignore[return-value]
    return config.DEFAULT_CATEGORY
