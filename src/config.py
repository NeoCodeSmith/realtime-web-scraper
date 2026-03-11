"""
NeoSignal Configuration Loader v4.0

Loads config/config.yaml from the project root and exposes it as a typed,
immutable config object. Supports environment variable overrides using the
NEOSIGNAL__SECTION__KEY naming convention (double underscores as separators).

Usage:
    from src.config import cfg

    limit   = cfg.scraper.hn_limit          # int
    sources = cfg.scraper.rss_sources       # dict[str, str]
    score   = cfg.scoring.min_authenticity  # float
    kws     = cfg.keywords.ai_filter        # list[str]

Environment overrides (case-insensitive):
    NEOSIGNAL__SCRAPER__HN_LIMIT=100
    NEOSIGNAL__SCORING__MIN_AUTHENTICITY=0.3
    NEOSIGNAL__HISTORY__MAX_AGE_DAYS=60

Values are automatically cast to the same type as the YAML default:
    int    → NEOSIGNAL__SCRAPER__HN_LIMIT=100
    float  → NEOSIGNAL__SCORING__BASE_SCORE=0.6
    bool   → (true/false/yes/no/1/0 accepted)
    str    → everything else

No secrets are ever stored in config.yaml.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_ENV_PREFIX = "NEOSIGNAL"
_SEP        = "__"

# ── Config root ───────────────────────────────────────────────────────────────
_REPO_ROOT   = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "config.yaml"


class _Section:
    """
    Dot-access wrapper around a dict.
    Raises AttributeError with a helpful message on missing keys.
    """

    def __init__(self, data: dict, path: str = "") -> None:
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        path = object.__getattribute__(self, "_path")
        if name not in data:
            key = f"{path}.{name}" if path else name
            raise AttributeError(
                f"Config key '{key}' not found in config.yaml. "
                f"Available: {list(data.keys())}"
            )
        val = data[name]
        if isinstance(val, dict):
            prefix = f"{path}.{name}" if path else name
            return _Section(val, prefix)
        return val

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("Config is immutable. Edit config/config.yaml instead.")

    def get(self, name: str, default: Any = None) -> Any:
        """Dict-style get with default."""
        try:
            return getattr(self, name)
        except AttributeError:
            return default

    def as_dict(self) -> dict:
        """Return the raw underlying dict."""
        return dict(object.__getattribute__(self, "_data"))


def _cast(value: str, target: Any) -> Any:
    """Cast env-var string to the same type as the YAML default."""
    if isinstance(target, bool):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(target, int):
        return int(value)
    if isinstance(target, float):
        return float(value)
    return value


def _apply_env_overrides(data: dict, prefix: str = _ENV_PREFIX) -> dict:
    """
    Walk all NEOSIGNAL__SECTION__KEY environment variables and override
    matching leaf values in the config dict.

    Only overrides keys that already exist in config.yaml — prevents
    accidental injection of arbitrary config via environment.
    """
    overrides: list[tuple[str, str]] = []
    for env_key, env_val in os.environ.items():
        if not env_key.upper().startswith(prefix + _SEP):
            continue
        parts = env_key.upper().split(_SEP)[1:]   # drop NEOSIGNAL prefix
        parts = [p.lower() for p in parts]
        overrides.append((parts, env_val))

    for parts, env_val in overrides:
        node = data
        for i, part in enumerate(parts):
            if not isinstance(node, dict) or part not in node:
                log.warning("Env override %s: key path not found in config — ignored.",
                            _SEP.join(parts))
                break
            if i == len(parts) - 1:
                original = node[part]
                try:
                    node[part] = _cast(env_val, original)
                    log.info("Config override: %s = %r", ".".join(parts), node[part])
                except (ValueError, TypeError) as exc:
                    log.warning("Env override %s: cast failed (%s) — using YAML default.",
                                _SEP.join(parts), exc)
            else:
                node = node[part]
    return data


def _load() -> _Section:
    """Load config.yaml, apply env overrides, return immutable Section."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found: {_CONFIG_PATH}\n"
            "Expected location: config/config.yaml relative to repo root."
        )
    with open(_CONFIG_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"config.yaml must be a YAML mapping, got {type(raw)}")
    raw = _apply_env_overrides(raw)
    log.debug("Config loaded from %s (v%s)", _CONFIG_PATH, raw.get("version", "?"))
    return _Section(raw)


# Module-level singleton — import and use directly
cfg: _Section = _load()

__all__ = ["cfg"]
