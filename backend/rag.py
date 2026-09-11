"""
The chatbot's brain: embed the question, retrieve a broad set of relevant
chunks (hybrid vector + keyword search) from Supabase, and ask the LLM to
write a genuinely generative answer grounded in that material — not a
templated or copy-pasted response — citing which document each part came
from.
"""
import logging
from typing import List, Optional

import requests

import db
from config import GROQ_API_KEY, GROQ_CHAT_MODEL, TOP_K_CHUNKS, MAX_CONTEXT_CHARS
from embeddings import embed_query

logger = logging.getLogger("janmat.rag")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are JanMat, an assistant that answers questions about Indian \
legislative bills, their PRS Legislative Research briefs, related news articles, and \
public opinion submissions.

Rules:
- Answer using the numbered SOURCE excerpts provided below. Do not invent facts that \
aren't supported by them.
- Write a genuinely thought-out, generative answer in your own words — synthesise \
across the sources, explain context and implications, and structure the answer to \
actually help the reader understand the topic. Do not just copy or lightly rephrase a \
single source's sentence.
- If the sources give a fuller picture together than any one of them alone, weave that \
together rather than picking one source and ignoring the rest.
- After each claim, cite the source number(s) it came from, like [1] or [2,3].
- If the sources don't contain enough information to answer, say so plainly instead of \
guessing.
- Keep the answer in plain, accessible language — assume the reader is a citizen, not \
a lawyer or policy expert.
- If sources disagree (e.g. a bill's official text vs. a news article's framing vs. a \
public comment), point that out rather than picking one silently.
"""


def _format_context(chunks: List[dict]) -> str:
    parts = []
    total = 0
    for i, c in enumerate(chunks, start=1):
        header = f"[{i}] {c['title']} ({c['kind']}, {c['url']}" + (
            f", page {c['page_number']})" if c.get("page_number") else ")"
        )
        block = f"{header}\n{c['content']}\n"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n---\n".join(parts)


def retrieve(question: str, top_k: int = TOP_K_CHUNKS, filter_kind: Optional[str] = None) -> List[dict]:
    """Hybrid retrieval: embeds the question for vector search, and passes the
    raw text too so Postgres can blend in trigram keyword matching — catches
    exact bill names / section numbers that a pure embedding search can miss,
    while still ranking mostly on semantic similarity."""
    query_vec = embed_query(question)
    return db.match_chunks(query_vec, query_text=question, match_count=top_k, filter_kind=filter_kind)


def _call_groq(messages: list, temperature: float = 0.3) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_CHAT_MODEL, "temperature": temperature, "messages": messages}
    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def answer_question(session_id: str, question: str, filter_kind: Optional[str] = None) -> dict:
    """
    Returns:
      {"answer": str, "citations": [{"n": 1, "title":.., "url":.., "kind":.., "document_id":..}], "chunks_used": int}
    """
    chunks = retrieve(question, filter_kind=filter_kind)
    if not chunks:
        return {
            "answer": (
                "I don't have any ingested bill text, PDFs, articles, or public "
                "opinions that match this question yet. Try asking about a bill "
                "that's already been ingested, or trigger an ingestion run."
            ),
            "citations": [],
            "chunks_used": 0,
        }

    context = _format_context(chunks)

    history = db.get_recent_messages(session_id, limit=6)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append(
        {
            "role": "user",
            "content": f"SOURCES:\n{context}\n\nQUESTION: {question}",
        }
    )

    answer = _call_groq(messages)

    citations = [
        {
            "n": i + 1,
            "document_id": c["document_id"],
            "title": c["title"],
            "url": c["url"],
            "kind": c["kind"],
            "page_number": c.get("page_number"),
        }
        for i, c in enumerate(chunks)
    ]

    return {"answer": answer, "citations": citations, "chunks_used": len(chunks)}
