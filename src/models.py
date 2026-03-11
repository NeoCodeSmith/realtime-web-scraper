"""
NeoSignal Article Model v4.0

Defines the canonical Article data structure used throughout the pipeline.
TypedDict is used for JSON-serialisable transport; the dataclass wraps it
with validation and factory helpers.

Design decisions:
  - TypedDict for JSON compat (dict subclass, zero serialisation overhead)
  - Separate validated factory avoids silent default propagation
  - All fields are explicitly typed; no implicit Any
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional, TypedDict


# ── Wire format (JSON-serialisable) ───────────────────────────────────────────

class Article(TypedDict):
    """
    Canonical article record.

    Fields
    ──────
    id               : 12-char hex fingerprint of the normalised title
    title            : Article headline (original, unmodified)
    url              : Canonical URL (HN fallback if no external URL)
    summary          : First 280 chars of body text, HTML-stripped
    source           : Primary source display name (e.g. "TechCrunch AI")
    source_type      : "media" | "community"
    score            : HackerNews points (0 for non-HN sources)
    date             : ISO date of scrape (YYYY-MM-DD)
    scraped_at       : Full ISO-8601 UTC timestamp of scrape
    authenticity_score : Float 0.0–1.0; set by deduplicate()
    source_count     : Number of distinct sources covering this story
    all_sources      : List of all source names covering this story
    """

    id:                  str
    title:               str
    url:                 str
    summary:             str
    source:              str
    source_type:         str
    score:               int
    date:                str
    scraped_at:          str
    # Set by deduplicate() — optional until scoring phase
    authenticity_score:  float
    source_count:        int
    all_sources:         list


# ── Validation ────────────────────────────────────────────────────────────────

_VALID_SOURCE_TYPES = frozenset({"media", "community"})


class ArticleValidationError(ValueError):
    """Raised when an article dict fails validation."""


def make_article(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    title:       str,
    url:         str,
    source:      str,
    source_type: str,
    summary:     str  = "",
    score:       int  = 0,
    date:        Optional[str] = None,
    scraped_at:  Optional[str] = None,
) -> Article:
    """
    Validated Article factory.

    Raises ArticleValidationError on constraint violations.
    Always sets 'id', 'date', and 'scraped_at' deterministically.
    """
    title       = title.strip()
    url         = url.strip()
    source      = source.strip()
    source_type = source_type.strip().lower()

    if not title:
        raise ArticleValidationError("title must be non-empty")
    if not url:
        raise ArticleValidationError("url must be non-empty")
    if not source:
        raise ArticleValidationError("source must be non-empty")
    if source_type not in _VALID_SOURCE_TYPES:
        raise ArticleValidationError(
            f"source_type must be one of {_VALID_SOURCE_TYPES}, got {source_type!r}"
        )
    if score < 0:
        raise ArticleValidationError(f"score must be >= 0, got {score}")

    now = datetime.now(timezone.utc)
    return Article(
        id              = _article_id(title),
        title           = title,
        url             = url,
        summary         = summary[:500] if summary else "",   # hard cap at 500
        source          = source,
        source_type     = source_type,
        score           = score,
        date            = date or now.strftime("%Y-%m-%d"),
        scraped_at      = scraped_at or now.isoformat(),
        authenticity_score = 0.0,
        source_count    = 1,
        all_sources     = [source],
    )


def from_dict(data: dict) -> Article:
    """
    Coerce a raw dict (e.g. from JSON) into a validated Article.
    Fills missing optional fields with safe defaults.
    Raises ArticleValidationError on missing required fields.
    """
    required = ("title", "url", "source", "source_type")
    for field in required:
        if not data.get(field):
            raise ArticleValidationError(f"Missing required field: {field!r}")

    return make_article(
        title       = data["title"],
        url         = data["url"],
        source      = data["source"],
        source_type = data["source_type"],
        summary     = data.get("summary", ""),
        score       = int(data.get("score", 0)),
        date        = data.get("date"),
        scraped_at  = data.get("scraped_at"),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _article_id(title: str) -> str:
    """12-char hex fingerprint from normalised title."""
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]


def tier_label(authenticity_score: float, tier_verified: float, tier_confirmed: float) -> str:
    """Return human-readable tier name from score and configured thresholds."""
    if authenticity_score >= tier_verified:
        return "VERIFIED"
    if authenticity_score >= tier_confirmed:
        return "CONFIRMED"
    return "EMERGING"


__all__ = [
    "Article",
    "ArticleValidationError",
    "make_article",
    "from_dict",
    "tier_label",
    "_article_id",
]
