#!/usr/bin/env python3
# PDF Report Generator for AI News Syndicate
# Uses fpdf2 for PDF generation

import json
import os
from datetime import datetime
from fpdf import FPDF

# Constants
NEWS_FEED_PATH = "news_feed.json"
HISTORY_LOG_PATH = "history.log"
REPORTS_DIR = "reports"

# Initialize PDF class
class PDFReport(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, f"AI News Syndicate Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1, "C")
        self.ln(10)

    def chapter_title(self, title):
        self.set_font("Arial", "B", 10)
        self.cell(0, 10, title, 0, 1)
        self.ln(5)

    def chapter_body(self, body):
        self.set_font("Arial", size=8)
        self.multi_cell(0, 5, body)
        self.ln(5)

# Load history log
def load_history():
    if os.path.exists(HISTORY_LOG_PATH):
        with open(HISTORY_LOG_PATH, "r") as f:
            return set(line.strip() for line in f)
    return set()

# Update history log
def update_history(new_urls):
    with open(HISTORY_LOG_PATH, "a") as f:
        for url in new_urls:
            f.write(f"{url}\n")

# Generate PDF report
def generate_pdf_report():
    # Load data
    with open(NEWS_FEED_PATH, "r") as f:
        data = json.load(f)
    
    history = load_history()
    new_articles = [
        article for article in data["news_feed"]
        if article["url"] not in history
    ]
    
    if not new_articles:
        print("No new articles to report.")
        return
    
    # Create PDF
    pdf = PDFReport()
    pdf.add_page()
    
    for article in new_articles:
        pdf.chapter_title(article["title"])
        pdf.chapter_body(
            f"Source: {article['source']}\n"
            f"URL: {article['url']}\n"
            f"Date: {article['date']}\n"
            f"Tag: {article['tag']}\n\n"
            f"Snippet: {article['snippet']}"
        )
    
    # Save PDF
    os.makedirs(REPORTS_DIR, exist_ok=True)
    pdf_path = os.path.join(REPORTS_DIR, f"ai_news_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
    pdf.output(pdf_path)
    
    # Update history
    update_history([article["url"] for article in new_articles])
    
    print(f"PDF report generated: {pdf_path}")
    return pdf_path

if __name__ == "__main__":
    generate_pdf_report()