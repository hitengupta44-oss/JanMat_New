# JanMat: step-by-step deployment

Order matters: **Supabase, then the Hugging Face Space, then Vercel.**
Everything runs on free tiers. Budget about 45 minutes.

```
GitHub repo ──► Vercel (frontend/)  ──► browser
        └─────► HF Space (backend/) ──► Groq, Sarvam, TinyFish
                      └────────────────► Supabase (database + login)
```

---

## 0. Accounts and keys to get first

| Service | Needed for | Where |
|---|---|---|
| GitHub | hosting the code | github.com |
| Supabase | database + login | supabase.com |
| Hugging Face | backend (Space) | huggingface.co |
| Vercel | frontend | vercel.com (sign in with GitHub) |
| Groq | answers + analysis | console.groq.com, API Keys |
| Sarvam AI | voice in/out (optional) | sarvam.ai |
| TinyFish | live web (optional) | agent.tinyfish.ai/api-keys |

Make up one long random string now (for example 40 characters). It is your **CRON_SECRET**, the admin password.

---

## 1. Put this folder on GitHub

Replace the contents of your existing repo with this folder.

```bash
git clone https://github.com/hitengupta44-oss/JanMat_New.git
cd JanMat_New
# delete the old files (keep the hidden .git folder), then copy in everything
# from janmat-complete/ so the layout is backend/ frontend/ supabase/ README.md DEPLOY.md
git add -A
git commit -m "Fix chat, public comments, add TinyFish"
git push
```

Do **not** commit real keys. `.env` files are already git-ignored.

---

## 2. Supabase (database)

1. **New project.** Pick a region near India (Mumbai) and save the database password.
2. **SQL Editor > New query.** Paste all of `supabase/schema.sql` and click **Run**. Run it **once only**; re-running errors on the policy lines.
3. **New query again.** Paste all of `supabase/migration_public_comments.sql` and click **Run**. This turns on Row Level Security, makes comments public with emails masked, and creates the public bills list. It is safe to re-run.
4. **Project Settings > API.** Copy three values:
   - Project URL
   - `anon` public key (goes to the frontend)
   - `service_role` key (goes to the backend only, never the frontend)
5. **Authentication > Sign In / Providers > Email.** Keep Email enabled and turn **Confirm email** off (otherwise sign-ups hit the email rate limit).
6. **Authentication > URL Configuration.** Leave for now; you set the Site URL in step 5 below.

---

## 3. Hugging Face Space (backend)

