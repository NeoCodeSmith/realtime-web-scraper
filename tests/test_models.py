# pylint: disable=missing-function-docstring,missing-class-docstring
"""Tests for src/models.py — Article model, validation, factory."""

import pytest
from src.models import make_article, from_dict, _article_id, ArticleValidationError, tier_label


class TestArticleId:
    def test_same_title_same_id(self):
        assert _article_id("GPT-5 released") == _article_id("GPT-5 released")

    def test_case_normalised(self):
        assert _article_id("GPT-5") == _article_id("gpt-5")

    def test_whitespace_stripped(self):
        assert _article_id("  GPT-5  ") == _article_id("GPT-5")

    def test_length_is_12(self):
        assert len(_article_id("any title here")) == 12


class TestMakeArticle:
    def test_happy_path(self):
        art = make_article(
            title="New LLM released by OpenAI",
            url="https://openai.com",
            source="TechCrunch AI",
            source_type="media",
        )
        assert art["title"] == "New LLM released by OpenAI"
        assert art["source_type"] == "media"
        assert art["authenticity_score"] == 0.0
        assert art["source_count"] == 1
        assert len(art["id"]) == 12

    def test_empty_title_raises(self):
        with pytest.raises(ArticleValidationError, match="title"):
            make_article(title="", url="https://x.com", source="HN", source_type="community")

    def test_empty_url_raises(self):
        with pytest.raises(ArticleValidationError, match="url"):
            make_article(title="Valid title", url="", source="HN", source_type="community")

    def test_invalid_source_type_raises(self):
        with pytest.raises(ArticleValidationError, match="source_type"):
            make_article(title="T", url="https://x.com", source="HN", source_type="newspaper")

    def test_negative_score_raises(self):
        with pytest.raises(ArticleValidationError, match="score"):
            make_article(title="T", url="https://x.com", source="HN",
                         source_type="community", score=-1)

    def test_summary_capped_at_500(self):
        long_summary = "word " * 200  # 1000 chars
        art = make_article(title="T", url="https://x.com", source="HN",
                           source_type="community", summary=long_summary)
        assert len(art["summary"]) <= 500

    def test_source_type_normalised_lowercase(self):
        art = make_article(title="T", url="https://x.com", source="HN",
                           source_type="COMMUNITY")
        assert art["source_type"] == "community"

    def test_date_auto_set_if_none(self):
        art = make_article(title="T", url="https://x.com", source="HN", source_type="community")
        assert len(art["date"]) == 10  # YYYY-MM-DD


class TestFromDict:
    def test_round_trip(self):
        raw = {
            "title":       "Claude 4 released",
            "url":         "https://anthropic.com",
            "source":      "TechCrunch AI",
            "source_type": "media",
            "score":       0,
            "summary":     "Short summary.",
        }
        art = from_dict(raw)
        assert art["title"] == raw["title"]
        assert art["source"] == raw["source"]

    def test_missing_title_raises(self):
        with pytest.raises(ArticleValidationError, match="title"):
            from_dict({"url": "https://x.com", "source": "HN", "source_type": "community"})

    def test_missing_source_raises(self):
        with pytest.raises(ArticleValidationError, match="source"):
            from_dict({"title": "T", "url": "https://x.com", "source_type": "media"})

    def test_defaults_filled(self):
        art = from_dict({"title": "T", "url": "https://x.com",
                         "source": "HN", "source_type": "community"})
        assert art["score"] == 0
        assert art["summary"] == ""


class TestTierLabel:
    def test_verified(self):
        assert tier_label(0.85, 0.80, 0.50) == "VERIFIED"

    def test_confirmed(self):
        assert tier_label(0.65, 0.80, 0.50) == "CONFIRMED"

    def test_emerging(self):
        assert tier_label(0.30, 0.80, 0.50) == "EMERGING"

    def test_boundary_verified(self):
        assert tier_label(0.80, 0.80, 0.50) == "VERIFIED"

    def test_boundary_confirmed(self):
        assert tier_label(0.50, 0.80, 0.50) == "CONFIRMED"
