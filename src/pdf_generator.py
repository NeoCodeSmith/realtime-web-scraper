"""
NeoSignal PDF Report Generator v3.1

Premium intelligence report with:
  - Cover page: brand bar, stat cards, pipeline explanation, tier legend
  - Source breakdown table
  - Articles in tier sections — each card has title, source badges,
    summary/description, authenticity score, and URL
  - Pure flow-based layout (no absolute set_xy inside cards)
  - Pre-flight page-break check ensures each card stays intact
  - DejaVu Unicode font with Latin-1 fallback
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

log = logging.getLogger(__name__)

BASE_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = BASE_DIR / "data"
REPORTS_DIR   = BASE_DIR / "reports"
NEWS_FILE     = DATA_DIR / "news_feed.json"
HISTORY_FILE  = BASE_DIR / "history.log"

# ── Colours ────────────────────────────────────────────────────────────────
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

TTF_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
TTF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PAGE_W   = 210
L_MAR    = 14
R_MAR    = 14
CONTENT_W = PAGE_W - L_MAR - R_MAR


def _find_fonts():
    """Return (regular_path, bold_path) or (None, None)."""
    if os.path.exists(TTF_REG) and os.path.exists(TTF_BOLD):
        return TTF_REG, TTF_BOLD
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
    """(label, colour) from authenticity score."""
    if score >= 0.8:
        return "VERIFIED",   C_VERIFIED
    if score >= 0.5:
        return "CONFIRMED",  C_CONFIRMED
    return "EMERGING",   C_EMERGING


class NeoSignalPDF(FPDF):
    """NeoSignal premium PDF report — pure flow layout."""

    def __init__(self, issue_date):
        super().__init__()
        self.issue_date = issue_date
        self._fn        = "Helvetica"
        self._uni       = False
        self._load_fonts()
        self.set_margins(L_MAR, 10, R_MAR)
        self.set_auto_page_break(auto=True, margin=18)

    # ── Font helpers ──────────────────────────────────────────────────────────

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
                log.warning("DejaVu load failed: %s — Helvetica fallback.", exc)
        log.info("PDF: Using Helvetica (ASCII sanitisation active).")

    def _t(self, text):
        """Text passthrough or sanitise depending on font mode."""
        return str(text) if self._uni else _sanitize(str(text))

    # ── Colour helpers ────────────────────────────────────────────────────────

    def _tc(self, r, g, b):
        self.set_text_color(r, g, b)

    def _fc(self, r, g, b):
        self.set_fill_color(r, g, b)

    def _dc(self, r, g, b):
        self.set_draw_color(r, g, b)

    # ── Header / footer ───────────────────────────────────────────────────────

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

    # ── Cover page ─────────────────────────────────────────────────────────────

    def cover_page(self, total, verified, confirmed, emerging, sources_hit, raw_count):  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        """Full cover page with branding, stats, and pipeline explanation."""
        self.add_page()

        # ── Brand bar ────────────────────────────────────────────────────────
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

        # Issue info top-right
        self.set_xy(PAGE_W - 72, 12)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_WHITE)
        self.cell(60, 5, self._t(self.issue_date), align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(PAGE_W - 72, 19)
        self.set_font(self._fn, size=7)
        self._tc(150, 185, 255)
        self.cell(60, 4,
                  self._t(f"{total} stories verified  ·  {raw_count} raw scraped  ·  {sources_hit} sources"),
                  align="R")

        # ── Stat cards ────────────────────────────────────────────────────────
        cards = [
            ("TOTAL",     str(total),     C_BLUE),
            ("VERIFIED",  str(verified),  C_VERIFIED),
            ("CONFIRMED", str(confirmed), C_CONFIRMED),
            ("EMERGING",  str(emerging),  C_EMERGING),
        ]
        cw    = (CONTENT_W - 9) / 4
        cx    = float(L_MAR)
        cy    = 57.0
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

        # ── Pipeline explanation ───────────────────────────────────────────────
        self.set_y(90)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_NAVY)
        self.cell(0, 6, "Pipeline", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font(self._fn, size=7.5)
        self._tc(55, 60, 80)
        steps = [
            "Scrape  HackerNews (Show/Top/New), Reddit (r/artificial, r/MachineLearning, "
            "r/singularity, r/LocalLLaMA), TechCrunch AI, VentureBeat AI, MIT Tech Review, "
            "The Verge AI, Wired AI, ArXiv CS.AI",
            "Filter   30+ AI keyword patterns — LLMs, alignment, safety, research, tooling, strategy",
            "Dedup   Title-similarity matching (45% threshold) merges cross-source variants of same story",
            "Score   Authenticity = 0.5 base + 0.3 per extra source + diversity bonus + HN score bonus",
            "Rank    Stories sorted by authenticity score. Below 0.25 threshold are dropped.",
        ]
        for step in steps:
            self.multi_cell(CONTENT_W, 4.5, self._t(step),
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(0.5)

        # ── Tier legend ────────────────────────────────────────────────────────
        self.ln(4)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_NAVY)
        self.cell(0, 6, "Authenticity Tiers", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for colour, tier, desc in [
            (C_VERIFIED,  "VERIFIED   0.80 - 1.00", "3+ independent sources including media"),
            (C_CONFIRMED, "CONFIRMED  0.50 - 0.79", "2 sources or 1 high-quality media outlet"),
            (C_EMERGING,  "EMERGING   0.25 - 0.49", "Single-source; passes AI keyword filter"),
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

    # ── Source breakdown ───────────────────────────────────────────────────────

    def source_table(self, articles):
        """Compact source breakdown table on a new page."""
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
        # Header
        self._fc(*C_NAVY)
        self.set_font(self._fn, "B", 7.5)
        self._tc(*C_WHITE)
        for i, hdr in enumerate(["Source", "Articles", "Category"]):
            self.cell(col[i], 6, hdr, fill=True)
        self.ln()
        # Rows
        alt = False
        for source, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            self._fc(*(C_BG_ALT if alt else C_WHITE))
            cat    = "Community" if source in ("HackerNews",) or "Reddit" in source else "Media"
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

    # ── Section header ────────────────────────────────────────────────────────

    def section_header(self, label, count, colour):
        """Full-width coloured section banner."""
        self.ln(3)
        self._fc(*colour)
        y = self.get_y()
        self.rect(0, y, PAGE_W, 8, "F")
        self.set_font(self._fn, "B", 8.5)
        self._tc(*C_WHITE)
        self.cell(0, 8,
                  self._t(f"  {label.upper()}  —  {count} {'story' if count == 1 else 'stories'}"),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._tc(*C_BODY)
        self.ln(2)

    # ── Article card (flow-only layout) ───────────────────────────────────────

    def _estimate_card_height(self, article):
        """
        Estimate the card height in mm so we can trigger a page break
        before rendering instead of mid-card.
        """
        title      = article.get("title", "")
        summary    = article.get("summary", "")
        # title: ~11 chars/mm at 9pt bold over CONTENT_W-12mm = ~170 chars/line → ceil lines * 5mm
        title_lines = max(1, (len(title) // 85) + 1)
        summ_lines  = max(0, (len(summary) // 95) + 1) if summary else 0
        return 6 + title_lines * 5 + 5 + summ_lines * 4.5 + 5 + 4  # header+title+meta+summary+url+padding

    def article_card(self, article, index, alt_bg=False):  # pylint: disable=too-many-locals,too-many-statements
        """
        Render one article card using pure flow layout.
        A pre-flight height check is done by the caller — this method
        never uses set_xy or absolute Y positions.
        """
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

        # ── Left tier stripe rendered as a narrow coloured rect ──────────────
        # We draw it after we know the full card height; here we use ln-based flow
        # and draw a stripe using a rect before the first cell.
        card_top = self.get_y()

        # Index + tier dot row
        self.set_font(self._fn, "B", 7)
        self._tc(*C_MUTED)
        self.set_fill_color(*bg)
        self.cell(8, 5, str(index), fill=True)
        self._tc(*tier_colour)
        self._fc(*tier_colour)
        self.cell(12, 5, self._t(f"  {tier_label[:4]}"), fill=False,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # ── Title ─────────────────────────────────────────────────────────────
        self.set_x(L_MAR + 6)
        self.set_font(self._fn, "B", 9)
        self._tc(*C_NAVY)
        self._fc(*bg)
        self.multi_cell(CONTENT_W - 6, 5, self._t(title),
                        fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # ── Meta row: source badge | extra sources | auth % | HN score ────────
        self.set_x(L_MAR + 6)
        # Source badge
        self._fc(*badge_clr)
        self.set_font(self._fn, "B", 6)
        self._tc(*C_WHITE)
        badge = self._t(source[:30])
        bw    = self.get_string_width(badge) + 4
        self.cell(bw, 4.5, badge, fill=True)
        # Cross-source count
        if n_src > 1:
            self.set_font(self._fn, size=6.5)
            self._tc(*tier_colour)
            self._fc(*bg)
            self.cell(38, 4.5,
                      self._t(f"  +{n_src-1} more source{'s' if n_src > 2 else ''}"),
                      fill=True)
        # Auth percentage (right side)
        self._fc(*tier_colour)
        self._tc(*C_WHITE)
        self.set_font(self._fn, "B", 6)
        auth_txt = self._t(f" {auth:.0%} ")
        self.cell(self.get_string_width(auth_txt) + 2, 4.5, auth_txt, fill=True)
        # HN score if notable
        if score > 0:
            self._fc(*bg)
            self._tc(*C_MUTED)
            self.set_font(self._fn, size=6.5)
            self.cell(22, 4.5, self._t(f"  HN {score}"), fill=True)
        self.ln(4.5)

        # ── Summary ───────────────────────────────────────────────────────────
        if summary:
            self.set_x(L_MAR + 6)
            self.set_font(self._fn, size=7.5)
            self._tc(60, 65, 88)
            self._fc(*bg)
            self.multi_cell(CONTENT_W - 6, 4.5, self._t(summary),
                            fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            self.set_x(L_MAR + 6)
            self.set_font(self._fn, "B", 7)
            self._tc(*C_MUTED)
            self._fc(*bg)
            self.cell(0, 4.5, "No summary available — click link for full article.",
                      fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # ── URL ───────────────────────────────────────────────────────────────
        self.set_x(L_MAR + 6)
        self.set_font(self._fn, size=6.5)
        self._tc(*C_URL)
        self._fc(*bg)
        display_url = url if len(url) <= 90 else url[:87] + "..."
        self.cell(0, 4.5, self._t(display_url),
                  fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Left tier stripe (drawn retroactively over left margin)
        card_bottom = self.get_y()
        self._fc(*tier_colour)
        self.rect(L_MAR, card_top, 2.5, card_bottom - card_top, "F")

        # Bottom divider
        self._dc(*C_DIVIDER)
        self.line(L_MAR, self.get_y(), PAGE_W - R_MAR, self.get_y())
        self.ln(3)
        self._tc(*C_BODY)


# ── History ───────────────────────────────────────────────────────────────────

def load_history():
    """Return set of already-reported article IDs."""
    if HISTORY_FILE.exists():
        return {l.strip() for l in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}
    return set()


def update_history(ids):
    """Append reported IDs to history log."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for item_id in ids:
            f.write(f"{item_id}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_report():
    """Generate the premium PDF intelligence report. Returns PDF path or None."""
    if not NEWS_FILE.exists():
        log.error("news_feed.json missing — run scraper first.")
        return None
    try:
        data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON: %s", exc)
        raise

    articles  = data.get("articles", []) if isinstance(data, dict) else data
    raw_count = data.get("meta", {}).get("raw_count", len(articles)) if isinstance(data, dict) else len(articles)

    if not articles:
        log.info("No articles — skipping PDF.")
        return None

    history     = load_history()
    new_arts    = [a for a in articles if a.get("id", a.get("url", "")) not in history]
    if not new_arts:
        log.info("All %d already reported — reusing all for today's report.", len(articles))
        new_arts = articles   # always produce a PDF for email

    verified  = sum(1 for a in new_arts if a.get("authenticity_score", 0) >= 0.8)
    confirmed = sum(1 for a in new_arts if 0.5 <= a.get("authenticity_score", 0) < 0.8)
    emerging  = sum(1 for a in new_arts if a.get("authenticity_score", 0) < 0.5)
    src_hit   = len({s for a in new_arts for s in a.get("all_sources", [a.get("source", "")])})

    issue_date = datetime.now().strftime("%d %B %Y")
    pdf = NeoSignalPDF(issue_date)

    # Page 1 — cover
    pdf.cover_page(len(new_arts), verified, confirmed, emerging, src_hit, raw_count)

    # Page 2 — source table
    pdf.source_table(new_arts)

    # Pages 3+ — tiered articles
    tiers = [
        ("Verified Intelligence", [a for a in new_arts if a.get("authenticity_score", 0) >= 0.8],    C_VERIFIED),
        ("Confirmed Signals",     [a for a in new_arts if 0.5 <= a.get("authenticity_score", 0) < 0.8], C_CONFIRMED),
        ("Emerging Signals",      [a for a in new_arts if a.get("authenticity_score", 0) < 0.5],      C_EMERGING),
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
