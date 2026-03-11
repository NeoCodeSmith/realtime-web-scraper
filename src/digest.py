"""
NeoSignal Weekly Digest Generator v4.0

Categorises articles from news_feed.json into intelligence domains
and produces a styled weekly digest PDF saved to archive/YYYY-WWW/.

Categories and keyword lists are loaded from config/config.yaml
(keywords.digest_categories) — not hardcoded here.

All font paths and tier thresholds come from config/config.yaml.
"""

import json
import logging
import os
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fpdf import FPDF, XPos, YPos

from src.config import cfg

log = logging.getLogger(__name__)

BASE_DIR     = Path(__file__).resolve().parent.parent
NEWS_FILE    = BASE_DIR / "data" / "news_feed.json"
ARCHIVE_DIR  = BASE_DIR / "archive"

# Colour palette — consistent with pdf_generator
C_NAVY     = (10,  18,  40)
C_WHITE    = (255, 255, 255)
C_BG       = (245, 247, 252)
C_DIVIDER  = (210, 215, 230)
C_BODY     = (25,  28,  48)
C_MUTED    = (120, 125, 145)
C_URL      = (0,   90,  200)

CATEGORY_COLOURS = {
    "Model Releases & Research": (0,   100, 210),
    "Strategic & Business":      (0,   130, 80),
    "Safety & Regulation":       (180, 60,  0),
    "Tools & Engineering":       (100, 0,   180),
    "General AI News":           (60,  60,  90),
}


def _sanitize(text):
    """Smart-punctuation → ASCII, strip non-Latin-1."""
    for src, dst in {
        "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...",
    }.items():
        text = text.replace(src, dst)
    return unicodedata.normalize("NFKD", text).encode("latin-1", "ignore").decode("latin-1")


def _find_fonts():
    """Return (regular, bold) paths from config or (None, None)."""
    reg = cfg.pdf.font_regular
    bld = cfg.pdf.font_bold
    if os.path.exists(reg) and os.path.exists(bld):
        return reg, bld
    return None, None


def load_recent_articles(days=None):
    """Load articles from news_feed.json within the past N days."""
    lookback = days if days is not None else cfg.digest.lookback_days
    if not NEWS_FILE.exists():
        log.warning("news_feed.json not found.")
        return []
    try:
        data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("JSON parse error: %s", exc)
        return []
    articles = data.get("articles", []) if isinstance(data, dict) else data
    cutoff   = (datetime.now(timezone.utc) - timedelta(days=lookback)).date()
    recent   = []
    for art in articles:
        try:
            art_date = datetime.fromisoformat(art.get("date", "2000-01-01")).date()
            if art_date >= cutoff:
                recent.append(art)
        except ValueError:
            recent.append(art)
    log.info("Loaded %d articles from past %d days.", len(recent), lookback)
    return recent


def categorize(articles):
    """
    Classify each article into a digest category using config keywords.
    Falls back to 'General AI News' if no category matches.
    """
    categories = cfg.keywords.digest_categories.as_dict()
    result     = defaultdict(list)
    for art in articles:
        text    = (art.get("title", "") + " " + art.get("summary", "")).lower()
        matched = False
        for category, keywords in categories.items():
            if any(kw in text for kw in keywords):
                result[category].append(art)
                matched = True
                break
        if not matched:
            result["General AI News"].append(art)
    return dict(result)


