"""
Central config for the JanMat RAG chatbot backend.

Everything secret comes from the environment (HF Space repository secrets in
prod, .env locally — see .env.example). Nothing here should hold a real key.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # harmless no-op if you never create a .env file

import os
from dotenv import load_dotenv

load_dotenv()  # harmless no-op if you never create a .env file — see note below

# ==============================================================================
# All secrets are read from environment variables, NEVER hardcoded here.
# This file is safe to commit to GitHub (public or private) as-is.
#
# Where the environment variables actually come from depends on where you run:
#   - Locally: `export SUPABASE_URL="..."` etc. in your terminal before running
#     `python main.py` (see MIGRATION_GUIDE.md for the exact commands).
#   - Hugging Face Space: Settings -> Variables and secrets -> add each one
#     under "Secrets". HF injects them as environment variables automatically
#     at runtime — nothing in this file needs to change.
# ==============================================================================

# --- Supabase (knowledge base + chat history) --------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # service_role key, backend-only

# --- Groq (answer generation) -------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")

# --- Sarvam AI (voice: speech-to-text + text-to-speech) -----------------------
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_DEFAULT_SPEAKER = os.getenv("SARVAM_DEFAULT_SPEAKER", "anushka")
SARVAM_DEFAULT_LANGUAGE = os.getenv("SARVAM_DEFAULT_LANGUAGE", "en-IN")

# --- Cron / admin protection ---------------------------------------------------
CRON_SECRET = os.getenv("CRON_SECRET", "")

# --- Embedding model (local, free, no API key needed) -------------------------
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIM = 384

# --- Chunking -------------------------------------------------------------------
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "220"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))

# --- Retrieval / generation -------------------------------------------------------
# Broader than a typical minimal RAG setup: more candidate chunks per query,
# and a larger context budget, so answers draw on more of the ingested
# material per question rather than a bare top-5. Still cheap — this is a
# few dozen KB of text per Groq call, not the whole knowledge base.
TOP_K_CHUNKS = int(os.getenv("TOP_K_CHUNKS", "20"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "20000"))

# --- Sources to ingest ------------------------------------------------------------
CONFIG = {
    "prs": {
        "name": "PRS Legislative Research",
        "base_url": "https://prsindia.org",
        "listing_url": "https://prsindia.org/billtrack",
        "bill_link_pattern": r"^/billtrack/[^/]+$",
        "bill_link_exclude_prefixes": ("/billtrack/category/", "/billtrack/field_bill_category/"),
        "rate_limit_seconds": 2,
        "max_bills_per_run": 25,
        "license_note": (
            "PRS's disclaimer permits reproduction for non-commercial purposes "
            "with due acknowledgement of PRS Legislative Research."
        ),
    },
    # Add more sources here as plain "seed URL lists" — the ingestion pipeline
    # treats any HTTP(S) URL the same way: fetch, detect PDF vs HTML, extract
    # full text, chunk, embed, store. See scraper.py:ArticleSource.
    "article_seed_urls": [
        # "https://example-news-site.com/article-about-a-bill",
    ],
}
