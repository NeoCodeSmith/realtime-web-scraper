"""
NeoSignal Multi-Source Scraper v4.0

Scrapes AI news from all configured sources, deduplicates cross-source
variants using title similarity, and scores each story's authenticity
based on how many independent sources corroborate it.

All tunable parameters (URLs, limits, thresholds, keywords) are loaded
from config/config.yaml — nothing is hardcoded in this file.

Sources configured in config.yaml:
  scraper.hn_endpoints     — HackerNews Firebase API
  scraper.reddit_subs      — Reddit public JSON API
  scraper.rss_sources      — RSS / Atom feeds

Security:
  - RSS feeds parsed with defusedxml (XXE-safe, replaces xml.etree)
  - HTTP requests use User-Agent from config (not hardcoded)
  - Retry with exponential backoff (configurable)
  - _safe_get() isolates all network errors per-source
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Optional

import defusedxml.ElementTree as ET
import requests

from src.config import cfg
from src.models import make_article

log = logging.getLogger(__name__)

# ── File paths ────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR     = os.path.join(BASE_DIR, "data")
NEWS_FILE    = os.path.join(DATA_DIR, "news_feed.json")
HISTORY_FILE = os.path.join(BASE_DIR, cfg.history.filename)


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _safe_get(url: str,
              headers: Optional[dict] = None,
              retries: Optional[int]  = None) -> Optional[requests.Response]:
    """
    GET with exponential backoff retry. Returns None on exhausted retries.

    Retries on: ConnectionError, Timeout, 429, 5xx.
    Does NOT retry on: 4xx (except 429).
    Never raises — all errors are logged and swallowed.
    """
    timeout     = cfg.scraper.request_timeout
    max_retries = retries if retries is not None else cfg.scraper.request_retries
    b_base      = cfg.scraper.request_backoff_base
    b_max       = cfg.scraper.request_backoff_max
    hdrs        = {"User-Agent": cfg.scraper.user_agent}
    if headers:
        hdrs.update(headers)

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, headers=hdrs)
            if resp.status_code in (429,) or resp.status_code >= 500:
                wait = min(b_base ** attempt, b_max)
                log.warning("HTTP %d [%s] — waiting %.1fs (attempt %d/%d)",
                            resp.status_code, url, wait, attempt + 1, max_retries + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            wait = min(b_base ** attempt, b_max)
            log.debug("Request failed [%s]: %s — retry in %.1fs", url, exc, wait)
            time.sleep(wait)
            last_exc = exc
        except requests.HTTPError:
            return None
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.debug("Unexpected error [%s]: %s", url, exc)
            return None

    log.warning("All %d attempts failed [%s] — last: %s", max_retries + 1, url, last_exc)
    return None


# ── Text utilities ────────────────────────────────────────────────────────────

def _is_ai(text: str) -> bool:
    """Return True if text contains at least one configured AI keyword."""
    lower = text.lower()
    return any(kw in lower for kw in cfg.keywords.ai_filter)


def _clean_html(raw: Optional[str]) -> str:
    """Strip HTML tags and decode entities."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_chars: Optional[int] = None) -> str:
    """Truncate to max_chars at word boundary, appending '...' if cut."""
    limit = max_chars if max_chars is not None else cfg.scraper.summary_max_chars
    text  = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def _similarity(a: str, b: str) -> float:
    """Case-normalised SequenceMatcher ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ── HackerNews ────────────────────────────────────────────────────────────────

def scrape_hackernews() -> list:
    """Scrape HN Show/Top/New with fallback chain. Captures body text field."""
    ep        = cfg.scraper.hn_endpoints
    endpoints = [ep.show, ep.top, ep.new]
    ids: list = []

    for endpoint in endpoints:
        resp = _safe_get(endpoint)
        if resp is not None:
            try:
                ids = resp.json()[:cfg.scraper.hn_limit]
                log.info("HN: %d IDs from %s", len(ids), endpoint.rsplit("/", maxsplit=1)[-1])
                break
            except (ValueError, KeyError):
                continue

    if not ids:
        log.warning("HN: all endpoints unreachable or returned invalid JSON")
        return []

    articles = []
    for sid in ids:
        resp = _safe_get(ep.item.format(sid), retries=1)
        if resp is None:
            continue
        try:
            d = resp.json()
        except ValueError:
            continue
        title = (d.get("title") or "").strip()
        if not title or not _is_ai(title):
            continue
        raw_text = _clean_html(d.get("text") or "")
        try:
            art = make_article(
                title       = title,
                url         = d.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                source      = "HackerNews",
                source_type = "community",
                summary     = _truncate(raw_text) if raw_text else "",
                score       = int(d.get("score") or 0),
            )
            articles.append(art)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.debug("HN item %s skipped: %s", sid, exc)

    log.info("HN: %d AI articles collected", len(articles))
    return articles


# ── Reddit ────────────────────────────────────────────────────────────────────

def scrape_reddit() -> list:
    """Scrape configured AI subreddits. Captures selftext for text posts."""
    subs     = cfg.scraper.reddit_subs
    min_self = cfg.scraper.selftext_min_chars
    articles = []

    for sub_entry in subs:
        sub_url  = sub_entry["url"]
        sub_name = sub_entry.get("name", sub_url.split("/r/")[1].split(".json")[0])

        resp = _safe_get(sub_url)
        if resp is None:
            log.warning("Reddit: %s unreachable", sub_name)
            continue
        try:
            posts = resp.json()["data"]["children"]
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("Reddit: %s parse error: %s", sub_name, exc)
            continue

        for post in posts:
            d = post.get("data", {})
            title = (d.get("title") or "").strip()
            if not title or not _is_ai(title):
                continue
            raw_self = _clean_html(d.get("selftext") or "")
            try:
                art = make_article(
                    title       = title,
                    url         = d.get("url") or f"https://reddit.com{d.get('permalink', '')}",
                    source      = f"Reddit {sub_name}",
                    source_type = "community",
                    summary     = _truncate(raw_self) if len(raw_self) >= min_self else "",
                    score       = int(d.get("score") or 0),
                )
                articles.append(art)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.debug("Reddit post in %s skipped: %s", sub_name, exc)

    log.info("Reddit: %d AI articles collected", len(articles))
    return articles


# ── RSS / Atom ────────────────────────────────────────────────────────────────

def _parse_rss(xml_text: str, source_name: str) -> list:
    """
    Parse RSS 2.0 and Atom feeds.
    Uses defusedxml — prevents XXE injection from malicious feeds.
    """
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("RSS parse error [%s]: %s", source_name, exc)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url   = (item.findtext("link")  or "").strip()
        if not title or not url or not _is_ai(title):
            continue
        raw_desc = (
            item.findtext("description")
            or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            or ""
        )
        try:
            articles.append(make_article(
                title       = title,
                url         = url,
                source      = source_name,
                source_type = "media",
                summary     = _truncate(_clean_html(raw_desc)),
            ))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.debug("RSS item [%s] skipped: %s", source_name, exc)

    for entry in root.findall(".//atom:entry", ns):
        title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
        link  = entry.find("atom:link", ns)
        url   = (link.get("href") if link is not None else "") or ""
        if not title or not url or not _is_ai(title):
            continue
        raw_desc = (
            entry.findtext("atom:summary", namespaces=ns)
            or entry.findtext("atom:content", namespaces=ns)
            or ""
        )
        try:
            articles.append(make_article(
                title       = title,
                url         = url,
                source      = source_name,
                source_type = "media",
                summary     = _truncate(_clean_html(raw_desc)),
            ))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.debug("Atom entry [%s] skipped: %s", source_name, exc)

    return articles


def scrape_rss() -> list:
    """Scrape all RSS / Atom feeds from config."""
    sources  = cfg.scraper.rss_sources.as_dict()
    articles = []
    for name, url in sources.items():
        resp = _safe_get(url)
        if resp is None:
            log.warning("RSS unavailable: %s", name)
            continue
        items = _parse_rss(resp.text, name)
        log.info("RSS %s: %d AI articles", name, len(items))
        articles.extend(items)
    return articles


# ── Deduplication & scoring ───────────────────────────────────────────────────

def deduplicate(articles: list) -> list:
    """
    Group stories covering the same event across sources, then score.

    Scoring (all weights from config.yaml):
      base_score
      + min(cross_source_bonus × (n−1), max_cross_source_bonus)
      + diversity_bonus   if community AND media both present
      + hn_score_bonus    if HN score ≥ hn_score_threshold
    Capped at 1.0. Stories below min_authenticity are dropped.
    """
    sc    = cfg.scoring
    sim_t = sc.similarity_threshold
    groups: list = []

    for article in articles:
        matched = False
        for i, group in enumerate(groups):
            if _similarity(article["title"], group[0]["title"]) >= sim_t:
                groups[i].append(article)
                matched = True
                break
        if not matched:
            groups.append([article])

    result = []
    for group in groups:
        rep          = max(group, key=lambda a: (a.get("score", 0), len(a.get("summary", ""))))
        sources      = list({a["source"] for a in group})
        source_types = {a["source_type"] for a in group}
        n            = len(sources)
        rep["summary"] = max((a.get("summary", "") for a in group), key=len)

        auth = min(
            sc.base_score
            + min(sc.cross_source_bonus * (n - 1), sc.max_cross_source_bonus)
            + (sc.diversity_bonus if len(source_types) > 1 else 0.0)
            + (sc.hn_score_bonus  if rep.get("score", 0) >= sc.hn_score_threshold else 0.0),
            1.0,
        )
        if auth < sc.min_authenticity:
            continue

        rep["authenticity_score"] = round(auth, 2)
        rep["source_count"]       = n
        rep["all_sources"]        = sources
        result.append(rep)

    result.sort(key=lambda a: (a["authenticity_score"], a.get("score", 0)), reverse=True)
    return result


# ── History management ────────────────────────────────────────────────────────

def _prune_history() -> None:
    """
    Remove entries older than history.max_age_days from history.log.
    Entry format: '<id>\t<YYYY-MM-DD>'
    Legacy single-column entries (no date) are preserved unconditionally.
    """
    if not os.path.exists(HISTORY_FILE):
        return
    cutoff  = datetime.now(timezone.utc) - timedelta(days=cfg.history.max_age_days)
    kept    = []
    pruned  = 0
    with open(HISTORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    entry_date = datetime.strptime(parts[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if entry_date < cutoff:
                        pruned += 1
                        continue
                except ValueError:
                    pass
            kept.append(line)

    if pruned:
        with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(kept) + "\n")
        log.info("History: pruned %d entries (> %d days old); %d remaining",
                 pruned, cfg.history.max_age_days, len(kept))


def load_history() -> set:
    """Return set of reported article IDs after pruning old entries."""
    _prune_history()
    if not os.path.exists(HISTORY_FILE):
        return set()
    seen = set()
    with open(HISTORY_FILE, encoding="utf-8") as fh:
        for line in fh:
            parts = line.strip().split("\t")
            if parts[0]:
                seen.add(parts[0])
    return seen


def append_history(ids: list) -> None:
    """Append article IDs with today's date to history.log."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        for article_id in ids:
            fh.write(f"{article_id}\t{today}\n")