class DigestPDF(FPDF):
    """NeoSignal weekly AI intelligence digest PDF."""

    def __init__(self, week):
        super().__init__()
        self._week = week
        self._fn   = cfg.pdf.font_fallback
        self._uni  = False
        self._load_fonts()
        self.set_margins(14, 10, 14)
        self.set_auto_page_break(auto=True, margin=18)

    def _load_fonts(self):
        reg, bld = _find_fonts()
        if reg and bld:
            try:
                self.add_font("DJ", style="",  fname=reg)
                self.add_font("DJ", style="B", fname=bld)
                self._fn  = "DJ"
                self._uni = True
                return
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.warning("DejaVu failed: %s", exc)

    def _t(self, text):
        return str(text) if self._uni else _sanitize(str(text))

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self._fn, "B", 7)
        self.set_text_color(0, 110, 230)
        self.cell(0, 5,
                  self._t(f"NeoSignal  ·  Weekly AI Digest  ·  {self._week}"),
                  align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*C_DIVIDER)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)
        self.set_text_color(*C_BODY)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-13)
        self.set_font(self._fn, size=7)
        self.set_text_color(*C_MUTED)
        self.cell(0, 6,
                  self._t(f"NeoSignal Weekly Digest  ·  {self._week}  ·  Page {self.page_no()}"),
                  align="C")
        self.set_text_color(*C_BODY)

    def cover_page(self, total, by_category, week_range):
        """Digest cover page with category breakdown."""
        self.add_page()
        self.set_fill_color(*C_NAVY)
        self.rect(0, 0, 210, 50, "F")
        self.set_xy(14, 9)
        self.set_font(self._fn, "B", 24)
        self.set_text_color(*C_WHITE)
        self.cell(0, 10, "NeoSignal", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(14)
        self.set_font(self._fn, size=8)
        self.set_text_color(150, 185, 255)
        self.cell(0, 5, self._t(f"Weekly AI Intelligence Digest  ·  {self._week}  ·  {week_range}"))
        self.set_xy(196 - 55, 12)
        self.set_font(self._fn, "B", 14)
        self.set_text_color(*C_WHITE)
        self.cell(55, 7, str(total), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(196 - 55, 21)
        self.set_font(self._fn, size=7)
        self.set_text_color(150, 185, 255)
        self.cell(55, 4, "stories this week", align="R")
        self.set_y(58)
        for cat, arts in sorted(by_category.items(), key=lambda x: -len(x[1])):
            colour = CATEGORY_COLOURS.get(cat, (80, 80, 100))
            self.set_fill_color(*colour)
            self.rect(14, self.get_y(), 3, 6, "F")
            self.set_x(20)
            self.set_font(self._fn, "B", 8)
            self.set_text_color(*colour)
            self.cell(110, 6, self._t(cat))
            self.set_font(self._fn, "B", 9)
            self.cell(0, 6, str(len(arts)), align="R",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_x(20)
            self.set_font(self._fn, size=7)
            self.set_text_color(*C_MUTED)
            preview = " · ".join(a["title"][:45] + "…" for a in arts[:2])
            self.multi_cell(176, 4, self._t(preview),
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
        self.set_text_color(*C_BODY)

    def section_header(self, title, count, colour):
        """Full-width coloured section banner."""
        self.ln(3)
        self.set_fill_color(*colour)
        self.rect(0, self.get_y(), 210, 8, "F")
        self.set_font(self._fn, "B", 8.5)
        self.set_text_color(*C_WHITE)
        self.cell(0, 8,
                  self._t(f"  {title.upper()}  —  {count} {'story' if count == 1 else 'stories'}"),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*C_BODY)
        self.ln(2)

    def article_entry(self, article, index, alt_bg=False):
        """One article row: title, summary, meta, URL."""
        title   = article.get("title", "Untitled")
        url     = article.get("url", "")
        source  = article.get("source", "?")
        score   = article.get("score", 0)
        auth    = article.get("authenticity_score", 0)
        summary = article.get("summary", "")
        bg      = C_BG if alt_bg else (255, 255, 255)

        self.set_fill_color(*bg)
        self.set_x(14)
        self.set_font(self._fn, "B", 8.5)
        self.set_text_color(*C_NAVY)
        self.cell(8, 5, str(index), fill=True)
        self.multi_cell(174, 5, self._t(title),
                        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if summary:
            self.set_x(22)
            self.set_font(self._fn, size=7.5)
            self.set_text_color(60, 65, 88)
            self.multi_cell(174, 4.5, self._t(summary),
                            fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(22)
        self.set_font(self._fn, size=6.5)
        self.set_text_color(*C_MUTED)
        auth_pct = f"{auth:.0%}" if auth else ""
        meta = self._t(f"{source}  ·  {auth_pct}  {'· HN ' + str(score) if score else ''}".strip(" ·"))
        self.cell(0, 4.5, meta, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(22)
        self.set_text_color(*C_URL)
        display_url = url if len(url) <= 90 else url[:87] + "..."
        self.cell(0, 4.5, self._t(display_url),
                  fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*C_DIVIDER)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2.5)
        self.set_text_color(*C_BODY)


def generate_digest():
    """Generate weekly digest PDF. Returns path or None."""
    articles = load_recent_articles()
    if not articles:
        log.warning("No articles found — skipping digest.")
        return None

    by_category = categorize(articles)
    week        = datetime.now().strftime("%Y-W%W")
    today       = datetime.now()
    week_start  = today - timedelta(days=today.weekday())
    week_range  = (
        f"{(week_start - timedelta(days=7)).strftime('%d %b')} – "
        f"{week_start.strftime('%d %b %Y')}"
    )
    total = sum(len(v) for v in by_category.values())

    pdf = DigestPDF(week=week)
    pdf.cover_page(total, by_category, week_range)
    pdf.add_page()

    categories = cfg.keywords.digest_categories.as_dict()
    idx = 1
    for cat in list(categories.keys()) + ["General AI News"]:
        cat_arts = by_category.get(cat, [])
        if not cat_arts:
            continue
        colour = CATEGORY_COLOURS.get(cat, (60, 60, 90))
        pdf.section_header(cat, len(cat_arts), colour)
        for i, art in enumerate(cat_arts[:cfg.digest.max_per_category]):
            est_h = 5 + (len(art.get("title", "")) // 80 + 1) * 5 + 12
            if pdf.get_y() + est_h > pdf.h - 20:
                pdf.add_page()
            pdf.article_entry(art, idx, alt_bg=i % 2 == 0)
            idx += 1

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    week_dir = ARCHIVE_DIR / week
    week_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = week_dir / f"neosignal_digest_{week}.pdf"
    pdf.output(str(pdf_path))
    log.info("Digest: %s  (%d stories, %d categories)", pdf_path, total, len(by_category))
    return str(pdf_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    generate_digest()
