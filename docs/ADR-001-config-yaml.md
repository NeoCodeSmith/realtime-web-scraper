# ADR-001: Centralised YAML Configuration

- **Date**: 2026-03-11
- **Status**: Accepted

## Context
v3.1 had 25+ magic values scattered across 3 source files. Adding/removing an RSS source required editing Python. Font paths were duplicated between `pdf_generator.py` and `digest.py`. Scoring weights were inlined in docstrings and code simultaneously.

## Decision
Single `config/config.yaml` as source of truth. `src/config.py` loads it at import time and exposes a `cfg` singleton with dot-access. All source files import `cfg`; zero hardcoded values.

## Rationale
- Operators can tune scoring, add sources, change limits without touching Python
- Environment variable override pattern (`NEOSIGNAL__SECTION__KEY`) supports GitHub Actions Secrets and CI overrides with zero code changes
- Immutable after load — prevents runtime mutation bugs
- YAML > .env for structured config (supports lists, nested dicts)

## Consequences
- ✅ Single place to change any parameter
- ✅ Config is auditable (plain text, git-tracked)
- ✅ CI can override specific values via env vars
- ⚠️ Config load failure = import failure (intentional — fail fast)
- ❌ Dynamic config reload requires process restart (acceptable for batch pipeline)

## Alternatives Considered
| Option | Reason Rejected |
|--------|----------------|
| Environment variables only | Cannot express nested structures (lists, dicts) |
| Python constants file | Requires code change for every config tweak |
| Database config | Overkill for a batch pipeline with no runtime API |
