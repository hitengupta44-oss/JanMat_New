"""
All Supabase reads/writes go through this module — talking directly to
Supabase's auto-generated REST API (PostgREST) with plain `requests` calls,
rather than the `supabase-py` package.

Why not supabase-py: it pulls in a `realtime` dependency that needs a newer
`websockets` version than Gradio's pinned version supports, causing a
`ModuleNotFoundError: No module named 'websockets.asyncio'` crash on HF
Spaces. We don't use any realtime features here (no live subscriptions),
so talking to the REST API directly avoids the conflict entirely and keeps
the dependency list smaller.
"""
import hashlib
import logging
from typing import List, Optional

import requests

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

logger = logging.getLogger("janmat.db")


def _base_url() -> str:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1"


def _headers(prefer: Optional[str] = None) -> dict:
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _raise_for_status(resp: requests.Response):
    if not resp.ok:
        raise RuntimeError(f"Supabase REST error {resp.status_code}: {resp.text[:500]}")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ documents

def find_document_by_url(url: str) -> Optional[dict]:
    resp = requests.get(
        f"{_base_url()}/documents",
        headers=_headers(),
        params={"url": f"eq.{url}", "select": "*", "limit": 1},
        timeout=20,
    )
    _raise_for_status(resp)
    rows = resp.json()
    return rows[0] if rows else None


def upsert_document(*, source: str, kind: str, title: str, url: str,
                     full_text_sha256: str, metadata: Optional[dict] = None,
                     published_at: Optional[str] = None) -> dict:
    """Insert or update a document row by its unique URL. Returns the row."""
    payload = {
        "source": source,
        "kind": kind,
        "title": title,
        "url": url,
        "full_text_sha256": full_text_sha256,
        "metadata": metadata or {},
        "status": "ingested",
        "error": None,
    }
    if published_at:
        payload["published_at"] = published_at

    resp = requests.post(
        f"{_base_url()}/documents",
        headers=_headers(prefer="resolution=merge-duplicates,return=representation"),
        params={"on_conflict": "url"},
        json=payload,
        timeout=30,
    )
    _raise_for_status(resp)
    rows = resp.json()
    return rows[0]


def mark_document_failed(url: str, source: str, kind: str, title: str, error: str) -> None:
    payload = {
        "url": url,
        "source": source,
        "kind": kind,
        "title": title,
        "status": "failed",
        "error": error[:2000],
    }
    resp = requests.post(
        f"{_base_url()}/documents",
        headers=_headers(prefer="resolution=merge-duplicates,return=representation"),
        params={"on_conflict": "url"},
        json=payload,
        timeout=30,
    )
    _raise_for_status(resp)


def delete_chunks_for_document(document_id: int) -> None:
    resp = requests.delete(
        f"{_base_url()}/chunks",
        headers=_headers(),
        params={"document_id": f"eq.{document_id}"},
        timeout=30,
    )
    _raise_for_status(resp)


# --------------------------------------------------------------------- chunks

def insert_chunks(document_id: int, chunks: List[dict]) -> int:
    """
    chunks: [{"chunk_index": int, "content": str, "token_count": int,
              "page_number": int|None, "embedding": list[float]}, ...]
    Batches in groups of 200 to stay well under request-size limits.
    """
    rows = [{"document_id": document_id, **c} for c in chunks]
    batch_size = 200
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        resp = requests.post(
            f"{_base_url()}/chunks",
            headers=_headers(prefer="return=minimal"),
            json=batch,
            timeout=60,
        )
        _raise_for_status(resp)
        inserted += len(batch)
    return inserted


def match_chunks(query_embedding: List[float], query_text: str = "", match_count: int = 20,
                  filter_kind: Optional[str] = None) -> List[dict]:
    """Calls the match_chunks() Postgres function defined in schema.sql via RPC.
    Passes both the embedding (vector similarity) and the raw question text
    (trigram keyword similarity) — the SQL function blends both scores, so
    retrieval isn't purely semantic-vector and catches exact term matches
    (bill names, section numbers) that embeddings alone sometimes miss."""
    resp = requests.post(
        f"{_base_url()}/rpc/match_chunks",
        headers=_headers(),
        json={
            "query_embedding": query_embedding,
            "query_text": query_text,
            "match_count": match_count,
            "filter_kind": filter_kind,
        },
        timeout=30,
    )
    _raise_for_status(resp)
    return resp.json() or []


# --------------------------------------------------------------- chat memory

def create_session(label: Optional[str] = None) -> str:
    resp = requests.post(
        f"{_base_url()}/chat_sessions",
        headers=_headers(prefer="return=representation"),
        json={"label": label},
        timeout=20,
    )
    _raise_for_status(resp)
    return resp.json()[0]["id"]


def get_recent_messages(session_id: str, limit: int = 8) -> List[dict]:
    resp = requests.get(
        f"{_base_url()}/chat_messages",
        headers=_headers(),
        params={
            "session_id": f"eq.{session_id}",
            "select": "role,content,created_at",
            "order": "created_at.desc",
            "limit": limit,
        },
        timeout=20,
    )
    _raise_for_status(resp)
    return list(reversed(resp.json() or []))


def save_message(session_id: str, role: str, content: str,
                  citations: Optional[list] = None, input_mode: str = "text",
                  language_code: Optional[str] = None) -> None:
    payload = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "citations": citations or [],
        "input_mode": input_mode,
        "language_code": language_code,
    }
    resp = requests.post(
        f"{_base_url()}/chat_messages",
        headers=_headers(prefer="return=minimal"),
        json=payload,
        timeout=20,
    )
    _raise_for_status(resp)


def list_documents(limit: int = 200) -> List[dict]:
    resp = requests.get(
        f"{_base_url()}/documents",
        headers=_headers(),
        params={
            "select": "id,title,url,kind,source,status,fetched_at,metadata",
            "order": "fetched_at.desc",
            "limit": limit,
        },
        timeout=20,
    )
    _raise_for_status(resp)
    return resp.json() or []


# ------------------------------------------------------------- ingestion log

def start_ingestion_run(started_at: str) -> int:
    resp = requests.post(
        f"{_base_url()}/ingestion_runs",
        headers=_headers(prefer="return=representation"),
        json={"started_at": started_at, "status": "running"},
        timeout=20,
    )
    _raise_for_status(resp)
    return resp.json()[0]["id"]


def finish_ingestion_run(run_id: int, finished_at: str, status: str, detail: dict) -> None:
    resp = requests.patch(
        f"{_base_url()}/ingestion_runs",
        headers=_headers(prefer="return=minimal"),
        params={"id": f"eq.{run_id}"},
        json={"finished_at": finished_at, "status": status, "detail": detail},
        timeout=20,
    )
    _raise_for_status(resp)
