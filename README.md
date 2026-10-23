# JanMat

**Ask questions about Indian bills, get answers grounded in the actual text, and read what stakeholders and citizens are saying, with TinyFish keeping the knowledge base connected to the live web.**

| | |
|---|---|
| Live app | https://jan-mat-new.vercel.app |
| Backend (Hugging Face Space) | https://beastzzz-janmat.hf.space |
| Demo video | _add link_ |
| Launch post | _add link_ |

JanMat reads draft bills and their full PDF briefs, stores every page in a searchable knowledge base, and answers questions in plain language with citations. Anyone can read the public comments on every bill; signed-in users can post their own. **TinyFish is the part that reaches the live web**: it finds new consultation material, recovers pages our own scraper cannot open, and pulls stakeholder comments off live pages as structured data.

---

## TinyFish integration (at a glance)

TinyFish is not decoration here. Remove the key and JanMat still works, but it can only see PRS pages that happen to be easy to scrape. With the key, it covers the rest of the live web.

| TinyFish API | Where it runs in JanMat | What it does for the product | Cost |
|---|---|---|---|
| **Search API** | `scraper.discover_via_tinyfish_search`, called from `ingest_pipeline.run_ingestion` | Finds draft bills, ministry consultation notices, news and stakeholder reactions that are **not** on PRS. Each hit is ingested as a searchable article. | Free |
| **Fetch API** | `pdf_ingest.ingest_source_document` (automatic fallback) | When a direct download fails (403 bot-block, SSL error, timeout, blocked host), the page or PDF is re-fetched through TinyFish's real-browser fetch and returned as clean text. | Free |
| **Web Agent** | `tinyfish_client.collect_comments`, via `scraper.discover_comment_documents` | Given only a goal in plain English, opens a consultation page and returns **every public stakeholder comment as structured JSON** (`stakeholder`, `comment`). Each page becomes one searchable "public opinion" document. | Billed per step |
| Browser Infrastructure | Not used | Our flows need goal-driven extraction, not hand-written Playwright scripts, so the Agent covers it. | n/a |

