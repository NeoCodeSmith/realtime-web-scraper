# NeoSignal v4.0 — Developer workflow
# Usage: make <target>

.PHONY: install install-dev test lint audit run-scraper run-pdf run-digest clean help

PYTHON := python3
PIP    := pip3

## Install runtime dependencies
install:
	$(PIP) install -r requirements.txt

## Install all dev + runtime dependencies
install-dev:
	$(PIP) install -r requirements-dev.txt

## Run all tests with coverage summary
test:
	$(PYTHON) -m pytest tests/ -v --tb=short

## Run pylint on src + tests
lint:
	$(PYTHON) -m pylint src/ tests/

## Run dependency vulnerability audit
audit:
	$(PYTHON) -m pip_audit -r requirements.txt

## Run scraper only
run-scraper:
	$(PYTHON) -m src.scraper

## Run PDF generator (requires news_feed.json)
run-pdf:
	$(PYTHON) -m src.pdf_generator

## Run weekly digest generator
run-digest:
	$(PYTHON) -m src.digest

## Full pipeline: scrape → PDF
run:
	$(PYTHON) -m src.scraper && $(PYTHON) -m src.pdf_generator

## Remove all generated artefacts (does NOT remove committed data)
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

## Show available targets
help:
	@grep -E '^##' Makefile | sed 's/## //'
