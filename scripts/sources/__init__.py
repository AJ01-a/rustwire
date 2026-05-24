"""Source-specific fetchers. Each module exposes ``fetch(session) -> list[dict]``."""

from . import hackernews, lobsters, reddit, rss

__all__ = ["reddit", "rss", "hackernews", "lobsters"]
