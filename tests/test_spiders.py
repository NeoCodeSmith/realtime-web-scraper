# Unit Tests for Scraper Spiders
# Enforces P1: Unit tests for all new code

import pytest
from scraper.spiders.base_spider import BaseSpider

class TestBaseSpider:
    @pytest.fixture
    def spider(self):
        return BaseSpider()
    
    def test_parse(self, spider, mocker):
        mock_response = mocker.Mock()
        mock_response.css.return_value.get.return_value = "Test Title"
        mock_response.url = "http://example.com"
        result = list(spider.parse(mock_response))
        assert result[0]["title"] == "Test Title"
        assert result[0]["url"] == "http://example.com"