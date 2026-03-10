# pylint: disable=missing-function-docstring
"""Unit tests for NeoSignal multi-source scraper v3.1"""

import json
from unittest.mock import MagicMock, patch

import requests as req

from src.scraper import (
    _article_id,
    _is_ai,
    _similarity,
    _clean_html,
    _truncate,
    deduplicate,
    scrape,
    _write,
)


class TestIsAi:
    """AI keyword filter tests."""

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


class TestArticleId:
    """Article ID generation tests."""

    def test_same_title_same_id(self):
        assert _article_id("GPT-5 is here") == _article_id("GPT-5 is here")

    def test_case_normalised(self):
        assert _article_id("GPT-5") == _article_id("gpt-5")

    def test_length_is_12(self):
        assert len(_article_id("any title")) == 12


class TestSimilarity:
    """Title similarity scoring tests."""

    def test_identical_is_one(self):
        assert _similarity("GPT-5 released", "GPT-5 released") == 1.0

    def test_different_below_threshold(self):
        assert _similarity("OpenAI raises funding", "Coffee shop in Berlin") < 0.45

    def test_same_story_above_threshold(self):
        assert _similarity(
            "OpenAI releases GPT-5 model",
            "OpenAI launches new GPT-5 language model",
        ) >= 0.45


class TestCleanHtml:
    """HTML stripping tests."""

    def test_strips_tags(self):
        assert _clean_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert "&amp;" not in _clean_html("AT&amp;T announces AI product")

    def test_empty_returns_empty(self):
        assert _clean_html("") == ""

    def test_none_returns_empty(self):
        assert _clean_html(None) == ""


class TestTruncate:
    """Summary truncation tests."""

    def test_short_text_unchanged(self):
        assert _truncate("Short text.") == "Short text."

    def test_long_text_truncated(self):
        long = "word " * 100
        result = _truncate(long, max_chars=50)
        assert len(result) <= 55
        assert result.endswith("...")

    def test_truncates_at_word_boundary(self):
        result = _truncate("one two three four five six seven", max_chars=12)
        assert " " not in result.replace("...", "").strip().split()[-1] or result.endswith("...")


class TestDeduplicate:
    """Cross-source deduplication and scoring tests."""

    @staticmethod
    def _art(title, source, source_type="media", score=0, summary=""):
        return {
            "id": _article_id(title), "title": title,
            "url": "https://example.com", "summary": summary,
            "source": source, "source_type": source_type,
            "score": score, "date": "2026-03-10",
            "scraped_at": "2026-03-10T00:00:00+00:00",
        }

    def test_single_source_base_score(self):
        result = deduplicate([self._art("New LLM released", "TechCrunch AI")])
        assert len(result) == 1
        assert result[0]["authenticity_score"] == 0.5

    def test_two_sources_higher_score(self):
        arts = [
            self._art("OpenAI launches GPT-5", "TechCrunch AI", "media"),
            self._art("OpenAI announces GPT-5 model", "VentureBeat AI", "media"),
        ]
        result = deduplicate(arts)
        assert len(result) == 1
        assert result[0]["authenticity_score"] > 0.5
        assert result[0]["source_count"] == 2

    def test_cross_type_diversity_bonus(self):
        arts = [
            self._art("Anthropic Claude 4 released", "TechCrunch AI", "media"),
            self._art("Anthropic releases Claude 4", "HackerNews", "community"),
        ]
        result = deduplicate(arts)
        assert result[0]["authenticity_score"] >= 0.9

    def test_hn_score_bonus(self):
        result = deduplicate([self._art("New neural net paper", "HackerNews", "community", score=250)])
        assert result[0]["authenticity_score"] >= 0.6

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


class TestWrite:
    """Atomic JSON write tests."""

    def test_writes_structured_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))
        arts = [{"id": "abc", "title": "LLM story", "url": "https://x.com",
                 "summary": "", "source": "HN", "source_type": "community",
                 "score": 0, "date": "2026-03-10", "scraped_at": "2026-03-10T00:00:00+00:00"}]
        _write(arts, raw_count=5)
        data = json.loads((tmp_path / "news_feed.json").read_text())
        assert data["meta"]["article_count"] == 1
        assert data["meta"]["raw_count"] == 5
        assert data["articles"][0]["title"] == "LLM story"

    def test_empty_is_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))
        _write([])
        data = json.loads((tmp_path / "news_feed.json").read_text())
        assert data["articles"] == []


class TestScrape:
    """Integration tests for full scrape pipeline."""

    def test_writes_output_on_network_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))
        with patch("src.scraper.requests.get", side_effect=req.RequestException("down")):
            result = scrape()
        assert not result
        assert (tmp_path / "news_feed.json").exists()

    def test_filters_non_ai(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.scraper.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("src.scraper.NEWS_FILE", str(tmp_path / "news_feed.json"))

        def mock_get(url, **_kwargs):
            """Mock requests.get for HN endpoints."""
            mock = MagicMock()
            if "stories" in url:
                mock.json.return_value = [1, 2]
            elif "/item/1" in url:
                mock.json.return_value = {"id": 1, "title": "GPT-5 by OpenAI",
                                          "url": "https://openai.com", "score": 500, "text": ""}
            elif "/item/2" in url:
                mock.json.return_value = {"id": 2, "title": "Best pizza in Rome",
                                          "url": "https://food.com", "score": 10}
            else:
                raise req.RequestException("blocked")
            return mock

        with patch("src.scraper.requests.get", side_effect=mock_get):
            result = scrape()

        titles = [a["title"] for a in result]
        assert any("GPT" in t for t in titles)
        assert not any("pizza" in t.lower() for t in titles)