# ── Output ────────────────────────────────────────────────────────────────────

def _write(articles: list, raw_count: int = 0) -> None:
    """Atomic write: tmp file + os.replace to prevent partial writes."""
    payload = {
        "meta": {
            "generated_at":   datetime.now(timezone.utc).isoformat(),
            "article_count":  len(articles),
            "raw_count":      raw_count,
            "config_version": cfg.version,
        },
        "articles": articles,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = NEWS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, NEWS_FILE)
    log.info("Written %d articles → %s", len(articles), NEWS_FILE)


# ── Entry point ───────────────────────────────────────────────────────────────

def scrape() -> list:
    """
    Run all scrapers, deduplicate, score, write news_feed.json.
    Always writes valid output — network failure → empty feed, not a crash.
    """
    log.info("NeoSignal v%s scrape starting.", cfg.version)
    raw = []
    for fn, name in [(scrape_hackernews, "HN"),
                     (scrape_reddit, "Reddit"),
                     (scrape_rss, "RSS")]:
        try:
            batch = fn()
            raw.extend(batch)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("%s scraper crashed: %s", name, exc)

    articles = deduplicate(raw)
    log.info("Final: %d articles (%d raw)", len(articles), len(raw))
    _write(articles, raw_count=len(raw))
    return articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    scrape()
