"""
NeoSignal PDF Report Generator v4.0

Generates a premium multi-page intelligence report from news_feed.json.

Pages:
  1. Cover — brand bar, stat cards (Total/Verified/Confirmed/Emerging),
             pipeline explanation, tier legend
  2. Source Breakdown — table: source name, article count, category
  3+. Articles — tiered sections (VERIFIED → CONFIRMED → EMERGING)
      Each card: index, tier label, title, source badge, cross-source count,
      authenticity %, HN score, summary, URL

Layout: pure flow (zero absolute set_xy inside cards).
Pre-flight height estimation triggers page breaks BEFORE a card, never mid-card.

All config (font paths, tier thresholds, scoring weights) from config/config.yaml.
"""

import html as html_lib
import json
import logging
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from fpdf import FPDF, XPos, YPos

from src.config import cfg

log = logging.getLogger(__name__)

BASE_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = BASE_DIR / "data"
REPORTS_DIR   = BASE_DIR / "reports"
NEWS_FILE     = DATA_DIR / "news_feed.json"
HISTORY_FILE  = BASE_DIR / cfg.history.filename

# ── Colour palette ─────────────────────────────────────────────────────────
C_NAVY       = (10,  18,  40)
C_BLUE       = (0,   110, 230)
C_VERIFIED   = (16,  122, 64)
C_CONFIRMED  = (200, 100, 0)
C_EMERGING   = (110, 110, 130)
C_MEDIA_BDG  = (0,   90,  190)
C_COMM_BDG   = (100, 50,  190)
C_BG_ALT     = (245, 247, 252)
C_WHITE      = (255, 255, 255)
C_DIVIDER    = (215, 220, 232)
C_BODY       = (25,  28,  48)
C_MUTED      = (120, 125, 145)
C_URL        = (0,   90,  200)

PAGE_W    = 210
L_MAR     = 14
R_MAR     = 14
CONTENT_W = PAGE_W - L_MAR - R_MAR


def _find_fonts():
    """Return (regular_path, bold_path) from config or (None, None)."""
    reg  = cfg.pdf.font_regular
    bld  = cfg.pdf.font_bold
    if os.path.exists(reg) and os.path.exists(bld):
        return reg, bld
    return None, None


def _sanitize(text):
    """Smart-punctuation → ASCII, strip non-Latin-1."""
    for src, dst in {
        "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u2022": "*",
        "\u2192": "->", "\u00d7": "x", "\u00b7": ".",
    }.items():
        text = text.replace(src, dst)
    return unicodedata.normalize("NFKD", text).encode("latin-1", "ignore").decode("latin-1")