Full explanation, guardrails and how to verify it is working are in [How TinyFish is used](#how-tinyfish-is-used) below.

---

## The problem

Public consultation only works if feedback is absorbed, and in India that is hard for three reasons:

1. **Citizens cannot easily read the bill.** Bills are long, technical documents spread across several sites.
2. **Comments are not public.** The Ministry of Corporate Affairs' e-consultation instruction kit states it will not publish the comments it receives, and stakeholders have asked for published responses and counter-comments (see [Market research](#market-research)). Nobody can see what others said.
3. **The relevant material is scattered across the live web**: ministry pages, think-tank notes, industry submissions, news. Much of it sits behind JavaScript or bot protection that a simple scraper cannot read.

JanMat's approach is **read everything first, summarise later**: documents are stored in full and chunked, never pre-summarised, so detail questions stay answerable months later. A question retrieves only the passages relevant to it and the model answers from those passages alone. If the corpus does not contain the answer, JanMat says so.

---

## What it does

| Feature | Details |
|---|---|
| **Grounded Q&A** | Retrieval-augmented answers over bill text, PDFs, articles and stakeholder comments. Each answer ends with a short list of the sources it actually cited. |
| **Hybrid retrieval** | Blends vector similarity (75%) with trigram keyword matching (25%), so exact bill names and section numbers are found alongside conceptual matches. 20 candidate chunks per question. |
| **Honest refusal** | Asked about something outside the corpus, it says so instead of inventing an answer. |
| **Public comments on every bill** | Every ingested bill is listed with its comment count. Anyone can read all comments without signing in; posting needs an account. Author emails are masked (`ab***@example.com`). |
| **"What people are saying" feed** | One feed of every comment across all bills, filterable by bill. |
| **Voice in and out** | Speak a question (Sarvam speech-to-text) and hear the answer (text-to-speech). |
| **Live-web ingestion with TinyFish** | Search, Fetch and Agent as described above. |
| **Admin panel** | Password-protected panel in the Space: run ingestion, check status (including a TinyFish usage line), and try each TinyFish API directly. |

---

## How TinyFish is used

One ingestion run (Admin → **Run ingestion now**) does this:

```
1. PRS bill listing → bill pages → linked PDFs                     (direct fetch)
        │  any page/PDF that fails (403, SSL, timeout, blocked host)
        └──────────────► TinyFish FETCH retries it in a real browser → clean text
2. Optional seed URLs from config                                  (direct fetch, same fallback)
3. TinyFish (when TINYFISH_API_KEY is set)
     a. SEARCH  "draft bill public consultation stakeholder comments India", ...
                → new article/consultation URLs → ingested
     b. AGENT   goal: "list every public stakeholder comment on this page as JSON"
                on the configured consultation pages + the first few PRS bill pages
                → [{stakeholder, comment}, ...] → one "public_opinion" document each
4. Every document → chunk (220 words, 40 overlap) → local embeddings → Supabase
```

Everything TinyFish returns lands in the same knowledge base as PRS content, so a user asking "what do industry groups say about this bill?" gets an answer that cites those documents.

### Why each API is the right tool

- **Search** removes the hard-coded source list. New consultations and reactions appear without anyone editing code.
- **Fetch** fixes our most common ingestion failure. The old log was full of 403 and SSL errors from off-site PDFs; now those are recovered instead of dropped. Fetch is free, so this fallback costs nothing.
- **Agent** handles the one thing scraping cannot: comment sections have no common structure. A plain-English goal gives structured data from a page we have never seen, which is exactly what stakeholder consultation pages are.

### Guardrails

- The agent goal is read-only: it is told to use only what is visible without logging in and never to submit, sign in or post.
- Agent runs are the only billed call, so they are capped by `agent_max_bill_pages` (default 3) and only run from an admin-triggered ingestion, never per chat message.
- Every TinyFish call is wrapped: one failure is logged and skipped, and never aborts the run.
- With no `TINYFISH_API_KEY`, every TinyFish function is skipped and ingestion behaves as plain PRS scraping.

### Verify it yourself (this is what the demo video shows)

1. Space → **Admin** → enter `CRON_SECRET` → under **TinyFish live check** run:
   - **Search** with `draft bill public consultation stakeholder comments India`: returns ranked results.
   - **Fetch** with any bill or PDF URL: returns title, character count and the extracted text.
   - **Agent** with a consultation page URL: returns the extracted comments.
2. **Run ingestion now**, then **Check status**. The status ends with a TinyFish line, for example:
   `TinyFish — Search: 2 queries → 10 results (6 ingested) | Fetch fallback: 3/4 pages recovered | Agent: 3 runs, 36 steps → 14 stakeholder comments (2 docs ingested)`
3. In Supabase SQL editor: `select source, count(*) from documents group by source;` shows `tinyfish_search` and `tinyfish_agent` rows next to `prs`.
4. Ask the chatbot a question that those documents answer; the cited sources include them.

---

## Architecture

```
                         ┌──────────────────────────┐
   Browser ────────────► │  Vercel (Next.js)        │
      │                  │  chat, login, bills +    │
      │                  │  public comments         │
      │                  └──────────┬───────────────┘
      │                             │ fetch()  /call/chat
      │                             ▼
      │                  ┌──────────────────────────┐        ┌──────────┐
      │                  │  Hugging Face Space      │ ─────► │  Groq    │ answers
      │                  │  (Gradio, Python)        │        └──────────┘
      │                  │  ingestion, RAG, voice,  │        ┌──────────┐
      │                  │  admin                   │ ─────► │  Sarvam  │ STT / TTS
      │                  └───────┬──────────┬───────┘        └──────────┘
      │                          │          │                ┌──────────┐
      │                          │          └──────────────► │ TinyFish │ Search · Fetch · Agent
      │                          │ REST (service_role)       └────┬─────┘
      │   anon key + RLS         ▼                                │ live web
      └─────────────────► ┌──────────────────────────┐            ▼
                          │  Supabase                │     ministry pages, PRS,
                          │  Postgres + pgvector,    │     think-tanks, news
                          │  Auth, public views      │
                          └──────────────────────────┘
```

**Two separate credentials, on purpose.** The Space talks to Supabase with the powerful `service_role` key (a Space secret, never sent to a browser). The Vercel site uses the `anon` key, which can only do what Row Level Security allows, and reads bills and comments through two **public views** that expose only safe columns.

### A question

```
question → embed → hybrid search (top 20 chunks) → prompt Groq with numbered sources
   → keep only sources the answer cites → renumber, de-duplicate by URL
   → answer + "Sources" list
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Live web | **TinyFish** Search, Fetch and Web Agent (REST) |
| Frontend | Next.js 14, Tailwind, `react-markdown`, `@supabase/supabase-js` |
| Backend | Python, Gradio 4.44, `requests`, BeautifulSoup + lxml, `pypdf` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (384-d), local, CPU |
| LLM | Groq, default `openai/gpt-oss-20b` |
| Voice | Sarvam AI (`saaras:v3` speech-to-text, `bulbul:v3` text-to-speech) |
| Database / Auth | Supabase Postgres with `pgvector` and `pg_trgm`; Supabase Auth |
| Hosting | Hugging Face Spaces, Vercel, Supabase |

---

## Repository layout

```
├── README.md
├── DEPLOY.md                         Step-by-step deployment
├── supabase/
│   ├── schema.sql                    Tables, indexes, match_chunks(), comment policies
│   └── migration_public_comments.sql Row Level Security + public_bills / public_comments views
├── backend/                          Hugging Face Space (SDK: gradio)
│   ├── app.py                        Gradio UI: chat, voice, admin, TinyFish live check
│   ├── config.py                     Settings and the TinyFish block; secrets from env
│   ├── tinyfish_client.py            TinyFish Search, Fetch, Agent wrappers + usage counters
│   ├── scraper.py                    PRS discovery; TinyFish search + agent discovery
│   ├── pdf_ingest.py                 Text extraction; TinyFish Fetch fallback
│   ├── ingest_pipeline.py            Discover → extract → chunk → embed → store
│   ├── embeddings.py                 Chunking and local embeddings
│   ├── rag.py                        Hybrid retrieval, answer generation, citations
│   ├── voice.py                      Sarvam speech-to-text and text-to-speech
│   ├── db.py                         Supabase REST access (no supabase-py)
│   └── requirements.txt
└── frontend/                         Vercel (Next.js)
    ├── app/page.jsx                  Chat, bills list, comments
    ├── components/
    │   ├── JanMatChatWidget.jsx      Chat UI, calls the Space
    │   ├── AuthWidget.jsx            Email + password login
    │   ├── AllComments.jsx           Every comment, filter by bill
    │   └── CommentSection.jsx        Comments on one bill, post when signed in
    └── lib/supabaseClient.js         Anon client + readable error messages
```

---

## Database

| Group | Tables / objects |
|---|---|
| Knowledge base | `documents`, `chunks` (with `vector(384)`) |
| Chat memory | `chat_sessions`, `chat_messages` |
| Operations | `ingestion_runs` |
| User comments | `comments` (insert and delete only as the signed-in author) |
| Public read access | views `public_bills` and `public_comments` |

`match_chunks()` does the hybrid vector + keyword ranking. `migration_public_comments.sql` turns on Row Level Security for the internal tables (so the public anon key cannot read chat history or the knowledge base) and creates the two views: `public_bills` exposes only title, link and status; `public_comments` exposes every comment with the author's email masked.

---

## Deployment

Full walkthrough in [DEPLOY.md](DEPLOY.md). Order: Supabase, then the Space, then Vercel.

| Where | Secret / variable |
|---|---|
| Space | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY`, `CRON_SECRET` (admin password), **`TINYFISH_API_KEY`** |
| Vercel | `NEXT_PUBLIC_JANMAT_SPACE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |

Run `schema.sql` once, then `migration_public_comments.sql`. Redeploy Vercel after changing any `NEXT_PUBLIC_*` variable: they are baked in at build time.

---

## Configuration

Set in `backend/config.py`.

| Setting | Default | Meaning |
|---|---|---|
| `TOP_K_CHUNKS` / `MAX_CONTEXT_CHARS` | 20 / 20000 | Chunks retrieved and context sent to the model per question |
| `CHUNK_WORDS` / `CHUNK_OVERLAP_WORDS` | 220 / 40 | Chunking window |
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-20b` | Answer model |
| `prs.max_bills_per_run` | 25 | Bills ingested per run |
| `tinyfish.search_queries` | 2 queries | What TinyFish Search looks for each run |
| `tinyfish.results_per_query` | 5 | Search hits ingested per query |
| `tinyfish.consultation_urls` | empty | Consultation pages whose comments the Agent extracts |
| `tinyfish.agent_max_bill_pages` | 3 | PRS bill pages the Agent reads per run (this is the billed part) |

---

## Price economics

All figures are computed from published prices (sources at the end) and from the limits in this repo. Where a number is my assumption rather than a published price, it is marked **(assumption)**. Exchange rate used: ₹88 per US$ **(assumption)**.

### Unit costs

| Item | How it is calculated | Cost |
|---|---|---|
| **One text question** | Context cap is 20,000 characters ≈ 5,000 tokens, plus ~700 tokens of prompt and history **(assumption)** = 5,700 input tokens; ~900 output tokens including reasoning **(assumption)**. Groq GPT-OSS 20B: $0.10 per 1M input, $0.50 per 1M output. | **≈ $0.001 (₹0.09)**; ~$1.02 per 1,000 questions |
| **One voice turn** | 10 s of speech at ₹30/hour = ₹0.08; a 600-character spoken answer at Bulbul v3 ₹30 per 10,000 characters = ₹1.80; plus the text answer. | **≈ ₹2.0 (~$0.022)**. Voice answers cost ~20× text, so speech output is the main cost lever (Bulbul v2 at ₹15 per 10,000 characters halves it). |
| **Embeddings** | Local model on the Space CPU | **$0** |
| **TinyFish Search and Fetch** | Free on every plan | **$0** |
| **TinyFish Agent run** | $0.016 per step; a comment-extraction run of ~12 steps **(assumption)** | **≈ $0.19 per page**; default 3 pages per ingestion run ≈ $0.58; weekly ≈ **$2.5 per month** |
| **Storage** | A chunk ≈ 1.3 KB text + 1.5 KB vector + overhead ≈ 4 KB **(assumption)**; 8,000 chunks (~100 documents) ≈ 30 MB | Fits Supabase's 500 MB free database many times over |

The design keeps the one billed TinyFish call off the user's path: chat never calls the Agent, only admin-triggered ingestion does, and it is capped by config.

### Monthly cost by stage

| Stage | Setup | Monthly cost |
|---|---|---|
| **Hackathon / demo** | Free tiers: Supabase Free, Vercel Hobby, Hugging Face free CPU, Groq and Sarvam free quotas, TinyFish's 500 free signup credits | **≈ $0**, plus ≤ $3 of TinyFish credits if you run the Agent weekly |
| **Production pilot** | 2,000 monthly users, 5,000 text questions, 1,000 voice turns, weekly ingestion | **≈ $95**: Supabase Pro $25 + Vercel Pro $20 + always-on Space $20 **(assumption)** + Groq $5.10 + voice $22.40 + TinyFish $2.50 |
| Pilot, per user | $95 ÷ 2,000 users | **≈ $0.05 (₹4) per user per month** |

Why the free stage cannot be the production stage: Supabase free projects pause after 7 idle days (which makes the site look broken), 500 MB is the ceiling, and Vercel's Hobby plan is meant for non-commercial use.

### Pricing

Citizens are never charged: at ₹0.09 per question, free access for the public costs almost nothing and is the point of the product. Money comes from organisations that need to watch consultations.

| Tier | Price **(proposed)** | What they get | Why this price |
|---|---|---|---|
| **Citizen** | Free | Q&A, read all comments, post comments | Variable cost ≈ ₹0.09 per question |
| **Analyst** (NGOs, journalists, students) | ₹999 / month (~$11) | Higher question limits, voice, saved bill list | 300 questions cost ~$0.31, leaving room for hosting and support |
| **Institution** (law firms, trade bodies, think-tanks) | ₹14,999 / month (~$170) | Their own list of consultation pages monitored weekly by the TinyFish Agent, with comments searchable alongside the bills | Watching 20 pages weekly costs ≈ $16.50 in Agent steps (20 pages × ~12 steps × $0.016 × 4.3 weeks), about 10% of the price. The rest covers hosting, support and margin. |

How to read this honestly: the cost side is derived from published prices. **The price side is a proposal.** I did not find public price lists for comparable Indian legislative-tracking tools, so willingness to pay is not yet validated; the first pilots should be used to test ₹999 and ₹14,999. A useful check is manual effort: reading 10,000 consultation comments at one minute each **(assumption)** is ~167 hours, about ₹83,000 at ₹500 per hour **(assumption)**, so a monthly fee in the tens of thousands of rupees is small next to that.

---

## Market research

**Who needs this and why now**

- **Reach.** India had about 958 million active internet users in 2025, with rural India (~57%) growing fastest; 38% of the population is still offline. Voice input and plain-language answers matter for exactly the people who find legal text hardest to read.
- **The gap is documented.** MCA's own e-consultation instruction kit says it will not publish received comments. Civil-society groups note that the portal route asks people to register and share a mobile number, which deters some from taking part. In 2023 nearly sixty stakeholders wrote to MCA asking for open consultation, published comments and a counter-comment round.
- **Consultations are active and contested.** MCA's Digital Competition Bill consultation ran from March 2024, its deadline was extended from 15 April to 15 May 2024, and MeitY later convened meetings because numerous representations had come in. That is the volume-and-fragmentation problem JanMat targets.
- **Existing options leave room.** PRS Legislative Research publishes bills and analysis free of charge but as static pages, not Q&A, and without a public place for citizens to respond. Government portals collect comments without showing them. General chatbots are not tied to the current text of a specific bill and do not cite it.

**Target segments:** citizens and students (free), journalists and NGOs (Analyst), law firms, industry bodies and think-tanks that file consultation responses (Institution), and, later, ministries that want to analyse what they received.

**What I have not done:** a revenue-size (TAM) estimate. I found no reliable source for the number of Indian organisations that regularly file consultation responses, and I would rather leave it blank than invent one.

---

## Security notes

- `service_role` and all API keys live only in Space secrets. Anything `NEXT_PUBLIC_` is visible in the browser.
- Row Level Security is enabled on every table; the browser reads only through the two public views, which mask emails.
- Admin actions, including the TinyFish live check, require `CRON_SECRET`.
- The TinyFish Agent goal forbids signing in, submitting forms or posting.
- Groq and Sarvam quotas are reachable by anyone who can reach the chat. Add per-IP rate limiting before promoting the site widely.
- With **Confirm email** off, anyone can register an address they do not own. Fine for open commenting in a demo.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Comments show `Failed to fetch` / site shows old UI | **Supabase free project is paused** (idle 7 days), or `NEXT_PUBLIC_SUPABASE_URL` is wrong. Restore the project in the Supabase dashboard, check the URL, then **redeploy Vercel** (env vars are baked in at build). If Vercel still shows the old layout, the latest deployment failed: open Vercel → Deployments and read the build log. |
| Comments show "views are missing" | Run `supabase/migration_public_comments.sql`. |
| Chat says "couldn't reach the chatbot" | The Space is asleep or crashed. Open it and read the Logs. A common crash is `cannot import name 'HfFolder'`: Gradio 4.44 needs `huggingface_hub<1.0`, which `requirements.txt` now pins. Also check `NEXT_PUBLIC_JANMAT_SPACE_URL` is the `*.hf.space` URL. |
| Startup crash `argument of type 'bool' is not iterable` | Newer `pydantic`/`starlette` against Gradio 4.44; pinned in `requirements.txt`. |
| Space shows "config error" | A `Dockerfile` alongside `sdk: gradio`. Remove the Dockerfile. |
| Ingestion log full of 403 / SSL / timeout | Off-site PDFs. With `TINYFISH_API_KEY` set these are retried through TinyFish Fetch. |
| TinyFish live check says "not set" | Add `TINYFISH_API_KEY` as a Space **secret** and let the Space restart. |
| Chat forgets earlier messages | The session id must round-trip; `app.py` returns it through a hidden textbox. Redeploy the Space with the current `app.py`. |
| Login redirects to `localhost:3000` | Supabase Site URL still default. Set it to the production domain. |

---

## Known limitations

- **Comment extraction depends on the page.** The Agent returns only comments visible without logging in; pages that hide comments behind a login or a PDF yield nothing. It is not run on every page, because Agent steps cost credits.
- **Fetch returns one block of text.** Documents recovered through TinyFish Fetch lose per-page numbers, so their citations point to the document, not a page.
- **No sentiment or theme analysis in this version.** An earlier prototype had sentiment scoring, themes and word clouds; the current codebase focuses on grounded Q&A, public comments and live-web ingestion.
- **Ingestion is manual.** Run it from the Admin panel; there is no scheduler yet.
- **Free-tier behaviour.** A sleeping Space takes tens of seconds to wake, free Supabase projects pause when idle, and free Groq and Sarvam quotas are finite.
- **Pricing is a proposal** (see Price economics).

---

## Roadmap

- Scheduled ingestion (weekly) so the knowledge base refreshes itself.
- Per-user watchlists: pick bills or consultation pages and get alerts when TinyFish finds new material.
- Per-IP rate limiting on the chat endpoint.
- Sentiment and theme summaries over stakeholder comments.
- Multilingual answers, not only multilingual voice input.

---

## Sources for the figures above

- TinyFish pricing (Search and Fetch free; Agent 1 credit per step, about $0.015–0.016): tinyfish.ai/blog/firecrawl-pricing, tinyfish.ai/blog/search-and-fetch-are-now-free-for-every-agent-everywhere
- Groq GPT-OSS 20B ($0.10 / $0.50 per 1M tokens): groq.com/pricing
- Sarvam AI pricing (speech-to-text ₹30/hour, Bulbul v3 ₹30 per 10K characters): docs.sarvam.ai/api-reference-docs/pricing
- Supabase Free and Pro limits (pause after 7 idle days, $25 Pro): jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs
- India internet users 2025 (IAMAI): tele.net.in/indias-internet-user-base-crosses-950-million-in-2025-as-per-iamai-report
- MCA e-consultation comments not published; Digital Competition Bill consultation: internetfreedom.in/iffs-submission-on-the-digital-competition-bill, tele.net.in/government-extends-deadline-for-comments-on-draft-digital-competition-bill-to-may-15-2024, storyboard18.com (MeitY meeting)
- Stakeholder letter requesting open consultation: medianama.com/2023/06/223-letter-open-consultation-digital-competition-act

---

## Acknowledgements

Bill texts and commentary are published by [PRS Legislative Research](https://prsindia.org) and used for non-commercial purposes with acknowledgement. Sources are shown with every answer. Live-web access by [TinyFish](https://www.tinyfish.ai).
