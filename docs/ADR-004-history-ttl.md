# ADR-004: Timestamped History with TTL Pruning

- **Date**: 2026-03-11
- **Status**: Accepted

## Context
v3.1 `history.log` stored bare article IDs, one per line, with no date. After 432 entries the file was read in full on every run (O(n) set construction). With no pruning mechanism, the file grows forever. After 1 year at ~20 new articles/day = ~7,300 entries; after 5 years = ~36,500 entries, all of which are checked against even though articles older than 30 days are irrelevant.

## Decision
History entries are stored as `<id>\t<YYYY-MM-DD>`. On every run, `_prune_history()` removes entries older than `history.max_age_days` (default 30). Legacy single-column entries (no date) are preserved unconditionally for backwards compatibility.

## Rationale
- History file stays bounded at ≤30 days × ~20 articles/day = ~600 entries maximum
- O(n) load remains O(1) in practice since n is bounded
- Backwards compatible — existing entries without dates are kept
- TTL is configurable via `config.yaml`

## Consequences
- ✅ File size stays bounded
- ✅ Configurable retention window
- ✅ Backwards compatible
- ⚠️ Articles older than TTL will be re-reported if they reappear (acceptable — stale news)

## Migration
Existing entries without a date tab are preserved. They will never be pruned.