def _strip_html(raw):
    """Remove HTML tags and decode entities."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _auth_tier(score):
    """Return (tier_label, colour_tuple) based on config thresholds."""
    if score >= cfg.pdf.tier_verified:
        return "VERIFIED",  C_VERIFIED
    if score >= cfg.pdf.tier_confirmed:
        return "CONFIRMED", C_CONFIRMED
    return "EMERGING", C_EMERGING


def _build_pipeline_steps():
    """Build pipeline explanation from config — no hardcoded source names."""
    rss_names = ", ".join(cfg.scraper.rss_sources.as_dict().keys())
    reddit_names = ", ".join(
        s.get("name", "?") for s in cfg.scraper.reddit_subs
    )
    sim_t  = cfg.scoring.similarity_threshold
    min_a  = cfg.scoring.min_authenticity
    base   = cfg.scoring.base_score
    bonus  = cfg.scoring.cross_source_bonus
    return [
        f"Scrape   HackerNews (Show/Top/New), Reddit ({reddit_names}), {rss_names}",
        f"Filter   {len(cfg.keywords.ai_filter)}+ AI keyword patterns — LLMs, alignment, safety, research, tooling",
        f"Dedup    Title-similarity ({int(sim_t*100)}% threshold) merges cross-source variants",
        f"Score    Authenticity = {base} base + {bonus} per extra source + diversity + HN score bonuses",
        f"Rank     Sorted by authenticity. Below {min_a} threshold are dropped.",
    ]


class NeoSignalPDF(FPDF):
    """NeoSignal premium PDF report — pure flow layout."""

    def __init__(self, issue_date):
        super().__init__()
        self.issue_date = issue_date
        self._fn        = cfg.pdf.font_fallback
        self._uni       = False
        self._load_fonts()
        self.set_margins(L_MAR, 10, R_MAR)
        self.set_auto_page_break(auto=True, margin=18)

    def _load_fonts(self):
        reg, bld = _find_fonts()
        if reg and bld:
            try:
                self.add_font("DJ", style="",  fname=reg)
                self.add_font("DJ", style="B", fname=bld)
                self._fn  = "DJ"
                self._uni = True
                log.info("PDF: DejaVu Unicode font loaded.")
                return
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.warning("DejaVu load failed: %s — fallback active.", exc)
        log.info("PDF: Using %s (ASCII sanitisation active).", self._fn)

    def _t(self, text):
        return str(text) if self._uni else _sanitize(str(text))

    def _tc(self, r, g, b):
        self.set_text_color(r, g, b)

    def _fc(self, r, g, b):
        self.set_fill_color(r, g, b)

    def _dc(self, r, g, b):
        self.set_draw_color(r, g, b)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font(self._fn, "B", 7)
        self._tc(*C_BLUE)
        self.cell(0, 5,
                  self._t(f"NeoSignal  ·  AI Intelligence Report  ·  {self.issue_date}"),
                  align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._dc(*C_DIVIDER)
        self.set_line_width(0.2)
        self.line(L_MAR, self.get_y(), PAGE_W - R_MAR, self.get_y())
        self.ln(2)
        self._tc(*C_BODY)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-13)
        self.set_font(self._fn, size=7)
        self._tc(*C_MUTED)
        self.cell(0, 6,
                  self._t(f"NeoSignal  ·  {self.issue_date}  ·  Page {self.page_no()}"),
                  align="C")
        self._tc(*C_BODY)

    def cover_page(self, total, verified, confirmed, emerging, sources_hit, raw_count):  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        """Full cover page."""
        self.add_page()

        # Brand bar
        self._fc(*C_NAVY)
        self.rect(0, 0, PAGE_W, 50, "F")
        self.set_xy(L_MAR, 9)
        self.set_font(self._fn, "B", 26)
        self._tc(*C_WHITE)
        self.cell(0, 11, "NeoSignal", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_x(L_MAR)
        self.set_font(self._fn, size=8)
        self._tc(150, 185, 255)
        self.cell(0, 5, self._t("AI Intelligence Daily  ·  Multi-Source  ·  Cross-Verified"))
        self.set_xy(PAGE_W - 72, 12)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_WHITE)
        self.cell(60, 5, self._t(self.issue_date), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(PAGE_W - 72, 19)
        self.set_font(self._fn, size=7)
        self._tc(150, 185, 255)
        self.cell(60, 4,
                  self._t(f"{total} verified  ·  {raw_count} raw  ·  {sources_hit} sources"),
                  align="R")

        # Stat cards
        cards = [
            ("TOTAL",     str(total),     C_BLUE),
            ("VERIFIED",  str(verified),  C_VERIFIED),
            ("CONFIRMED", str(confirmed), C_CONFIRMED),
            ("EMERGING",  str(emerging),  C_EMERGING),
        ]
        cw, cx, cy = (CONTENT_W - 9) / 4, float(L_MAR), 57.0
        for label, value, colour in cards:
            self._fc(*C_BG_ALT)
            self._dc(*colour)
            self.set_line_width(0.6)
            self.rect(cx, cy, cw, 24, "FD")
            self._fc(*colour)
            self.rect(cx, cy, cw, 3, "F")
            self.set_xy(cx, cy + 5)
            self.set_font(self._fn, "B", 17)
            self._tc(*colour)
            self.cell(cw, 8, value, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_x(cx)
            self.set_font(self._fn, size=6)
            self._tc(*C_MUTED)
            self.cell(cw, 4, label, align="C")
            cx += cw + 3
        self.set_line_width(0.2)

        # Pipeline explanation (built from config — no hardcoded source names)
        self.set_y(90)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_NAVY)
        self.cell(0, 6, "Pipeline", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font(self._fn, size=7.5)
        self._tc(55, 60, 80)
        for step in _build_pipeline_steps():
            self.multi_cell(CONTENT_W, 4.5, self._t(step),
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(0.5)

        # Tier legend
        self.ln(4)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_NAVY)
        self.cell(0, 6, "Authenticity Tiers", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        tv, tc = cfg.pdf.tier_verified, cfg.pdf.tier_confirmed
        for colour, tier, desc in [
            (C_VERIFIED,  f"VERIFIED   {tv:.2f} - 1.00", "3+ independent sources including media"),
            (C_CONFIRMED, f"CONFIRMED  {tc:.2f} - {tv - 0.01:.2f}", "2 sources or 1 high-quality media"),
            (C_EMERGING,  f"EMERGING   {cfg.scoring.min_authenticity:.2f} - {tc - 0.01:.2f}",
             "Single-source; passes AI keyword filter"),
        ]:
            self._fc(*colour)
            self.rect(L_MAR, self.get_y() + 1.5, 3, 3, "F")
            self.set_x(L_MAR + 5)
            self.set_font(self._fn, "B", 7.5)
            self._tc(*colour)
            self.cell(44, 5, self._t(tier))
            self.set_font(self._fn, size=7.5)
            self._tc(75, 80, 100)
            self.cell(0, 5, self._t(desc), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def source_table(self, articles):
        """Page 2 — source breakdown table."""
        self.add_page()
        self.set_font(self._fn, "B", 11)
        self._tc(*C_NAVY)
        self.cell(0, 8, "Source Breakdown", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._dc(*C_DIVIDER)
        self.line(L_MAR, self.get_y(), PAGE_W - R_MAR, self.get_y())
        self.ln(4)

        counts = Counter(
            s for a in articles for s in a.get("all_sources", [a.get("source", "?")])
        )
        col = [94, 28, 52]
        self._fc(*C_NAVY)
        self.set_font(self._fn, "B", 7.5)
        self._tc(*C_WHITE)
        for hdr in ["Source", "Articles", "Category"]:
            self.cell(col[0 if hdr == "Source" else 1 if hdr == "Articles" else 2],
                      6, hdr, fill=True)
        self.ln()
        alt = False
        for source, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            self._fc(*(C_BG_ALT if alt else C_WHITE))
            cat    = "Community" if source == "HackerNews" or "Reddit" in source else "Media"
            colour = C_COMM_BDG if cat == "Community" else C_MEDIA_BDG
            self.set_font(self._fn, size=7.5)
            self._tc(*C_BODY)
            self.cell(col[0], 5.5, self._t(source), fill=True)
            self._tc(*colour)
            self.cell(col[1], 5.5, str(cnt), align="C", fill=True)
            self._tc(*C_BODY)
            self.cell(col[2], 5.5, cat, fill=True)
            self.ln()
            alt = not alt
        self._tc(*C_BODY)

    def section_header(self, label, count, colour):
        """Full-width coloured tier banner."""
        self.ln(3)
        self._fc(*colour)
        self.rect(0, self.get_y(), PAGE_W, 8, "F")
        self.set_font(self._fn, "B", 8.5)
        self._tc(*C_WHITE)
        self.cell(0, 8,
                  self._t(f"  {label.upper()}  —  {count} {'story' if count == 1 else 'stories'}"),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._tc(*C_BODY)
        self.ln(2)

    def _estimate_card_height(self, article):
        """
        Conservative card height estimate.
        Errs on the side of larger to prevent mid-card page breaks.
        """
        title   = article.get("title", "")
        summary = article.get("summary", "")
        # ~80 chars per line at 9pt bold; summary ~90 chars per line at 7.5pt
        title_lines = max(1, len(title) // 80 + 1)
        summ_lines  = max(0, len(summary) // 90 + 1) if summary else 0
        # header(5) + title_lines×5 + meta(5) + summary_lines×4.5 + url(4.5) + padding(5)
        return 5 + title_lines * 5 + 5 + summ_lines * 4.5 + 4.5 + 5

    def article_card(self, article, index, alt_bg=False):  # pylint: disable=too-many-locals,too-many-statements
        """Render one article card — pure flow, zero absolute set_xy."""
        tier_label, tier_colour = _auth_tier(article.get("authenticity_score", 0))
        source      = article.get("source", "?")
        source_type = article.get("source_type", "media")
        badge_clr   = C_COMM_BDG if source_type == "community" else C_MEDIA_BDG
        n_src       = article.get("source_count", 1)
        auth        = article.get("authenticity_score", 0)
        score       = article.get("score", 0)
        title       = article.get("title", "Untitled")
        summary     = _strip_html(article.get("summary", ""))
        url         = article.get("url", "")

        bg = C_BG_ALT if alt_bg else C_WHITE
        self._fc(*bg)
        self._dc(*C_DIVIDER)
        self.set_line_width(0.15)

        card_top = self.get_y()

        # Index + tier label
        self.set_font(self._fn, "B", 7)
        self._tc(*C_MUTED)
        self.set_fill_color(*bg)
        self.cell(8, 5, str(index), fill=True)
        self._tc(*tier_colour)
        self._fc(*tier_colour)
        self.cell(12, 5, self._t(f"  {tier_label[:4]}"), fill=False,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Title
        self.set_x(L_MAR + 6)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_NAVY)
        self._fc(*bg)
        self.multi_cell(CONTENT_W - 6, 5, self._t(title),
                        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Meta row
        self.set_x(L_MAR + 6)
        self._fc(*badge_clr)
        self.set_font(self._fn, "B", 6)
        self._tc(*C_WHITE)
        badge = self._t(source[:30])
        bw    = self.get_string_width(badge) + 4
        self.cell(bw, 4.5, badge, fill=True)
        if n_src > 1:
            self.set_font(self._fn, size=6.5)
            self._tc(*tier_colour)
            self._fc(*bg)
            self.cell(38, 4.5, self._t(f"  +{n_src-1} source{'s' if n_src > 2 else ''}"), fill=True)
        self._fc(*tier_colour)
        self._tc(*C_WHITE)
        self.set_font(self._fn, "B", 6)
        auth_txt = self._t(f" {auth:.0%} ")
        self.cell(self.get_string_width(auth_txt) + 2, 4.5, auth_txt, fill=True)
        if score > 0:
            self._fc(*bg)
            self._tc(*C_MUTED)
            self.set_font(self._fn, size=6.5)
            self.cell(22, 4.5, self._t(f"  HN {score}"), fill=True)
        self.ln(4.5)

        # Summary
        self.set_x(L_MAR + 6)
        self._fc(*bg)
        if summary:
            self.set_font(self._fn, size=7.5)
            self._tc(60, 65, 88)
            self.multi_cell(CONTENT_W - 6, 4.5, self._t(summary),
                            fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            self.set_font(self._fn, "B", 7)
            self._tc(*C_MUTED)
            self.cell(0, 4.5, "No summary — see link for full article.",
                      fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # URL
        self.set_x(L_MAR + 6)
        self.set_font(self._fn, size=6.5)
        self._tc(*C_URL)
        display_url = url if len(url) <= 90 else url[:87] + "..."
        self.cell(0, 4.5, self._t(display_url),
                  fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Left tier stripe
        self._fc(*tier_colour)
        self.rect(L_MAR, card_top, 2.5, self.get_y() - card_top, "F")
        self._dc(*C_DIVIDER)
        self.line(L_MAR, self.get_y(), PAGE_W - R_MAR, self.get_y())
        self.ln(3)
        self._tc(*C_BODY)


# ── History ───────────────────────────────────────────────────────────────────

def load_history():
    """Return set of already-reported article IDs."""
    if HISTORY_FILE.exists():
        return {
            line.strip().split("\t")[0]
            for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    return set()


def update_history(ids):
    """Append reported IDs with today's date to history.log."""
    today = datetime.now().strftime("%Y-%m-%d")
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        for article_id in ids:
            fh.write(f"{article_id}\t{today}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def generate_report():
    """Generate premium PDF report. Returns PDF path or None."""
    if not NEWS_FILE.exists():
        log.error("news_feed.json missing — run scraper first.")
        return None
    try:
        data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON in news_feed.json: %s", exc)
        raise

    articles  = data.get("articles", []) if isinstance(data, dict) else data
    raw_count = data.get("meta", {}).get("raw_count", len(articles)) if isinstance(data, dict) else len(articles)
    if not articles:
        log.info("No articles — skipping PDF generation.")
        return None

    history  = load_history()
    new_arts = [a for a in articles if a.get("id", a.get("url", "")) not in history]
    if not new_arts:
        log.info("All %d articles already reported — reusing all for today.", len(articles))
        new_arts = articles

    verified  = sum(1 for a in new_arts if a.get("authenticity_score", 0) >= cfg.pdf.tier_verified)
    confirmed = sum(1 for a in new_arts
                    if cfg.pdf.tier_confirmed <= a.get("authenticity_score", 0) < cfg.pdf.tier_verified)
    emerging  = sum(1 for a in new_arts if a.get("authenticity_score", 0) < cfg.pdf.tier_confirmed)
    src_hit   = len({s for a in new_arts for s in a.get("all_sources", [a.get("source", "")])})

    issue_date = datetime.now().strftime("%d %B %Y")
    pdf        = NeoSignalPDF(issue_date)

    pdf.cover_page(len(new_arts), verified, confirmed, emerging, src_hit, raw_count)
    pdf.source_table(new_arts)

    tiers = [
        ("Verified Intelligence",
         [a for a in new_arts if a.get("authenticity_score", 0) >= cfg.pdf.tier_verified],
         C_VERIFIED),
        ("Confirmed Signals",
         [a for a in new_arts if cfg.pdf.tier_confirmed <= a.get("authenticity_score", 0) < cfg.pdf.tier_verified],
         C_CONFIRMED),
        ("Emerging Signals",
         [a for a in new_arts if a.get("authenticity_score", 0) < cfg.pdf.tier_confirmed],
         C_EMERGING),
    ]

    pdf.add_page()
    idx = 1
    for tier_name, tier_arts, colour in tiers:
        if not tier_arts:
            continue
        pdf.section_header(tier_name, len(tier_arts), colour)
        for i, art in enumerate(tier_arts):
            est_h = pdf._estimate_card_height(art)  # pylint: disable=protected-access
            if pdf.get_y() + est_h > pdf.h - 20:
                pdf.add_page()
            pdf.article_card(art, idx, alt_bg=i % 2 == 0)
            idx += 1

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp    = datetime.now().strftime("%Y%m%d_%H%M")
    pdf_path = REPORTS_DIR / f"neosignal_{stamp}.pdf"
    pdf.output(str(pdf_path))

    update_history([a.get("id", a.get("url", "")) for a in new_arts])
    log.info("Report: %s  (%d articles, %d verified)", pdf_path, len(new_arts), verified)
    return str(pdf_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    generate_report()
