"""
TinyFish integration: three small wrappers over TinyFish's public REST APIs.

  fetch_text(url)       Fetch API   real-browser fetch -> clean markdown text
                                    (also extracts PDF text). Free within TinyFish's
                                    daily allowance.
  search(query)         Search API  ranked web results (title, snippet, url).
                                    Free within the daily allowance.
  collect_comments(url) Agent API   a natural-language goal on a live page; returns
                                    each stakeholder comment as structured data.
                                    Billed from your TinyFish wallet, so cap its use.

Every function is a no-op / raises cleanly when TINYFISH_API_KEY is not set, so
the rest of JanMat keeps working without it.
"""
import logging
from typing import List, Optional

import requests

from config import TINYFISH_API_KEY

logger = logging.getLogger("janmat.tinyfish")

FETCH_URL = "https://api.fetch.tinyfish.ai"
SEARCH_URL = "https://api.search.tinyfish.ai"
AGENT_RUN_URL = "https://agent.tinyfish.ai/v1/automation/run"

COMMENTS_GOAL = (
    "Read this page and list every public stakeholder comment, submission or "
    "response shown on it. Return JSON shaped like "
    '{"comments": [{"stakeholder": "<name or organisation>", "comment": "<full comment text>"}]}. '
    "Only use what is visible without logging in. Do not click submit, sign in, "
    "or post anything."
)


def enabled() -> bool:
    return bool(TINYFISH_API_KEY)


def _headers() -> dict:
    if not TINYFISH_API_KEY:
        raise RuntimeError("TINYFISH_API_KEY is not set")
    return {"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"}


def fetch_text(url: str, timeout: int = 90) -> dict:
    """Returns {"title", "text", "final_url"}. Raises if TinyFish cannot fetch it."""
    resp = requests.post(FETCH_URL, headers=_headers(), json={"urls": [url], "format": "markdown"}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"TinyFish Fetch returned no content for {url}: {(data.get('errors') or [])[:1]}")
    page = results[0]
    text = (page.get("text") or "").strip()
    if not text:
        raise RuntimeError(f"TinyFish Fetch returned empty text for {url}")
    return {
        "title": page.get("title") or url.rsplit("/", 1)[-1],
        "text": text,
        "final_url": page.get("final_url") or url,
    }


def search(query: str, max_results: int = 5) -> List[dict]:
    """Returns [{"url", "title", "snippet"}, ...]."""
    resp = requests.get(SEARCH_URL, headers=_headers(), params={"query": query}, timeout=30)
    resp.raise_for_status()
    out = []
    for item in (resp.json().get("results") or [])[:max_results]:
        url = item.get("url") or item.get("link")
        if url:
            out.append({"url": url, "title": item.get("title") or url, "snippet": item.get("snippet") or ""})
    return out


def collect_comments(url: str, timeout: int = 300) -> List[dict]:
    """
    Runs one Agent API automation on `url` and returns
    [{"stakeholder": str, "comment": str}, ...]. Empty list if nothing found.
    """
    resp = requests.post(AGENT_RUN_URL, headers=_headers(), json={"url": url, "goal": COMMENTS_GOAL}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "COMPLETED":
        raise RuntimeError(f"TinyFish agent run did not complete for {url}: {data.get('status')}")
    result = data.get("result") or {}
    # A JSON object arrives directly; a bare list/text arrives under result["result"].
    items = result.get("comments") if isinstance(result, dict) else None
    if items is None and isinstance(result, dict):
        items = result.get("result")
    if not isinstance(items, list):
        return []
    cleaned = []
    for it in items:
        if isinstance(it, dict) and str(it.get("comment") or "").strip():
            cleaned.append({"stakeholder": str(it.get("stakeholder") or "Unnamed").strip(), "comment": str(it["comment"]).strip()})
    return cleaned


def comments_to_text(title: str, comments: List[dict]) -> str:
    blocks = [f"Stakeholder comments: {title}"]
    for c in comments:
        blocks.append(f"Stakeholder: {c['stakeholder']}\nComment: {c['comment']}")
    return "\n\n".join(blocks)
