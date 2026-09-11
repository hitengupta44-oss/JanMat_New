"""
Embeddings, kept local and free: sentence-transformers/all-MiniLM-L6-v2 runs
fine on CPU and needs no API key, which matches this project's existing
free-tier-only stack (Groq for text, no paid vector DB, no GPU rental).

If you'd rather use a hosted embedding API (OpenAI, Cohere, Voyage, etc.),
swap embed_texts() below and update EMBEDDING_DIM + the `vector(384)` columns
in supabase/schema.sql to match the new dimension.
"""
import logging
from typing import List

from config import EMBEDDING_MODEL_NAME, CHUNK_WORDS, CHUNK_OVERLAP_WORDS

logger = logging.getLogger("janmat.embeddings")

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s (first call only)...", EMBEDDING_MODEL_NAME)
        # Force CPU explicitly: on ZeroGPU Spaces, torch reports a CUDA
        # device as available even outside an @spaces.GPU-decorated call,
        # which causes a crash the moment SentenceTransformer actually
        # tries to use it. This embedding model is tiny and runs fine on
        # CPU, so we never want it touching CUDA at all.
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS,
               overlap_words: int = CHUNK_OVERLAP_WORDS) -> List[str]:
    """
    Word-based sliding-window chunking. Simple and dependency-free; good
    enough for legislative-brief PDFs and news prose. Overlap keeps sentences
    that straddle a chunk boundary retrievable from either side.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_words:
        return [text.strip()]

    step = max(chunk_words - overlap_words, 1)
    chunks = []
    for start in range(0, len(words), step):
        piece = words[start : start + chunk_words]
        if not piece:
            continue
        chunks.append(" ".join(piece))
        if start + chunk_words >= len(words):
            break
    return chunks


def chunk_pages(pages: List[str], chunk_words: int = CHUNK_WORDS,
                 overlap_words: int = CHUNK_OVERLAP_WORDS) -> List[dict]:
    """
    Chunk a PDF that's already split into per-page text, preserving which
    page each chunk came from (so citations can say "page 4").
    Returns [{"content": str, "page_number": int}, ...] in reading order.
    """
    out = []
    for page_number, page_text in enumerate(pages, start=1):
        for piece in chunk_text(page_text, chunk_words, overlap_words):
            out.append({"content": piece, "page_number": page_number})
    return out
