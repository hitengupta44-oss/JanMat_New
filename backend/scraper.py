"""
Discovery layer: finds *which* URLs to ingest. Actual full-text extraction
lives in pdf_ingest.py; this module's only job is producing a list of
(url, kind, source, title, metadata) tuples to hand off.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

import tinyfish_client

logger = logging.getLogger("janmat.scraper")

USER_AGENT = "JanMatBot/0.2 (+non-commercial civic-tech RAG chatbot)"


@dataclass
class DiscoveredDocument:
    url: str
    kind: str            # 'bill_pdf' | 'bill_page' | 'article' | 'public_opinion'
    source: str
    title: str
    metadata: dict = field(default_factory=dict)
    text: Optional[str] = None   # pre-extracted text (skips fetching), e.g. from the TinyFish agent


class PRSDiscovery:
    """
    Walks the PRS billtrack listing, then for each bill page discovers:
      - the bill_page itself (HTML, always ingested)
      - any PDF(s) linked from that page (the actual legislative brief —
        this is the "read the PDF completely" source)
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _get(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        time.sleep(self.cfg.get("rate_limit_seconds", 2))
        return resp

    def discover_bill_pages(self) -> List[DiscoveredDocument]:
        link_pattern = re.compile(self.cfg["bill_link_pattern"])
        exclude_prefixes = self.cfg["bill_link_exclude_prefixes"]

        resp = self._get(self.cfg["listing_url"])
        soup = BeautifulSoup(resp.text, "lxml")

        docs, seen = [], set()
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            link = heading.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            path = href if href.startswith("/") else href.replace(self.cfg["base_url"], "", 1)
            if any(path.startswith(p) for p in exclude_prefixes):
                continue
            if not link_pattern.match(path):
                continue

            url = href if href.startswith("http") else self.cfg["base_url"] + href
            if url in seen:
                continue
            seen.add(url)

            status = None
            node = heading.find_next_sibling()
            while node is not None and not node.get_text(strip=True):
                node = node.find_next_sibling()
            if node is not None and node.name not in ("h1", "h2", "h3", "h4", "h5", "h6"):
                status = node.get_text(strip=True)

            docs.append(
                DiscoveredDocument(
                    url=url,
                    kind="bill_page",
                    source="prs",
                    title=link.get_text(strip=True),
                    metadata={"bill_status": status} if status else {},
                )
            )

        limit = self.cfg.get("max_bills_per_run")
        return docs[:limit] if limit else docs

    def discover_pdfs_from_bill_page(self, bill_doc: DiscoveredDocument, pdf_links: List[str]) -> List[DiscoveredDocument]:
        return [
            DiscoveredDocument(
                url=pdf_url,
                kind="bill_pdf",
                source="prs",
                title=f"{bill_doc.title} — full brief (PDF)",
                metadata={**bill_doc.metadata, "parent_bill_url": bill_doc.url},
            )
            for pdf_url in pdf_links
        ]


def discover_article_seed_urls(seed_urls: List[str]) -> List[DiscoveredDocument]:
    """
    Static seed list of news/opinion URLs (from config.py). For a production
    setup, replace this with a real news-source crawler or an RSS/Google
    News query per bill topic — this MVP keeps it explicit and reviewable so
    nothing gets ingested from a source you haven't vetted.
    """
    return [
        DiscoveredDocument(url=u, kind="article", source="seed_list", title=u)
        for u in seed_urls
    ]


def discover_via_tinyfish_search(queries: List[str], per_query: int = 5) -> List[DiscoveredDocument]:
    """Search API: finds extra drafts, news and stakeholder reactions on the live web."""
    docs, seen = [], set()
    for q in queries:
        try:
            hits = tinyfish_client.search(q, max_results=per_query)
        except Exception as exc:
            logger.warning("TinyFish search failed for %r: %s", q, exc)
            continue
        for h in hits:
            if h["url"] in seen:
                continue
            seen.add(h["url"])
            docs.append(DiscoveredDocument(url=h["url"], kind="article", source="tinyfish_search", title=h["title"],
                                           metadata={"found_by_query": q}))
    return docs


def discover_comment_documents(pages: List[DiscoveredDocument]) -> List[DiscoveredDocument]:
    """Agent API: opens each page, extracts every public comment as structured
    data, and returns one 'public_opinion' document per page."""
    docs = []
    for page in pages:
        try:
            comments = tinyfish_client.collect_comments(page.url)
        except Exception as exc:
            logger.warning("TinyFish agent failed on %s: %s", page.url, exc)
            continue
        if not comments:
            continue
        docs.append(DiscoveredDocument(
            url=f"{page.url}#stakeholder-comments", kind="public_opinion", source="tinyfish_agent",
            title=f"Stakeholder comments: {page.title}",
            metadata={"parent_bill_url": page.url, "comment_count": len(comments)},
            text=tinyfish_client.comments_to_text(page.title, comments)))
    return docs
