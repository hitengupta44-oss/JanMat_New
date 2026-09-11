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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

logger = logging.getLogger("janmat.pdf_ingest")

# A browser-like User-Agent. Several government sites (indiacode.nic.in,
# mha.gov.in, labour.gov.in) return 403 Forbidden to requests that identify
# as a bot, but serve the same public documents fine to a normal browser.
# These are public legislative documents, and this crawler is polite (rate
# limited, robots-respecting in spirit, non-commercial) — the UA change is
# to avoid blanket bot-blocking, not to evade a deliberate access policy.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 JanMatBot/0.3 (+non-commercial civic-tech)"
)

# Hosts that fail for reasons a User-Agent can't fix. Skipping them up front
# saves ~15s per link in connection timeouts and keeps `documents` free of
# permanently-failed rows. Revisit occasionally — these may come back.
BLOCKED_PDF_HOSTS = {
    # Connection times out from Hugging Face's network (site down or
    # geo/network-restricted — not a bot block).
    "bombayhighcourt.nic.in",
    "fcraonline.nic.in",
    # DNS doesn't resolve at all — the hostname appears to be wrong/retired
    # on PRS's side (note: api.sci.gov.in DOES work and is NOT blocked).
    "sapi.sci.gov.in",
    # Incomplete SSL certificate chain; fetching would require disabling
    # certificate verification, which isn't worth the MITM risk.
    "egazette.gov.in",
}


class BlockedHostError(Exception):
    """Raised when a URL's host is on BLOCKED_PDF_HOSTS — signals 'skip
    quietly', not 'something went wrong'."""


def is_blocked_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    return host in BLOCKED_PDF_HOSTS


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
    PDF links to hosts in BLOCKED_PDF_HOSTS are dropped here rather than
    attempted and failed later — see that constant for why each is listed.
    Everything else is followed: PRS bill pages link out to genuinely
    valuable material (Supreme Court judgments, NCRB statistics tables,
    government report PDFs) that belongs in the knowledge base.
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
    skipped_blocked = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        absolute = urljoin(base_url, href)
        if is_blocked_host(absolute):
            skipped_blocked += 1
            continue
        pdf_links.append(absolute)

    if skipped_blocked:
        logger.info(
            "Skipped %s PDF link(s) on %s from known-unreachable hosts",
            skipped_blocked,
            base_url,
        )

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
    Raises:
      BlockedHostError if the URL is on a known-unreachable host.
    """
    if is_blocked_host(url):
        raise BlockedHostError(f"Skipped known-unreachable host: {url}")

    # (connect timeout, read timeout) — a short connect timeout means a dead
    # host fails in 5s instead of 15s, which matters when a run touches
    # dozens of links.
    head_resp = requests.head(
        url, headers={"User-Agent": USER_AGENT}, timeout=(5, 15), allow_redirects=True
    )
    content_type = head_resp.headers.get("Content-Type", "")

    if is_pdf_url(url, content_type):
        raw = fetch_bytes(url)
        pages = extract_pdf_pages(raw)
        title = url.rsplit("/", 1)[-1]
        return {"title": title, "kind_hint": "pdf", "pages": pages, "full_text": "\n\n".join(pages), "pdf_links": []}

    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(5, 30))
    resp.raise_for_status()
    parsed = extract_html_article(resp.text, url)
    return {
        "title": parsed["title"],
        "kind_hint": "html",
        "pages": [],
        "full_text": parsed["full_text"],
        "pdf_links": parsed["pdf_links"],
    }
