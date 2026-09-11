---
title: JanMat
emoji: 🏛️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# JanMat

A chatbot that reads Indian legislative bills — their PRS Legislative
Research PDF briefs in full, the bill pages themselves, related articles,
and public opinion — and answers questions grounded in that material, with
sources cited. Supports both typed and spoken questions (voice via Sarvam
AI), and speaks answers back.

This is a single Gradio Space: the chat UI, the retrieval engine, and the
ingestion pipeline all run here — no separate frontend deployment needed.

## Required secrets (Space Settings → Variables and secrets)

Add each of these as a **Secret**:

| Secret name           | Where to get it |
|------------------------|------------------|
| `SUPABASE_URL`          | Supabase project → Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY`  | Supabase project → Settings → API → service_role key |
| `GROQ_API_KEY`          | console.groq.com → API Keys |
| `SARVAM_API_KEY`        | sarvam.ai → dashboard → API keys |
| `CRON_SECRET`           | any random string you make up yourself |

## First-time setup

1. Create a Supabase project, open its SQL Editor, and run `supabase/schema.sql`
   from this repo once. This creates the tables and the vector search function.
2. Add the five secrets above in this Space's settings.
3. Once the Space is running, open the "Admin: refresh the knowledge base"
   section at the bottom of the app, enter your `CRON_SECRET`, and click
   "Run ingestion now". This scrapes PRS bills + their PDFs and fills the
   knowledge base — it takes a few minutes.
4. Once ingestion finishes, ask a question in the chat box above.

## How it works

- **Reading**: `pdf_ingest.py` downloads and reads every page of every linked
  PDF (and every paragraph of every HTML page) in full — nothing is
  summarized at this stage.
- **Storage**: `embeddings.py` + `db.py` chunk and embed that text (locally,
  free, no extra API key) and store it in Supabase with pgvector.
- **Answering**: `rag.py` finds the most relevant chunks for a question and
  asks Groq to answer using only those chunks, citing which document each
  part came from.
- **Voice**: `voice.py` calls Sarvam AI for speech-to-text (your question)
  and text-to-speech (the spoken answer).
