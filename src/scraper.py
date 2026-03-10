"""
NeoSignal Multi-Source Scraper v3.1
Scrapes 10 AI news sources, deduplicates across sources,
scores authenticity, and captures article summaries/descriptions.

Sources:
  1-3. HackerNews Show/Top/New  (Firebase API)
  4-7. Reddit r/artificial, r/MachineLearning, r/singularity, r/LocalLLaMA
  8.   TechCrunch AI     (RSS)
  9.   VentureBeat AI    (RSS)
 10.   MIT Technology Review (RSS)
 11.   The Verge AI      (RSS)
 12.   Wired AI          (RSS)
 13.   ArXiv CS.AI       (RSS)
"""

import hashlib
import html
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher

import requests

log = logging.getLogger(__name__)

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(BASE_DIR, "data")
NEWS_FILE = os.path.join(DATA_DIR, "news_feed.json")

HN_SHOW  = "https://hacker-news.firebaseio.com/v0/showstories.json"
HN_TOP   = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_NEW   = "https://hacker-news.firebaseio.com/v0/newstories.json"
HN_ITEM  = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_LIMIT = 60

REDDIT_HEADERS = {"User-Agent": "NeoSignal/3.1 (+https://github.com/NeoCodeSmith/NeoSignal)"}
REDDIT_SUBS = [
    "https://www.reddit.com/r/artificial.json?limit=50&sort=hot",
    "https://www.reddit.com/r/MachineLearning.json?limit=50&sort=hot",
    "https://www.reddit.com/r/singularity.json?limit=25&sort=hot",
    "https://www.reddit.com/r/LocalLLaMA.json?limit=25&sort=hot",
]

RSS_SOURCES = {
    "TechCrunch AI":   "https://techcrunch.com/category/artificial-intelligence/feed/",
    "VentureBeat AI":  "https://venturebeat.com/category/ai/feed/",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "The Verge AI":    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "Wired AI":        "https://www.wired.com/feed/tag/artificial-intelligence/latest/rss",
    "ArXiv CS.AI":     "http://export.arxiv.org/rss/cs.AI",
}

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "large language model", "neural network", "transformer",
    "gpt", "claude", "gemini", "llama", "mistral", "falcon",
    "openai", "anthropic", "deepmind", "meta ai", "hugging face",
    "diffusion", "stable diffusion", "midjourney",
    "rag", "vector", "embedding", "fine-tun", "reinforcement learning",
    "alignment", "nlp", "computer vision", "multimodal", "benchmark",
    "inference", "foundation model", "generative", "chatgpt", "copilot",
    "autonomous agent", "ai agent", "language model",
]

SIMILARITY_THRESHOLD = 0.45
MIN_AUTHENTICITY     = 0.25
CROSS_SOURCE_BONUS   = 0.3
SUMMARY_MAX_CHARS    = 280


def _safe_get(url, timeout=12, headers=None):
    """GET with error isolation. Returns None on any failure."""
    try:
        resp = requests.get(url, timeout=timeout, headers=headers or {})
        resp.raise_for_status()
        return resp
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.debug("Request failed [%s]: %s", url, exc)
        return None


def _is_ai(text):
    """Return True if text contains any AI keyword."""
    lower = text.lower()
    return any(kw in lower for kw in AI_KEYWORDS)


def _article_id(title):
    """Stable 12-char hex ID from normalised title."""
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]