1. huggingface.co > **New Space**. Name it (for example `janmat`), SDK **Gradio**, hardware **CPU basic (free)**. Do **not** add a Dockerfile.
2. Upload **every file inside `backend/`** to the Space root: `app.py`, `config.py`, `db.py`, `embeddings.py`, `pdf_ingest.py`, `scraper.py`, `ingest_pipeline.py`, `rag.py`, `voice.py`, `tinyfish_client.py`, `requirements.txt` and `README.md`. Files tab > **Add file > Upload files**. Keep the YAML block at the top of `README.md` untouched.
3. Space **Settings > Variables and secrets > New secret**. Add these as **Secrets**, not Variables:

   | Name | Value |
   |---|---|
   | `SUPABASE_URL` | Project URL |
   | `SUPABASE_SERVICE_KEY` | `service_role` key |
   | `GROQ_API_KEY` | from Groq |
   | `SARVAM_API_KEY` | from Sarvam (skip if you don't need voice) |
   | `CRON_SECRET` | your long random string |
   | `TINYFISH_API_KEY` | from TinyFish (optional, see step 6) |

4. Wait for the Space to show **Running**. The first build takes several minutes because it installs the embedding model.
5. Your direct app URL is `https://<hf-username>-<space-name>.hf.space` (lowercase, dashes). **This is the URL the frontend needs, not the `huggingface.co/spaces/...` page.**
6. **Test the chat endpoint** from any terminal:

   ```bash
   curl -X POST https://<hf-username>-<space-name>.hf.space/call/chat \
     -H "Content-Type: application/json" \
     -d '{"data":["hi",[],null]}'
   ```
   You should get back `{"event_id": "..."}`. If you get HTML or an error, fix the Space before moving on.
7. Open the Space, go to the **Admin** tab, enter your `CRON_SECRET`, click **Run ingestion now**, and use the status button to follow progress. This loads the bills. It can take a while on the free CPU.

---

## 4. Vercel (frontend)

1. vercel.com > **Add New > Project**, import your GitHub repo.
2. **Root Directory:** `frontend`. Framework is detected as Next.js.
3. **Environment Variables** (all three, for Production):

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_JANMAT_SPACE_URL` | the direct `.hf.space` URL from step 3.5 |
   | `NEXT_PUBLIC_SUPABASE_URL` | Project URL |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the **anon** key (never `service_role`) |

4. Click **Deploy**.
5. **Settings > Deployment Protection:** set Vercel Authentication to **Disabled**, otherwise visitors see a login wall.
6. Whenever you change a `NEXT_PUBLIC_*` variable, **Redeploy**. They are baked in at build time.

---

## 5. Connect login to your live site

Supabase > **Authentication > URL Configuration**:
- **Site URL:** your Vercel domain, for example `https://janmat.vercel.app`
- **Redirect URLs:** add the same domain.

---

## 6. Turn on TinyFish (optional)

1. Create a key at agent.tinyfish.ai/api-keys and add it as the `TINYFISH_API_KEY` Space secret (step 3.3). The Space restarts.
2. Open `backend/config.py` (edit it in the Space too) and under `CONFIG["tinyfish"]` set:
   - `search_queries`: what to look for on the web
   - `consultation_urls`: public consultation pages whose comments the agent should extract
   - `agent_max_bill_pages`: how many PRS bill pages the agent reads per run (Agent runs are billed, so keep this small)
3. Admin tab > **Run ingestion now**. With the key set, ingestion also: retries failed downloads through TinyFish Fetch, adds web search results, and stores agent-extracted comments as searchable documents.
4. To see TinyFish working, open the Admin accordion again: the **TinyFish live check** lets you run Search, Fetch and Agent on their own, and **Check status** now ends with a TinyFish usage line.
5. Without the key, nothing changes.

---

## 7. Check that everything works

- [ ] Open your Vercel URL. Type "hi" in the chat. You get an answer (the first reply can take up to a minute if the Space was asleep).
- [ ] Ask "What is the Insolvency and Bankruptcy Code amendment about?". The answer cites sources.
- [ ] The **Comment on a bill** list shows bills.
- [ ] Sign up, open a bill, post a comment. It appears under **What people are saying** with your email masked.
- [ ] Open the site in a private window (signed out). You can still read every comment.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Chat says "Details: Network error reaching ..." | Wrong or missing `NEXT_PUBLIC_JANMAT_SPACE_URL`; fix it and redeploy. Also check the Space is Running. |
| Chat says "Details: ... non-JSON page" | Space is asleep or building. Wait a minute and retry. |
| Chat error mentions Groq / 401 | `GROQ_API_KEY` missing or wrong in Space secrets. |
| Chat error mentions Supabase | `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` wrong (service_role, not anon). |
| Bill list says "No bills yet" | Run ingestion in the Admin tab; confirm the migration SQL ran. |
| Bill list or comments show a red error | Migration SQL not run, so `public_bills` / `public_comments` don't exist. |
| Space shows "config error" | A Dockerfile is present, or the README header was changed. |
| Sign-up says "email rate limit exceeded" | Turn **Confirm email** off in Supabase. |
| Login redirects to localhost:3000 | Set the Supabase Site URL (step 5). |
| Ingestion log full of 403/SSL errors | Add `TINYFISH_API_KEY` (step 6). |

---

## Run locally (optional)

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # fill it in
python app.py            # http://localhost:7860

# frontend (new terminal)
cd frontend && cp .env.example .env.local   # set NEXT_PUBLIC_JANMAT_SPACE_URL=http://localhost:7860
npm install && npm run dev                   # http://localhost:3000
```

## Security reminders

- `service_role` and all API keys live only in Space secrets.
- The Groq and Sarvam quotas are open to anyone who can use the chat; add per-IP rate limiting before sharing widely.
- With **Confirm email** off, anyone can register an address they don't own.

---

## 8. If something breaks

| Symptom | Fix |
|---|---|
| Site shows comments error `Failed to fetch` or still shows an old layout | Supabase free projects **pause after 7 idle days**. Open the Supabase dashboard and restore the project, confirm `NEXT_PUBLIC_SUPABASE_URL` is correct, then **Redeploy** on Vercel. If the old layout persists, open Vercel > Deployments: the newest deployment probably failed to build; read its log. |
| Space crashes with `cannot import name 'HfFolder'` | Keep `huggingface_hub>=0.25,<1.0` in `backend/requirements.txt` (Gradio 4.44 needs it), then restart the Space. |
| Comments list says the views are missing | Run `supabase/migration_public_comments.sql` (step 2.3). |
