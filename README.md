# NeoSignal

[![CI](https://github.com/NeoCodeSmith/NeoSignal/actions/workflows/ci.yml/badge.svg)](https://github.com/NeoCodeSmith/NeoSignal/actions/workflows/ci.yml)
[![Daily Report](https://github.com/NeoCodeSmith/NeoSignal/actions/workflows/daily_pipeline.yml/badge.svg)](https://github.com/NeoCodeSmith/NeoSignal/actions/workflows/daily_pipeline.yml)
[![Weekly Digest](https://github.com/NeoCodeSmith/NeoSignal/actions/workflows/weekly_digest.yml/badge.svg)](https://github.com/NeoCodeSmith/NeoSignal/actions/workflows/weekly_digest.yml)

**Automated AI intelligence pipeline.** Scrapes 10+ sources daily, deduplicates and cross-verifies stories, generates a premium styled PDF report, and delivers it by email at 9 AM IST.

---

## What It Does

| Step | Detail |
|------|--------|
| **Scrape** | HackerNews (Show/Top/New), Reddit ×4, TechCrunch AI, VentureBeat AI, MIT Tech Review, The Verge AI, Wired AI, ArXiv CS.AI |
| **Filter** | 35+ AI keyword patterns — LLMs, alignment, safety, research, tooling, strategy |
| **Deduplicate** | Title-similarity matching merges cross-source variants of the same story |
| **Score** | Authenticity formula: base + cross-source bonus + diversity bonus + HN score bonus |
| **Report** | Premium PDF — cover page, source breakdown, tiered articles (VERIFIED / CONFIRMED / EMERGING) |
| **Email** | Sent via Gmail SMTP if `EMAIL_*` secrets are configured |

---

## Quick Start

```bash
# Clone
git clone https://github.com/NeoCodeSmith/NeoSignal.git
cd NeoSignal

# Install
make install-dev

# Run full pipeline
make run

# Reports appear in reports/
```

---

## Configuration

**All parameters live in `config/config.yaml`** — the single source of truth. No values are hardcoded in Python source.

```yaml
# config/config.yaml (excerpt)
scraper:
  hn_limit: 60
  request_retries: 3

scoring:
  base_score: 0.5
  min_authenticity: 0.25

keywords:
  rss_sources:
    "TechCrunch AI": "https://techcrunch.com/..."
    # Add any RSS feed here — no code changes needed
```

### Runtime Overrides

Override any config value via environment variable:

```bash
NEOSIGNAL__SCRAPER__HN_LIMIT=100
NEOSIGNAL__SCORING__MIN_AUTHENTICITY=0.3
```

Set these as **GitHub Actions Secrets** for CI overrides.

### Secrets (Email Delivery)

Add these in **Settings → Secrets → Actions**:

| Secret | Purpose |
|--------|---------|
| `EMAIL_USERNAME` | Gmail address (sender) |
| `EMAIL_PASSWORD` | [Gmail App Password](https://support.google.com/accounts/answer/185833) |
| `EMAIL_TO` | Recipient address |

See [`.github/EMAIL_SETUP.md`](.github/EMAIL_SETUP.md) for step-by-step instructions.

---

## Adding a New Source

**RSS/Atom feed** — edit `config/config.yaml`, add one line:

```yaml
scraper:
  rss_sources:
    "My New Source": "https://example.com/ai/feed/"
```

No Python changes. No re-deployment. Commit and push.

**Reddit subreddit** — add an entry to `scraper.reddit_subs`:

```yaml
scraper:
  reddit_subs:
    - url:  "https://www.reddit.com/r/AINews.json?limit=25&sort=hot"
      name: "r/AINews"
```

---

## Authenticity Scoring

```
score = base (0.5)
      + min(0.3 × extra_sources, 0.5)   ← cross-source corroboration
      + 0.1 if community AND media both present
      + 0.1 if HN score ≥ 100
      capped at 1.0
```

| Tier | Score | Meaning |
|------|-------|---------|
| **VERIFIED** | ≥ 0.80 | 3+ independent sources including media |
| **CONFIRMED** | ≥ 0.50 | 2 sources or 1 high-quality outlet |
| **EMERGING** | ≥ 0.25 | Single source, passed keyword filter |

All weights are configurable in `config.yaml`.

---

## Repository Structure

```
NeoSignal/
├── config/
│   └── config.yaml          ← ALL tunable parameters here
├── src/
│   ├── config.py            ← Config loader + env override
│   ├── models.py            ← Article TypedDict + validated factory
│   ├── scraper.py           ← Multi-source scraper + dedup + scoring
│   ├── pdf_generator.py     ← Daily report PDF
│   └── digest.py            ← Weekly digest PDF
├── tests/
│   ├── test_config.py
│   ├── test_models.py
│   └── test_scraper.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ADR-001-config-yaml.md
│   ├── ADR-002-defusedxml.md
│   ├── ADR-003-article-model.md
│   ├── ADR-004-history-ttl.md
│   └── ADR-005-retry-backoff.md
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              ← Tests + lint (Python 3.11 & 3.12)
│   │   ├── daily_pipeline.yml  ← Scrape + PDF (9:00 AM IST daily)
│   │   └── weekly_digest.yml   ← Digest (9:00 PM IST Sunday)
│   └── EMAIL_SETUP.md
├── data/                    ← news_feed.json (committed by CI)
├── reports/                 ← Daily PDFs (committed by CI)
├── archive/                 ← Weekly digests (committed by CI)
├── Makefile
├── requirements.txt
├── requirements-dev.txt
└── history.log              ← Dedup log (auto-pruned after 30 days)
```

---

## Development

```bash
make test          # Run 91 tests
make lint          # Pylint src/ tests/
make audit         # Dependency vulnerability scan
make run-scraper   # Scraper only
make run-pdf       # PDF only (requires data/news_feed.json)
make run-digest    # Weekly digest
make clean         # Remove __pycache__, .pytest_cache
```

---

## CI/CD

| Workflow | Trigger | Steps |
|----------|---------|-------|
| **CI** | Push / PR to `main` | Tests (3.11+3.12), pylint ≥9.0, pip-audit |
| **Daily Report** | 9:00 AM IST | Scrape → PDF → commit → email |
| **Weekly Digest** | 9:00 PM IST Sunday | Scrape → categorise → digest → commit → email |

All pipeline artefacts (PDFs, `news_feed.json`, `history.log`) are committed back to the repo by the CI bot, forming a permanent archive.

---

## Security

- **No hardcoded secrets** — all credentials via GitHub Actions Secrets
- **XXE-safe XML parsing** — `defusedxml` used throughout (see [ADR-002](docs/ADR-002-defusedxml.md))
- **Retry with backoff** — prevents cascade failures and respects rate limits
- **Atomic writes** — `news_feed.json` written via tmp+replace, no partial reads
- **History TTL** — log bounded to 30 days, never grows unbounded

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
