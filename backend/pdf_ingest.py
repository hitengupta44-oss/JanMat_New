"""
Full-document text extraction — the "read through the scraped PDFs
completely" half of the pipeline. No summarization happens here; every page
of every PDF and every paragraph of every article is extracted and passed on
to be chunked+embedded whole. Summarization only happens later, at answer
time, over the small set of chunks actually retrieved for a given question.
"""
import io
import logging
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

logger = logging.getLogger("janmat.pdf_ingest")

USER_AGENT = "JanMatBot/0.2 (+non-commercial civic-tech RAG chatbot)"


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def is_pdf_url(url: str, content_type: str = "") -> bool:
    return url.lower().endswith(".pdf") or "application/pdf" in content_type.lower()


def extract_pdf_pages(pdf_bytes: bytes) -> List[str]:
    """Returns the full, uncompressed text of every page, in order."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # a single malformed page shouldn't kill the doc
            logger.warning("Failed extracting page %s: %s", i, exc)
            text = ""
        pages.append(text.strip())
    return pages


def extract_html_article(html: str, base_url: str) -> dict:
    """
    Full-text extraction from an HTML page (bill page or news article).
    Pulls every substantive paragraph/list item — no truncation, no
    "first N paragraphs" shortcut — plus any linked PDF hrefs found on the
    page, so a bill's legislative-brief PDF gets queued for ingestion too.
    """
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else base_url

    paragraphs = []
    for el in soup.find_all(["p", "li", "h1", "h2", "h3", "h4"]):
        text = el.get_text(strip=True)
        if len(text) >= 25:
            paragraphs.append(text)
    full_text = "\n\n".join(paragraphs)

    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            pdf_links.append(urljoin(base_url, href))

    return {"title": title, "full_text": full_text, "pdf_links": sorted(set(pdf_links))}


def ingest_source_document(url: str) -> dict:
    """
    Fetches whatever is at `url`, figures out if it's a PDF or HTML, and
    returns the full extracted text ready for chunking.

    Returns:
      {
        "title": str,
        "kind_hint": "pdf" | "html",
        "pages": [str, ...],       # for PDFs: one entry per page
        "full_text": str,          # for HTML: the whole extracted text
        "pdf_links": [str, ...],   # for HTML: any PDFs linked from the page
      }
    """
    head_resp = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=15, allow_redirects=True)
    content_type = head_resp.headers.get("Content-Type", "")

    if is_pdf_url(url, content_type):
        raw = fetch_bytes(url)
        pages = extract_pdf_pages(raw)
        title = url.rsplit("/", 1)[-1]
        return {"title": title, "kind_hint": "pdf", "pages": pages, "full_text": "\n\n".join(pages), "pdf_links": []}

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    parsed = extract_html_article(resp.text, url)
    return {
        "title": parsed["title"],
        "kind_hint": "html",
        "pages": [],
        "full_text": parsed["full_text"],
        "pdf_links": parsed["pdf_links"],
    }
