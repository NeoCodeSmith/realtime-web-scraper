# NeoSignal v4.0 — Architecture

## Overview

NeoSignal is a fully automated AI news intelligence pipeline that runs as a scheduled GitHub Actions workflow. It scrapes 10+ sources, deduplicates cross-source stories, scores authenticity, and delivers a styled PDF report daily at 9 AM IST.

```
┌──────────────────────────────────────────────────────────────┐
│                    GitHub Actions (CI/CD)                    │
│  ┌────────────┐   ┌───────────────┐   ┌───────────────────┐  │
│  │  Scraper   │──▶│ news_feed.json│──▶│  PDF Generator    │  │
│  │ (scraper.py│   │  (data/)      │   │ (pdf_generator.py)│  │
│  └────────────┘   └───────────────┘   └───────────────────┘  │
│        │                                        │             │
│        ▼                                        ▼             │
│  ┌──────────┐                          ┌───────────────────┐  │
│  │ history  │                          │  reports/*.pdf    │  │
│  │  .log    │                          │  archive/YYYY-WWW │  │
│  └──────────┘                          └───────────────────┘  │
└──────────────────────────────────────────────────────────────┘
              │ config/config.yaml (single source of truth)
```

---

## Module Map

| Module | Purpose |
|--------|---------|
| `src/config.py` | Loads `config/config.yaml`, applies env overrides, exposes `cfg` singleton |
| `src/models.py` | `Article` TypedDict + validated `make_article()` factory |
| `src/scraper.py` | Scrapes HN / Reddit / RSS, deduplicates, scores, writes `data/news_feed.json` |
| `src/pdf_generator.py` | Reads `news_feed.json`, renders premium tiered PDF to `reports/` |
| `src/digest.py` | Categorises articles, renders weekly digest PDF to `archive/` |

---

## Configuration Architecture

**All tunable parameters live in `config/config.yaml`**. This is the single source of truth. No values are hardcoded in Python source.

### Environment Override Pattern

Any config leaf value can be overridden via environment variable:

```
NEOSIGNAL__<SECTION>__<KEY>=<value>
```

Examples:
```bash
NEOSIGNAL__SCRAPER__HN_LIMIT=100
NEOSIGNAL__SCORING__MIN_AUTHENTICITY=0.3
NEOSIGNAL__HISTORY__MAX_AGE_DAYS=60
```

Set these as GitHub Actions Secrets for runtime overrides without code changes.

### Config Sections

```yaml
scraper:        # URLs, limits, retry settings, User-Agent
scoring:        # Authenticity score formula weights
history:        # Log TTL, filename
pdf:            # Font paths, tier thresholds
digest:         # Lookback window, per-category cap
keywords:
  ai_filter:          # Keywords for AI article detection
  digest_categories:  # Keyword lists per intelligence domain
```

---

## Authenticity Scoring

```
score = base_score
        + min(cross_source_bonus × (n_sources − 1), max_cross_source_bonus)
        + diversity_bonus   (if community AND media sources both present)
        + hn_score_bonus    (if top HN score ≥ hn_score_threshold)
        capped at 1.0
```

Default weights (from `config.yaml`):

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `base_score` | 0.50 | Single-source baseline |
| `cross_source_bonus` | 0.30 | Per additional corroborating source |
| `max_cross_source_bonus` | 0.50 | Cap on cross-source contribution |
| `diversity_bonus` | 0.10 | Community + media both present |
| `hn_score_bonus` | 0.10 | HN score ≥ threshold |
| `min_authenticity` | 0.25 | Discard threshold |

**Tiers:**
- **VERIFIED** ≥0.80 — 3+ independent sources including media
- **CONFIRMED** ≥0.50 — 2 sources or 1 quality media outlet
- **EMERGING** ≥0.25 — Single source, passes AI keyword filter

---

## Data Flow

### Daily Pipeline

```
1. scraper.py
   ├── scrape_hackernews()   → HN Show/Top/New (3 endpoints, first responding)
   ├── scrape_reddit()       → r/artificial, r/ML, r/singularity, r/LocalLLaMA
   └── scrape_rss()          → 6 RSS/Atom feeds
          │
          ▼
   deduplicate()             → title similarity + multi-source scoring
          │
          ▼
   _write()                  → atomic write to data/news_feed.json
          │
2. pdf_generator.py
   ├── load_history()        → prune old entries, return seen IDs
   ├── NeoSignalPDF.cover_page()
   ├── NeoSignalPDF.source_table()
   └── NeoSignalPDF.article_card() × N
          │
          ▼
   reports/neosignal_YYYYMMDD_HHMM.pdf
```

### Weekly Digest

```
1. scraper.py               → (same as daily)
2. digest.py
   ├── load_recent_articles() → articles from past 7 days
   ├── categorize()          → keyword-based domain classification
   └── DigestPDF             → cover + category sections
          │
          ▼
   archive/YYYY-WWW/neosignal_digest_YYYY-WWW.pdf
```

---

## Security Architecture

| Concern | Implementation |
|---------|---------------|
| XXE injection via RSS | `defusedxml` replaces `xml.etree.ElementTree` |
| API keys / secrets | Zero hardcoding; GitHub Actions Secrets only |
| Config in source | `config/config.yaml` — values only, no secrets |
| HTTP retry storms | Exponential backoff with configurable cap |
| Partial file writes | Atomic `tmp + os.replace()` for `news_feed.json` |
| History bloat | TTL-based pruning on every run (configurable days) |
| User-Agent spoofing | Version-tagged UA string from config |

---

## ADR Index

| ADR | Decision | Status |
|-----|---------|--------|
| [ADR-001](ADR-001-config-yaml.md) | Centralised YAML config over env-only | Accepted |
| [ADR-002](ADR-002-defusedxml.md) | `defusedxml` for RSS parsing | Accepted |
| [ADR-003](ADR-003-article-model.md) | TypedDict Article model with factory | Accepted |
| [ADR-004](ADR-004-history-ttl.md) | Timestamped history with TTL pruning | Accepted |
| [ADR-005](ADR-005-retry-backoff.md) | Exponential backoff for HTTP retries | Accepted |
