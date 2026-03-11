# ADR-005: Exponential Backoff for HTTP Retries

- **Date**: 2026-03-11
- **Status**: Accepted

## Context
v3.1 `_safe_get()` made a single HTTP attempt per URL. One transient 429 (rate limit), 503 (server overload), or DNS blip permanently killed an entire source for that run. Reddit and ArXiv both rate-limit aggressively during peak hours.

## Decision
`_safe_get()` retries up to `request_retries` times (default 3) with wait = `min(backoff_base ^ attempt, backoff_max)` seconds between attempts. Retry triggers: `ConnectionError`, `Timeout`, 429, 5xx. No retry on: 4xx (client error, retry is futile).

## Rationale
- Exponential backoff is the standard defence against rate limits and transient failures
- Cap (`backoff_max=30s`) prevents excessive CI runtime on repeated failures
- 4xx errors are not retried (correct response to invalid requests)
- All retry params are configurable in `config.yaml`

## Consequences
- ✅ Transient failures no longer kill an entire source
- ✅ Respects 429 rate limiting
- ✅ All params configurable
- ⚠️ Worst-case pipeline runtime increases by `retries × backoff_max` per failing source
- ⚠️ Does not implement per-host rate limiting (out of scope for batch pipeline)

## Alternatives Considered
| Option | Reason Rejected |
|--------|----------------|
| `urllib3.Retry` + `HTTPAdapter` | Less transparent, harder to test |
| `tenacity` library | Adds dependency; exponential backoff is simple enough to implement directly |
| No retry (status quo) | One flaky source per day = missing data consistently |
