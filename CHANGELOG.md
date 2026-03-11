# Changelog

All notable changes to NeoSignal are documented here.
Format: [Semantic Versioning](https://semver.org/). Latest first.

---

## [4.0.0] — 2026-03-11

### Architecture — Breaking Changes
- **Centralised config**: All tunable parameters moved to `config/config.yaml`.
  Zero magic values in Python source. `src/config.py` loads YAML + applies
  `NEOSIGNAL__SECTION__KEY` env var overrides.
- **Article model**: New `src/models.py` — `Article` TypedDict + `make_article()`
  validated factory. All scrapers use it; bare dict construction removed.
- **Split requirements**: `requirements.txt` (runtime) + `requirements-dev.txt` (dev/test).

### Security Fixes
- **[P2-SEC] XXE injection**: Replaced `xml.etree.ElementTree` with `defusedxml`
  throughout RSS parsing. Malicious feeds can no longer read local files.
- **Zero hardcoded secrets**: All URLs, limits, and parameters in `config.yaml`.
  Python source contains no literal URLs, scoring constants, or font paths.

### Reliability Fixes
- **[P1-REL] Retry + backoff**: `_safe_get()` retries up to 3× with exponential
  backoff (configurable). One transient 429/503 no longer kills a source.
- **[P1-REL] History TTL**: `history.log` entries timestamped (`id\tYYYY-MM-DD`).
  Entries older than `max_age_days` (default 30) pruned on every run.
  Prevents unbounded file growth.
- **[P1-REL] Atomic write**: `news_feed.json` written via tmp+`os.replace()`.
  Partial writes on disk-full no longer corrupt the feed.

### Testing
- 91 tests (up from 29): added `test_config.py`, `test_models.py`,
  expanded `test_scraper.py` with retry, RSS parsing, history TTL, and
  pipeline isolation tests.
- CI matrix: Python 3.11 and 3.12.
- `pip-audit` dependency vulnerability scan in CI.

### Developer Experience
- `Makefile`: `make test`, `make lint`, `make audit`, `make run`, `make clean`
- `docs/ARCHITECTURE.md`: full system diagram, module map, data flow
- `docs/ADR-001` through `ADR-005`: all major architectural decisions recorded
- `.python-version` file added

---

## [3.1.0] — 2026-03-11

- `digest.py` v3.1: cover page with category breakdown, summary + auth scores
- Fixed git rebase exit-1: commit-first pattern (`add → commit → pull --rebase → push`)
- Fixed email pre-flight: `Check email secrets` step prevents crash on unset secrets
- Repo cleanup: removed committed `__pycache__`, stale `data/news_feed.json`, test PDFs
- Updated `.gitignore`, `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`

## [3.0.0] — 2026-03-10

- 10+ AI news sources (HN, Reddit ×4, TechCrunch AI, VentureBeat AI, MIT Tech Review,
  The Verge AI, Wired AI, ArXiv CS.AI)
- Cross-source authenticity scoring formula
- Deduplication via title similarity (SequenceMatcher)
- Summary extraction (HTML-stripped, 280-char cap)
- Premium PDF: cover page, source breakdown table, tiered article cards
- History-based deduplication across runs
- 29 unit tests

## [2.0.0] — Prior

- Multi-source scraper (initial version)
- Basic PDF generation

## [1.0.0] — Prior

- Single-source HackerNews scraper
