"""Assign a category to every ingested item.

Reddit / Lobsters / RSS items already know their category from config.
Hacker News items are classified by title keyword scan with word-boundary
matching; titles that don't match any category return ``None`` so callers
can drop them instead of polluting a default bucket.
"""

from __future__ import annotations

import re

from . import config


def for_hn_title(title: str) -> str | None:
    """Return the category id for a HN story based on its title.

    Returns ``None`` if no keyword matches. The HN source drops such items
    rather than dumping them into a default bucket, which is what produced
    "Toxic chemical leak..." showing up under Engineering.

    Matching is anchored at word boundaries (``(?:^|\\W)<keyword>``) so a
    short keyword like ``rce`` no longer matches inside ``source``.
    """
    if not title:
        return None
    text = title.lower()
    for category_id, keywords in config.HN_CATEGORY_KEYWORDS:
        for kw in keywords:
            pattern = r"(?:^|\W)" + re.escape(kw.lower().strip())
            if re.search(pattern, text):
                return category_id
    return None


def coerce(category: str | None) -> str:
    """Snap an unknown / missing category to the default known one."""
    if category in config.CATEGORY_IDS:
        return category  # type: ignore[return-value]
    return config.DEFAULT_CATEGORY
