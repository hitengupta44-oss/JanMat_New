# JanMat

**Ask questions about Indian legislation and see what stakeholders are saying about it.**

JanMat reads draft bills and their full PDF texts from [PRS Legislative Research](https://prsindia.org), stores every page in a searchable knowledge base, and does two things with it:

1. **Answers questions in plain language** through a chatbot, with each answer citing only the documents it actually used.
2. **Analyses stakeholder commentary** on draft legislation: sentiment per comment, thematic summaries, and word clouds.

It was built for **Smart India Hackathon 2025, problem statement SIH25035** (Ministry of Corporate Affairs: sentiment analysis of comments received through the eConsultation module), and goes beyond the brief by adding grounded question answering and voice.

---

## The idea

Public consultation only works if the feedback is actually absorbed. When a draft bill is opened for comment, the volume of submissions outruns what people can read, so substance gets archived rather than weighed. A citizen who wants to know what a bill does faces a different version of the same problem: long, technical documents spread over several sites.

JanMat's approach is to **read everything first, summarise later**:

- Documents are stored in full and chunked, never pre-summarised, so detail questions stay answerable months later.
- A question retrieves only the passages relevant to it, and the model writes an answer from those passages alone.
- If the corpus does not contain the answer, the system says so instead of inventing one.

---

## Features

| Feature | What it does |
|---|---|
| **Grounded Q&A** | Retrieval-augmented answers over bill text, PDFs and commentary. Markdown-formatted, with a short "Sources" list of the documents actually cited. |
| **Hybrid retrieval** | Blends vector similarity (75%) with trigram keyword matching (25%), so exact references such as bill names and section numbers are found alongside conceptual matches. Pulls 20 candidate chunks per question. |
| **Honest refusal** | Asked about something outside the corpus, it declines rather than fabricating. |
| **Voice in and out** | Speak a question (Sarvam AI speech-to-text) and hear the answer (text-to-speech). |
| **Consultation analysis** | Per-comment sentiment (score from -1 to +1) and one-line summary, theme clustering with written summaries, and weighted word clouds per bill and overall. |
| **Login and public comments** | Email and password accounts; signed-in users can post comments on a bill. Reading is open to everyone. |
| **Admin console** | Password-protected panel to run ingestion and analysis on demand and check status. |

---

## Architecture

Three independently deployed pieces. They share one Supabase project.

```
                         ┌──────────────────────────┐
   Browser ────────────► │  Vercel  (Next.js)       │
      │                  │  chat widget, login,     │
      │                  │  comments                │
      │                  └──────────┬───────────────┘
      │                             │ fetch()  /call/chat
      │                             ▼
      │                  ┌──────────────────────────┐        ┌─────────┐
      │                  │  Hugging Face Space      │ ─────► │  Groq   │  answers,
      │                  │  (Gradio, Python)        │        └─────────┘  sentiment
      │                  │  ingestion, RAG,         │        ┌─────────┐
      │                  │  analysis, voice         │ ─────► │ Sarvam  │  STT / TTS
      │                  └──────────┬───────────────┘        └─────────┘
      │                             │ REST (service_role key)
      │   anon key + RLS            ▼
      └─────────────────► ┌──────────────────────────┐
                          │  Supabase                │
                          │  Postgres + pgvector,    │
                          │  Auth                    │
                          └──────────────────────────┘
```

**Two separate credentials, on purpose.** The Space talks to Supabase with the powerful `service_role` key (kept as a Space secret, never sent to a browser). The Vercel site talks to Supabase with the `anon` key, which can only do what the Row Level Security policies in `supabase/schema.sql` allow.

### Data flow: ingestion

```
PRS bill listing → bill pages → linked PDFs → full-text extraction (pypdf / HTML)
   → overlapping chunks (220 words, 40 overlap) → local embeddings (MiniLM, 384-d)
   → Supabase: documents + chunks
```

### Data flow: a question

```
question → embed → hybrid search (top 20 chunks) → prompt Groq with numbered sources
   → keep only sources the answer cites → renumber and de-duplicate by URL
   → answer + "Sources" list
```

### Data flow: consultation analysis

```
stored bill pages → extract commentary paragraphs → sentiment + summary per comment (Groq)
   → cluster into themes (Groq) → word-cloud terms → dashboard tab
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 14, Tailwind, `react-markdown` + `remark-gfm`, `@supabase/supabase-js` |
| Backend | Python, Gradio 4.44, `requests`, BeautifulSoup + lxml, `pypdf` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2`, forced onto CPU |
| LLM | Groq (default model `openai/gpt-oss-20b`, configurable) |
| Voice | Sarvam AI (`saaras:v3` speech-to-text, `bulbul:v3` text-to-speech) |
| Database | Supabase Postgres with `pgvector` and `pg_trgm` |
| Auth | Supabase Auth, email and password |
| Hosting | Hugging Face Spaces, Vercel, Supabase (all free tiers) |

Everything runs on free tiers. Embeddings are computed locally, so indexing has no per-document API cost.

---

## Repository layout

```
janmat-v2/
├── README.md
├── supabase/
│   └── schema.sql            Run once in the Supabase SQL editor
├── backend/                  Deploy as a Hugging Face Space (SDK: gradio)
│   ├── README.md             Space config header, keep as-is (see Deployment)
│   ├── app.py                Gradio UI: chat, analysis dashboard, admin panel
│   ├── config.py             Settings, all secrets read from the environment
│   ├── db.py                 Supabase access via REST (no supabase-py)
│   ├── embeddings.py         Chunking and local embeddings
│   ├── pdf_ingest.py         Full-text extraction, host blocklist
│   ├── scraper.py            PRS bill discovery
│   ├── ingest_pipeline.py    Discover, extract, chunk, embed, store
│   ├── rag.py                Hybrid retrieval, answer generation, citations
│   ├── voice.py              Sarvam speech-to-text and text-to-speech
│   ├── analysis.py           Sentiment, themes, word clouds
│   ├── analysis_pipeline.py  Orchestrates the four analysis stages
│   └── requirements.txt
└── frontend/                 Deploy on Vercel
    ├── app/                  layout, page, global styles
    ├── components/
    │   ├── JanMatChatWidget.jsx   Chat UI; calls the Space with fetch()
    │   ├── AuthWidget.jsx         Email and password login
    │   └── CommentSection.jsx     Public comments per bill
    ├── lib/supabaseClient.js
    └── package.json
```

---

## Database

`supabase/schema.sql` is idempotent (`create ... if not exists`), so it is safe to re-run.

| Group | Tables |
|---|---|
| Knowledge base | `documents`, `chunks` (with `vector(384)` embedding) |
| Chat memory | `chat_sessions`, `chat_messages` |
| Operations | `ingestion_runs` |
| User comments | `comments` (public read, authenticated write, own rows only) |
| Consultation analysis | `comments_ingested`, `comment_analysis`, `comment_themes`, `word_cloud_terms` (public read; written by the backend only) |

The `match_chunks()` function does the hybrid vector + keyword ranking.

---

## Deployment

Do these in order: Supabase, then the Space, then Vercel.

### 1. Supabase

1. Create a project.
2. SQL Editor: paste and run `supabase/schema.sql`.
3. Settings, API: copy the **Project URL**, the **service_role** key, and the **anon** key.
4. Authentication, Sign In / Providers, Email: leave the provider **enabled** and turn **Confirm email** off (see Troubleshooting).

### 2. Hugging Face Space (backend)

1. Create a Space with SDK **Gradio**. Do not add a Dockerfile.
2. Upload every file in `backend/`. Keep the YAML header at the top of `backend/README.md` intact; it sets `sdk: gradio` and `app_file: app.py`.
3. Settings, Variables and secrets: add these as **Secrets**:

| Secret | Value |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_SERVICE_KEY` | `service_role` key (backend only) |
| `GROQ_API_KEY` | from console.groq.com |
| `SARVAM_API_KEY` | from sarvam.ai |
| `CRON_SECRET` | any long random string; it is the admin password |

4. When the Space shows *Running*, open the **Admin** tab, enter `CRON_SECRET`, click **Run ingestion now**, then **Run analysis now**. Use the status buttons to follow progress.

### 3. Vercel (frontend)

1. Import the repo with `frontend/` as the root directory.
2. Environment variables:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_JANMAT_SPACE_URL` | the direct app URL, e.g. `https://username-spacename.hf.space` (not the `huggingface.co/spaces/...` page) |
| `NEXT_PUBLIC_SUPABASE_URL` | Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the **anon** key, never `service_role` |

3. Redeploy after adding or changing any `NEXT_PUBLIC_*` variable. Those values are baked in at build time.
4. Settings, Deployment Protection: set **Vercel Authentication** to disabled, otherwise visitors hit a login wall.
5. In Supabase, Authentication, URL Configuration: set the **Site URL** to your production domain and add it to **Redirect URLs**.

---

## Configuration

All tunable in `backend/config.py`, most overridable with environment variables.

| Setting | Default | Meaning |
|---|---|---|
| `TOP_K_CHUNKS` | 20 | Candidate chunks retrieved per question |
| `MAX_CONTEXT_CHARS` | 20000 | Context budget sent to the model |
| `CHUNK_WORDS` / `CHUNK_OVERLAP_WORDS` | 220 / 40 | Chunking window |
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-20b` | Answer and analysis model |
| `max_bills_per_run` | 50 | Bills ingested per run |
| `mca_keywords` | company, LLP, insolvency, ... | Flags bills under the MCA's remit |

---

## Security notes

- `service_role` and all API keys live only in Space secrets. Anything prefixed `NEXT_PUBLIC_` is visible in the browser, so only the Space URL, Supabase URL and anon key belong there.
- Public tables are protected by Row Level Security, not by hiding the page.
- Admin actions require `CRON_SECRET`.
- The Groq and Sarvam free tiers are reachable by anyone who can reach the chat. Add per-IP rate limiting before promoting the site widely.
- With **Confirm email** off, anyone can register an address they do not own. Fine for a demo and open commenting; turn it back on (and connect an SMTP provider) for anything sensitive.

---

## Troubleshooting

Issues hit during development, with the fix for each.

| Symptom | Cause and fix |
|---|---|
| Space shows "config error" | A `Dockerfile` alongside `sdk: gradio`, or unfilled `{{placeholders}}` in the README header. Remove the Dockerfile; use real values. |
| `No module named 'websockets.asyncio'` | `supabase-py` conflicts with Gradio's pinned `websockets`. This project calls Supabase's REST API directly instead. |
| Startup crash: `argument of type 'bool' is not iterable`, or `unhashable type: 'dict'` | Newer `pydantic` / `starlette` against Gradio 4.44. Pins in `requirements.txt`: `pydantic==2.10.6`, `starlette<1.0`. |
| Build fails: `spaces==x` conflict | Do not pin `spaces`. ZeroGPU hardware injects its own version. |
| Ingestion fails: `Low-level CUDA init` | ZeroGPU reports CUDA as available outside `@spaces.GPU`. `embeddings.py` forces `device="cpu"`. |
| Chat shows "couldn't reach the chatbot" | `NEXT_PUBLIC_JANMAT_SPACE_URL` missing or pointing at `huggingface.co/spaces/...`; redeploy after setting it. |
| Chat fails only on long answers | Gradio's event stream ends with a null heartbeat. The widget keeps the last non-null payload. |
| Ingestion log full of 403 / SSL / timeout errors | Off-site PDFs linked from PRS. Browser-style User-Agent added; unreachable hosts are blocklisted in `pdf_ingest.py`. |
| Login redirects to `localhost:3000` | Supabase Site URL still the default. Set it to the production domain. |
| "email rate limit exceeded" on sign-up | Supabase's built-in mailer is capped at a few emails per hour. Turn Confirm email off (no mail sent), or connect an SMTP provider. If the project's Auth logs show no `/signup` requests at all, the Vercel env vars point at a different Supabase project than the one you are inspecting. |

---

## Known limitations

Stated plainly, because they affect how the project should be described.

- **Data source.** SIH25035 concerns MCA's eConsultation module. Per-comment eConsultation data is not publicly available, so the analysis runs on stakeholder commentary that PRS publishes about the same draft legislation. The analysis layer reads from a `source` column, so real eConsultation exports can be loaded without changing the pipeline.
- **Comment extraction is heuristic.** `looks_like_comment()` separates commentary from statutory text using opinion-signal phrases. Expect some false positives and misses on real pages. Discrete exported comments would remove this step entirely.
- **Model-dependent formatting.** The prompt steers answers toward short paragraphs and bullets, but the model chooses its own formatting, so tables occasionally still appear.
- **Legacy register on the homepage.** The original bill/theme list in `frontend/app/page.jsx` still calls endpoints from the retired summarisation backend and shows a "cannot be reached" state. It should be reconnected to the new analysis tables or removed.
- **Ingestion is manual.** There is no scheduler; run it from the Admin tab.
- **Free-tier behaviour.** A sleeping Space takes tens of seconds to wake on the first request, and the free Groq and Sarvam quotas are finite.

---

## Mapping to SIH25035

| Requirement | Where it lives |
|---|---|
| Sentiment analysis of comments | `analysis.py`: score and label per comment, stored in `comment_analysis` |
| Summaries | One-line summary per comment, plus a written summary per theme |
| Word clouds | `build_word_cloud()`, per bill and overall; weights favour terms recurring across comments |
| Help users understand feedback efficiently | Consultation Analysis tab, plus the grounded chatbot |
| MCA focus | `mca_keywords` flag bills in the Ministry of Corporate Affairs' remit |

---

## Roadmap

- Load real eConsultation exports through the `source` field.
- Scheduled ingestion and analysis.
- Per-IP rate limiting on the chat endpoint.
- Reconnect the homepage register to the analysis tables and show sentiment and themes there.
- Multilingual answers, not only multilingual voice input.

---

## Acknowledgements

Bill texts and commentary are published by [PRS Legislative Research](https://prsindia.org) and used for non-commercial purposes with acknowledgement. Sources are shown with every answer.
