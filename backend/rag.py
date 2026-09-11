"""
The chatbot's brain: embed the question, retrieve a broad set of relevant
chunks (hybrid vector + keyword search) from Supabase, and ask the LLM to
write a genuinely generative answer grounded in that material — not a
templated or copy-pasted response — citing which document each part came
from.
"""
import logging
import re
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
- Explain the substance in your own words. Short quoted phrases are fine where \
the exact legal wording matters, but don't string together long verbatim passages \
from the source text — the point is to make the material understandable, not to \
reproduce it.
- Only cite a source if you actually used it for that claim. Don't add citations \
to look thorough.
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


def _extract_cited_numbers(answer: str, max_n: int) -> List[int]:
    """
    Find which source numbers the model actually cited, e.g. [1], [2,3],
    [4, 5]. Returns them sorted and de-duplicated, ignoring any number
    outside the range of sources we actually supplied.
    """
    cited = set()
    for group in re.findall(r"\[([\d\s,]+)\]", answer):
        for part in group.split(","):
            part = part.strip()
            if part.isdigit():
                n = int(part)
                if 1 <= n <= max_n:
                    cited.add(n)
    return sorted(cited)


def _renumber_answer(answer: str, old_to_new: dict) -> str:
    """
    After dropping uncited sources, the surviving ones are renumbered 1..N.
    Rewrite the markers in the answer text to match, so [12] becomes [3] if
    source 12 is now the third in the list.
    """
    def replace(match):
        seen = []
        for part in match.group(1).split(","):
            part = part.strip()
            if part.isdigit() and int(part) in old_to_new:
                new = str(old_to_new[int(part)])
                # Two chunks from the same document map to the same new
                # number — don't emit "[1,1]".
                if new not in seen:
                    seen.append(new)
        return f"[{','.join(seen)}]" if seen else ""

    return re.sub(r"\[([\d\s,]+)\]", replace, answer)


def answer_question(session_id: str, question: str, filter_kind: Optional[str] = None) -> dict:
    """
    Returns:
      {"answer": str, "citations": [{"n": 1, "title":.., "url":.., "kind":.., "document_id":..}], "chunks_used": int}
    Note: `citations` contains only the sources the model actually cited in
    its answer — not every chunk that was retrieved. Retrieval deliberately
    pulls a broad set of candidates (TOP_K_CHUNKS) so the model has enough
    context to work with, but listing all of them under the answer would be
    misleading: most retrieved chunks don't end up informing the response.
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

    # Keep only the sources the model actually cited. Multiple chunks often
    # come from the same document, so also de-duplicate by URL — citing the
    # same PDF three times as [2], [7], [13] is noise, not precision.
    cited_numbers = _extract_cited_numbers(answer, len(chunks))

    citations = []
    old_to_new = {}
    seen_urls = {}
    for n in cited_numbers:
        c = chunks[n - 1]
        url = c["url"]
        if url in seen_urls:
            # Already citing this document — point this marker at the
            # existing entry instead of adding a duplicate.
            old_to_new[n] = seen_urls[url]
            continue
        new_n = len(citations) + 1
        seen_urls[url] = new_n
        old_to_new[n] = new_n
        citations.append(
            {
                "n": new_n,
                "document_id": c["document_id"],
                "title": c["title"],
                "url": url,
                "kind": c["kind"],
                "page_number": c.get("page_number"),
            }
        )

    answer = _renumber_answer(answer, old_to_new)

    return {"answer": answer, "citations": citations, "chunks_used": len(chunks)}