def _similarity(a, b):
    """Title similarity ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _clean_html(raw):
    """Strip HTML tags and decode entities. Return plain text."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _truncate(text, max_chars=SUMMARY_MAX_CHARS):
    """Truncate to max_chars at word boundary."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated + "..."


# ── HackerNews ───────────────────────────────────────────────────────────────

def scrape_hackernews():
    """Scrape HN Show/Top/New with fallback. Captures HN text body if present."""
    ids = []
    for endpoint in (HN_SHOW, HN_TOP, HN_NEW):
        resp = _safe_get(endpoint)
        if resp is not None:
            ids = resp.json()[:HN_LIMIT]
            log.info("HN: %d IDs from %s", len(ids), endpoint.rsplit("/", maxsplit=1)[-1])
            break
    if not ids:
        log.warning("HN: all endpoints unreachable")
        return []

    articles = []
    for sid in ids:
        story = _safe_get(HN_ITEM.format(sid))
        if story is None:
            continue
        d = story.json()
        title = (d.get("title") or "").strip()
        if not title or not _is_ai(title):
            continue
        # HN stories may have a `text` body (Ask HN / Show HN)
        raw_text = _clean_html(d.get("text") or "")
        summary  = _truncate(raw_text) if raw_text else ""
        articles.append({
            "id":           _article_id(title),
            "title":        title,
            "url":          d.get("url") or f"https://news.ycombinator.com/item?id={sid}",
            "summary":      summary,
            "source":       "HackerNews",
            "source_type":  "community",
            "score":        d.get("score", 0),
            "date":         datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "scraped_at":   datetime.now(timezone.utc).isoformat(),
        })
    log.info("HN: %d AI articles", len(articles))
    return articles


# ── Reddit ────────────────────────────────────────────────────────────────────

def scrape_reddit():
    """Scrape AI subreddits. Captures selftext for text posts."""
    articles = []
    for sub_url in REDDIT_SUBS:
        resp = _safe_get(sub_url, headers=REDDIT_HEADERS)
        if resp is None:
            continue
        try:
            posts = resp.json()["data"]["children"]
        except (KeyError, ValueError, TypeError):
            continue
        sub_name = sub_url.split("/r/")[1].split(".json")[0]
        for post in posts:
            d = post.get("data", {})
            title = (d.get("title") or "").strip()
            if not title or not _is_ai(title):
                continue
            # Text posts have selftext; link posts have empty selftext
            raw_self = _clean_html(d.get("selftext") or "")
            summary  = _truncate(raw_self) if len(raw_self) > 30 else ""
            articles.append({
                "id":           _article_id(title),
                "title":        title,
                "url":          d.get("url") or f"https://reddit.com{d.get('permalink','')}",
                "summary":      summary,
                "source":       f"Reddit r/{sub_name}",
                "source_type":  "community",
                "score":        d.get("score", 0),
                "date":         datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "scraped_at":   datetime.now(timezone.utc).isoformat(),
            })
    log.info("Reddit: %d AI articles", len(articles))
    return articles


# ── RSS ───────────────────────────────────────────────────────────────────────

def _parse_rss(xml_text, source_name):
    """
    Parse RSS 2.0 and Atom feeds.
    Extracts title, link, and description/summary for each entry.
    """
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("RSS parse error [%s]: %s", source_name, exc)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # ── RSS 2.0 items ─────────────────────────────────────────────────────────
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url   = (item.findtext("link") or "").strip()
        if not title or not url or not _is_ai(title):
            continue
        # Try description, then content:encoded, then summary
        raw_desc = (
            item.findtext("description")
            or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            or ""
        )
        summary = _truncate(_clean_html(raw_desc))
        articles.append({
            "id":           _article_id(title),
            "title":        title,
            "url":          url,
            "summary":      summary,
            "source":       source_name,
            "source_type":  "media",
            "score":        0,
            "date":         datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "scraped_at":   datetime.now(timezone.utc).isoformat(),
        })

    # ── Atom entries ──────────────────────────────────────────────────────────
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
        summary = _truncate(_clean_html(raw_desc))
        articles.append({
            "id":           _article_id(title),
            "title":        title,
            "url":          url,
            "summary":      summary,
            "source":       source_name,
            "source_type":  "media",
            "score":        0,
            "date":         datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "scraped_at":   datetime.now(timezone.utc).isoformat(),
        })

    return articles


def scrape_rss():
    """Scrape all RSS/Atom feeds."""
    articles = []
    for name, url in RSS_SOURCES.items():
        resp = _safe_get(url, headers={"User-Agent": "NeoSignal/3.1"})
        if resp is None:
            log.warning("RSS unavailable: %s", name)
            continue
        items = _parse_rss(resp.text, name)
        log.info("RSS %s: %d AI articles", name, len(items))
        articles.extend(items)
    return articles


# ── Deduplication & scoring ───────────────────────────────────────────────────

def deduplicate(articles):
    """
    Merge duplicate stories across sources and compute authenticity score.

    Score formula:
      0.5  base
      +0.3 per additional source covering the same story (capped at +0.5)
      +0.1 if covered by both community and media source types
      +0.1 if top HN score >= 100
    """
    groups = []
    for article in articles:
        matched = False
        for i, group in enumerate(groups):
            if _similarity(article["title"], group[0]["title"]) >= SIMILARITY_THRESHOLD:
                groups[i].append(article)
                matched = True
                break
        if not matched:
            groups.append([article])

    result = []
    for group in groups:
        # Best representative: highest score, or longest summary
        rep          = max(group, key=lambda a: (a.get("score", 0), len(a.get("summary", ""))))
        sources      = list({a["source"] for a in group})
        source_types = {a["source_type"] for a in group}
        n            = len(sources)

        # Merge summaries: prefer longest non-empty summary from any source in group
        best_summary = max((a.get("summary", "") for a in group), key=len)
        rep["summary"] = best_summary

        auth = min(
            0.5
            + min(CROSS_SOURCE_BONUS * (n - 1), 0.5)
            + (0.1 if len(source_types) > 1 else 0.0)
            + (0.1 if rep.get("score", 0) >= 100 else 0.0),
            1.0,
        )
        if auth < MIN_AUTHENTICITY:
            continue

        rep["authenticity_score"] = round(auth, 2)
        rep["source_count"]       = n
        rep["all_sources"]        = sources
        result.append(rep)

    result.sort(key=lambda a: (a["authenticity_score"], a.get("score", 0)), reverse=True)
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape():
    """
    Run all scrapers, deduplicate, score, write news_feed.json.
    Always writes valid output — never raises on network failure.
    """
    log.info("NeoSignal v3.1 multi-source scrape starting.")
    os.makedirs(DATA_DIR, exist_ok=True)
    raw = []
    for fn, name in [(scrape_hackernews, "HN"), (scrape_reddit, "Reddit"), (scrape_rss, "RSS")]:
        try:
            batch = fn()
            raw.extend(batch)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.error("%s scraper crashed: %s", name, exc)

    articles = deduplicate(raw)
    log.info("Final: %d articles (from %d raw)", len(articles), len(raw))
    _write(articles, raw_count=len(raw))
    return articles


def _write(articles, raw_count=0):
    """Atomically write articles to NEWS_FILE."""
    payload = {
        "meta": {
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "article_count": len(articles),
            "raw_count":     raw_count,
        },
        "articles": articles,
    }
    tmp = NEWS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, NEWS_FILE)
    log.info("Written %d articles → %s", len(articles), NEWS_FILE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    scrape()
