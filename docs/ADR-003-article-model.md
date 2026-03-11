# ADR-003: TypedDict Article Model with Validated Factory

- **Date**: 2026-03-11
- **Status**: Accepted

## Context
v3.1 constructed article dicts inline in each scraper function (HN, Reddit, RSS). A typo like `authentcity_score` would silently propagate as `0` in all downstream PDF rendering. Missing fields caused `KeyError` only at render time, far from the source. No single definition of what a valid article looks like.

## Decision
`src/models.py` defines:
- `Article` TypedDict — canonical field specification
- `make_article()` — validated factory; raises `ArticleValidationError` on constraint violations
- `from_dict()` — coerces raw dicts (from JSON) with validation

## Rationale
- TypedDict provides type-checker compatibility without runtime overhead
- Validation at creation time (fail fast, close to source)
- Single authoritative field list — prevents field-name drift across modules
- `make_article()` sets `id`, `date`, `scraped_at` deterministically
- Summary hard-capped at 500 chars at model level

## Consequences
- ✅ Field typos caught at construction, not at render time
- ✅ Invalid articles (empty title, bad source_type) never enter the pipeline
- ✅ JSON round-trip safe (TypedDict is a plain dict subclass)
- ⚠️ Every scraper must use `make_article()` — no naked dict construction

## Alternatives Considered
| Option | Reason Rejected |
|--------|----------------|
| `dataclasses` | Not JSON-serialisable without a custom encoder |
| `pydantic.BaseModel` | Adds large dependency for a batch pipeline |
| Plain dicts (status quo) | Silent failures, no validation |
