"""Tests for src/config.py — config loading, env overrides, immutability."""

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from src.config import _Section, _cast, _apply_env_overrides


class TestSection:
    """_Section dot-access wrapper."""

    def test_dot_access_returns_value(self):
        s = _Section({"foo": 42})
        assert s.foo == 42

    def test_nested_returns_section(self):
        s = _Section({"outer": {"inner": "val"}})
        assert s.outer.inner == "val"

    def test_missing_key_raises_attribute_error(self):
        s = _Section({"a": 1})
        with pytest.raises(AttributeError, match="Config key"):
            _ = s.missing

    def test_immutable_raises_on_setattr(self):
        s = _Section({"x": 1})
        with pytest.raises(TypeError, match="immutable"):
            s.x = 99

    def test_get_with_default(self):
        s = _Section({"a": 1})
        assert s.get("a") == 1
        assert s.get("missing", "default") == "default"

    def test_as_dict_returns_raw(self):
        data = {"k": "v"}
        s = _Section(data)
        assert s.as_dict() == data


class TestCast:
    """Type casting for env overrides."""

    def test_cast_int(self):
        assert _cast("42", 0) == 42

    def test_cast_float(self):
        assert abs(_cast("0.75", 0.0) - 0.75) < 1e-9

    def test_cast_bool_true_variants(self):
        for val in ("1", "true", "True", "TRUE", "yes", "on"):
            assert _cast(val, False) is True

    def test_cast_bool_false_variants(self):
        for val in ("0", "false", "False", "no", "off"):
            assert _cast(val, True) is False

    def test_cast_string_passthrough(self):
        assert _cast("hello", "default") == "hello"


class TestEnvOverrides:
    """Env var override application."""

    def test_override_int_value(self):
        data = {"scraper": {"hn_limit": 60}}
        with patch.dict(os.environ, {"NEOSIGNAL__SCRAPER__HN_LIMIT": "100"}):
            result = _apply_env_overrides(data)
        assert result["scraper"]["hn_limit"] == 100

    def test_override_float_value(self):
        data = {"scoring": {"min_authenticity": 0.25}}
        with patch.dict(os.environ, {"NEOSIGNAL__SCORING__MIN_AUTHENTICITY": "0.4"}):
            result = _apply_env_overrides(data)
        assert abs(result["scoring"]["min_authenticity"] - 0.4) < 1e-9

    def test_unknown_key_ignored(self):
        data = {"scraper": {"hn_limit": 60}}
        with patch.dict(os.environ, {"NEOSIGNAL__SCRAPER__NONEXISTENT": "999"}):
            result = _apply_env_overrides(data)
        assert "nonexistent" not in result["scraper"]

    def test_non_neosignal_env_ignored(self):
        data = {"scraper": {"hn_limit": 60}}
        with patch.dict(os.environ, {"OTHER_APP__SCRAPER__HN_LIMIT": "999"}):
            result = _apply_env_overrides(data)
        assert result["scraper"]["hn_limit"] == 60


class TestConfigLoad:
    """Full config.yaml load via the module-level singleton."""

    def test_cfg_version_present(self):
        from src.config import cfg
        assert cfg.version == "4.0"

    def test_scraper_section_accessible(self):
        from src.config import cfg
        assert cfg.scraper.hn_limit > 0

    def test_scoring_min_authenticity_in_range(self):
        from src.config import cfg
        val = cfg.scoring.min_authenticity
        assert 0.0 < val < 1.0

    def test_keywords_ai_filter_nonempty(self):
        from src.config import cfg
        kws = cfg.keywords.ai_filter
        assert isinstance(kws, list)
        assert len(kws) > 10

    def test_digest_categories_present(self):
        from src.config import cfg
        cats = cfg.keywords.digest_categories.as_dict()
        assert "Model Releases & Research" in cats
        assert "Safety & Regulation" in cats

    def test_history_max_age_positive(self):
        from src.config import cfg
        assert cfg.history.max_age_days > 0

    def test_missing_config_raises(self, tmp_path, monkeypatch):
        """FileNotFoundError when config.yaml is absent."""
        monkeypatch.setattr("src.config._CONFIG_PATH", tmp_path / "nonexistent.yaml")
        # Force reload by reimporting
        import importlib
        import src.config as mod
        with pytest.raises(FileNotFoundError):
            mod._load()

    def test_invalid_yaml_raises(self, tmp_path, monkeypatch):
        """ValueError when config.yaml is not a mapping."""
        bad = tmp_path / "config.yaml"
        bad.write_text("- just\n- a\n- list\n")
        monkeypatch.setattr("src.config._CONFIG_PATH", bad)
        import src.config as mod
        with pytest.raises(ValueError):
            mod._load()
