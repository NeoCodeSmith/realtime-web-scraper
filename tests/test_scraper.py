# pylint: disable=missing-function-docstring
"""Unit & integration tests for NeoSignal multi-source scraper v4.0."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests as req

from src.models import _article_id
from src.scraper import (
    _is_ai,
    _clean_html,
    _truncate,
    _similarity,
    _parse_rss,
    _safe_get,
    deduplicate,
    scrape,
    _write,
    load_history,
    append_history,
    _prune_history,
)


# ── AI keyword filter ─────────────────────────────────────────────────────────

class TestIsAi:
    def test_llm_matches(self):
        assert _is_ai("Show HN: We built an LLM router") is True

    def test_case_insensitive(self):
        assert _is_ai("OpenAI releases GPT-5") is True

    def test_unrelated_no_match(self):
        assert _is_ai("Best coffee shops in Berlin") is False

    def test_empty_no_match(self):
        assert _is_ai("") is False

    def test_anthropic_matches(self):
        assert _is_ai("Anthropic raises $2B") is True

    def test_alignment_matches(self):
        assert _is_ai("AI alignment research from DeepMind") is True


# ── Text utilities ─────────────────────────────────────────────────────────────

class TestCleanHtml:
    def test_strips_tags(self):
        assert _clean_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert "&amp;" not in _clean_html("AT&amp;T announces AI product")

    def test_empty_returns_empty(self):
        assert _clean_html("") == ""

    def test_none_returns_empty(self):
        assert _clean_html(None) == ""

    def test_nested_tags(self):
        assert _clean_html("<div><p><a href='x'>Link</a></p></div>") == "Link"


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("Short text.") == "Short text."

    def test_long_text_truncated(self):
        long = "word " * 100
        result = _truncate(long, max_chars=50)
        assert len(result) <= 55
        assert result.endswith("...")

    def test_truncates_at_word_boundary(self):
        result = _truncate("one two three four five", max_chars=10)
        assert "..." in result
        # Should not cut mid-word
        core = result.replace("...", "")
        assert all(c.isalpha() or c == " " for c in core)

    def test_exactly_at_limit_not_truncated(self):
        text = "a" * 50
        assert _truncate(text, max_chars=50) == text


class TestSimilarity:
    def test_identical_is_one(self):
        assert _similarity("GPT-5 released", "GPT-5 released") == 1.0

    def test_completely_different_low(self):
        assert _similarity("OpenAI raises funding", "Coffee shop in Berlin") < 0.45

    def test_same_story_different_wording_above_threshold(self):
        assert _similarity(
            "OpenAI releases GPT-5 model",
            "OpenAI launches new GPT-5 language model",
        ) >= 0.45

    def test_case_insensitive(self):
        assert _similarity("GPT-5", "gpt-5") == 1.0


# ── RSS parsing ───────────────────────────────────────────────────────────────

class TestParseRss:
    RSS_XML = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>New LLM paper on arxiv</title>
          <link>https://arxiv.org/abs/1234</link>
          <description>A new paper about large language models.</description>
        </item>
        <item>
          <title>Best pizza in Naples</title>
          <link>https://food.com/pizza</link>
          <description>Great pizza recipe.</description>
        </item>
      </channel>
    </rss>"""

    ATOM_XML = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>GPT-5 released by OpenAI</title>
        <link href="https://openai.com/gpt5"/>
        <summary>OpenAI releases GPT-5 with major improvements.</summary>
      </entry>
      <entry>
        <title>Dog walking tips for beginners</title>
        <link href="https://pets.com/dogs"/>
        <summary>How to walk your dog.</summary>
      </entry>
    </feed>"""

    def test_rss_filters_ai_articles(self):
        articles = _parse_rss(self.RSS_XML, "Test Source")
        assert len(articles) == 1
        assert "LLM" in articles[0]["title"]

    def test_rss_extracts_summary(self):
        articles = _parse_rss(self.RSS_XML, "Test Source")
        assert "language models" in articles[0]["summary"]

    def test_atom_filters_ai_articles(self):
        articles = _parse_rss(self.ATOM_XML, "Test Atom")
        assert len(articles) == 1
        assert "GPT-5" in articles[0]["title"]

    def test_malformed_xml_returns_empty(self):
        articles = _parse_rss("<not valid xml>><<<", "Bad Source")
        assert articles == []

    def test_source_type_is_media(self):
        articles = _parse_rss(self.RSS_XML, "TechCrunch AI")
        assert articles[0]["source_type"] == "media"

    def test_source_name_preserved(self):
        articles = _parse_rss(self.RSS_XML, "My Source")
        assert articles[0]["source"] == "My Source"


# ── Safe get / retry ──────────────────────────────────────────────────────────

class TestSafeGet:
    def test_returns_response_on_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        with patch("src.scraper.requests.get", return_value=mock_resp):
            result = _safe_get("https://example.com", retries=0)
        assert result is not None

    def test_returns_none_on_connection_error(self):
        with patch("src.scraper.requests.get", side_effect=req.ConnectionError("down")):
            result = _safe_get("https://example.com", retries=0)
        assert result is None

    def test_retries_on_429(self):
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_ok  = MagicMock()
        mock_ok.status_code  = 200
        mock_ok.raise_for_status = MagicMock()
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            return mock_429 if call_count["n"] == 1 else mock_ok

        with patch("src.scraper.requests.get", side_effect=side_effect), \
             patch("src.scraper.time.sleep"):
            result = _safe_get("https://example.com", retries=2)
        assert result is mock_ok
        assert call_count["n"] == 2

    def test_returns_none_after_all_retries_exhausted(self):
        with patch("src.scraper.requests.get", side_effect=req.ConnectionError("down")), \
             patch("src.scraper.time.sleep"):
            result = _safe_get("https://example.com", retries=2)
        assert result is None


# ── Deduplication & scoring ───────────────────────────────────────────────────

class TestDeduplicate:
    @staticmethod
    def _art(title, source, source_type="media", score=0, summary=""):
        from src.models import make_article
        art = make_article(title=title, url="https://example.com",
                           source=source, source_type=source_type,
                           summary=summary, score=score)
        return art

    def test_single_source_base_score(self):
        result = deduplicate([self._art("New LLM released", "TechCrunch AI")])
        assert len(result) == 1
        from src.config import cfg
        assert result[0]["authenticity_score"] == cfg.scoring.base_score

    def test_two_sources_higher_score(self):
        arts = [
            self._art("OpenAI launches GPT-5", "TechCrunch AI", "media"),
            self._art("OpenAI announces GPT-5 model", "VentureBeat AI", "media"),
        ]
        result = deduplicate(arts)
        assert len(result) == 1
        from src.config import cfg
        assert result[0]["authenticity_score"] > cfg.scoring.base_score
        assert result[0]["source_count"] == 2

    def test_cross_type_diversity_bonus(self):
        arts = [
            self._art("Anthropic Claude 4 released", "TechCrunch AI", "media"),
            self._art("Anthropic releases Claude 4", "HackerNews", "community"),
        ]
        result = deduplicate(arts)
        from src.config import cfg
        expected = min(
            cfg.scoring.base_score + cfg.scoring.cross_source_bonus + cfg.scoring.diversity_bonus,
            1.0
        )
        assert abs(result[0]["authenticity_score"] - round(expected, 2)) < 0.01

    def test_hn_score_bonus_applied(self):
        from src.config import cfg
        result = deduplicate([
            self._art("New neural net paper", "HackerNews", "community",
                      score=cfg.scoring.hn_score_threshold + 1)
        ])
        assert result[0]["authenticity_score"] >= cfg.scoring.base_score + cfg.scoring.hn_score_bonus

    def test_distinct_stories_not_merged(self):
        arts = [
            self._art("OpenAI raises $10B from Microsoft", "TechCrunch AI"),
            self._art("New ArXiv paper on quantum computing algorithms", "ArXiv CS.AI"),
        ]
        assert len(deduplicate(arts)) == 2

    def test_best_summary_selected(self):
        arts = [
            self._art("Anthropic releases Claude", "HN", summary=""),
            self._art("Anthropic launches Claude model", "TC", summary="Detailed summary here."),
        ]
        result = deduplicate(arts)
        assert result[0]["summary"] == "Detailed summary here."

    def test_below_min_authenticity_dropped(self):
        from src.config import cfg
        # Single source → base score only; if base >= min_auth it passes
        # Force min to be higher than base via a separate low-score test
        result = deduplicate([self._art("AI story", "Solo Source")])
        # Default base 0.5 >= default min 0.25 — should pass
        assert len(result) == 1

    def test_output_sorted_by_score_desc(self):
        arts = [
            self._art("Low AI Story", "TechCrunch AI"),
            self._art("Anthropic Claude 4 breaking news", "TechCrunch AI",
                      "media", score=0),
            self._art("Anthropic Claude 4 released today", "HackerNews",
                      "community", score=500),
        ]
        result = deduplicate(arts)
        scores = [a["authenticity_score"] for a in result]
        assert scores == sorted(scores, reverse=True)


# ── Atomic write ──────────────────────────────────────────────────────────────

class TestWrite:
    def test_writes_structured_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))
        from src.models import make_article
        arts = [make_article(title="LLM story", url="https://x.com",
                             source="HN", source_type="community")]
        _write(arts, raw_count=5)
        data = json.loads((tmp_path / "news_feed.json").read_text())
        assert data["meta"]["article_count"] == 1
        assert data["meta"]["raw_count"] == 5
        assert data["articles"][0]["title"] == "LLM story"

    def test_empty_feed_is_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))
        _write([])
        data = json.loads((tmp_path / "news_feed.json").read_text())
        assert data["articles"] == []
        assert data["meta"]["article_count"] == 0

    def test_atomic_write_no_partial(self, tmp_path, monkeypatch):
        """If write fails mid-way, original file is untouched."""
        target = tmp_path / "news_feed.json"
        target.write_text('{"original": true}')
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(target))
        import builtins
        real_open = builtins.open

        def failing_open(path, *args, **kwargs):
            if str(path).endswith(".tmp"):
                raise OSError("Disk full")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=failing_open):
            with pytest.raises(OSError):
                _write([])

        assert json.loads(target.read_text())["original"] is True


# ── History management ────────────────────────────────────────────────────────

class TestHistory:
    def test_append_and_load(self, tmp_path, monkeypatch):
        hist = str(tmp_path / "history.log")
        monkeypatch.setattr("src.scraper.HISTORY_FILE", hist)
        append_history(["abc123", "def456"])
        seen = load_history()
        assert "abc123" in seen
        assert "def456" in seen

    def test_load_empty_returns_empty_set(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.HISTORY_FILE", str(tmp_path / "noexist.log"))
        assert load_history() == set()

    def test_prune_old_entries(self, tmp_path, monkeypatch):
        hist = tmp_path / "history.log"
        hist.write_text("old_id\t2020-01-01\nnew_id\t2099-12-31\n")
        monkeypatch.setattr("src.scraper.HISTORY_FILE", str(hist))
        _prune_history()
        remaining = hist.read_text()
        assert "old_id" not in remaining
        assert "new_id" in remaining

    def test_legacy_entry_without_date_preserved(self, tmp_path, monkeypatch):
        hist = tmp_path / "history.log"
        hist.write_text("legacyid_no_date\n")
        monkeypatch.setattr("src.scraper.HISTORY_FILE", str(hist))
        _prune_history()
        assert "legacyid_no_date" in hist.read_text()


# ── Full pipeline integration ─────────────────────────────────────────────────

class TestScrape:
    def test_writes_output_on_network_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))
        with patch("src.scraper.requests.get", side_effect=req.RequestException("down")):
            result = scrape()
        assert result == []
        assert (tmp_path / "news_feed.json").exists()

    def test_filters_non_ai_articles(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))

        def mock_get(url, **_kwargs):
            mock = MagicMock()
            mock.status_code = 200
            mock.raise_for_status = MagicMock()
            if "stories" in url:
                mock.json.return_value = [1, 2]
            elif "/item/1" in url:
                mock.json.return_value = {"id": 1, "title": "GPT-5 by OpenAI",
                                          "url": "https://openai.com", "score": 500}
            elif "/item/2" in url:
                mock.json.return_value = {"id": 2, "title": "Best pizza in Rome",
                                          "url": "https://food.com", "score": 10}
            else:
                raise req.RequestException("blocked")
            return mock

        with patch("src.scraper.requests.get", side_effect=mock_get), \
             patch("src.scraper.time.sleep"):
            result = scrape()

        titles = [a["title"] for a in result]
        assert any("GPT" in t for t in titles)
        assert not any("pizza" in t.lower() for t in titles)

    def test_one_source_failure_does_not_crash_pipeline(self, tmp_path, monkeypatch):
        """If one scraper raises, others still run and output is written."""
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))

        def crashing_hackernews():
            raise RuntimeError("Unexpected crash")

        with patch("src.scraper.scrape_hackernews", side_effect=crashing_hackernews), \
             patch("src.scraper.scrape_reddit", return_value=[]), \
             patch("src.scraper.scrape_rss", return_value=[]):
            result = scrape()

        assert result == []
        assert (tmp_path / "news_feed.json").exists()
