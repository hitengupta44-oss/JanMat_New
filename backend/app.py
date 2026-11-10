"""
JanMat — single Gradio Space.

Two jobs (SIH 2025, PS SIH25035 - sentiment analysis of e-consultation comments):
  1. Chat: answers questions using Groq, grounded in the full text of scraped
     PRS bill pages + PDFs (stored in Supabase), with optional voice in/out via
     Sarvam AI. Only signed-in users can chat: every call must carry a valid
     Supabase access token from the website.
  2. Comment analysis: labels each public comment positive/negative/neutral,
     summarises it, and keeps an overall summary per bill (see analysis.py).

Everything lives in this one Space, same as your original setup — no
separate frontend needed.
"""
import logging
import threading

import gradio as gr

import analysis
import db
import rag
import voice
from config import CRON_SECRET
from ingest_pipeline import run_ingestion
import tinyfish_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("janmat.app")

# This Space's hardware tier is set to ZeroGPU (HF's free GPU allowance).
# The actual workload here is 100% CPU (embeddings, HTTP calls to Supabase/
# Groq/Sarvam) — nothing needs a GPU. However, ZeroGPU hardware expects at
# least one @spaces.GPU-decorated function to exist so HF's runtime
# recognizes the Space as compliant with that hardware tier. This mirrors
# what the original app.py did for the same reason (see git history).
try:
    import spaces

    @spaces.GPU
    def _zerogpu_keepalive():
        """No-op — exists only to satisfy the ZeroGPU hardware requirement."""
        return "ok"

    try:
        _zerogpu_keepalive()
    except Exception:
        logger.info("ZeroGPU keepalive call skipped (no GPU allocated at import time) — harmless.")
except ImportError:
    logger.info("`spaces` package not available — assuming non-ZeroGPU hardware, skipping keepalive.")

_ingestion_lock = threading.Lock()
_ingestion_state = {"running": False, "last_summary": None}


LOGIN_REQUIRED = "🔒 Please sign in on the JanMat website to use the chatbot."


def _ensure_session(session_id, user):
    """Reuse the chat session only if it belongs to this user; otherwise start a new one."""
    label = f"user:{user['id']}"
    if session_id:
        existing = db.get_session(session_id)
        if existing and existing.get("label") == label:
            return session_id
    return db.create_session(label)


def _clean_source_title(title: str) -> str:
    """
    Source titles are often raw PDF filenames like
    'Corporate_Laws_(A)_Bill_2026_Text.pdf' — turn those into something
    readable before showing them to a citizen.
    """
    name = title.strip()
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    name = name.replace("_", " ").replace("%2C", ",")
    # Collapse the double spaces that underscore-stripping can leave behind.
    return " ".join(name.split())


def _format_answer_with_sources(answer: str, citations: list) -> str:
    if not citations:
        return answer
    lines = "\n".join(
        f"{c['n']}. [{_clean_source_title(c['title'])}]({c['url']})" for c in citations
    )
    return f"{answer}\n\n---\n\n**Sources**\n\n{lines}"


def chat_fn(message, history, session_id, access_token):
    if not message or not message.strip():
        return history, "", session_id

    user = db.get_user_from_token(access_token)
    if not user:
        return history + [(message, LOGIN_REQUIRED)], "", session_id

    session_id = _ensure_session(session_id, user)
    db.save_message(session_id, "user", message, input_mode="text")

    result = rag.answer_question(session_id, message)
    db.save_message(session_id, "assistant", result["answer"], citations=result["citations"], input_mode="text")

    display_answer = _format_answer_with_sources(result["answer"], result["citations"])
    history = history + [(message, display_answer)]
    return history, "", session_id


def voice_fn(audio_path, history, session_id, access_token):
    if audio_path is None:
        return history, session_id, None

    user = db.get_user_from_token(access_token)
    if not user:
        return history + [(None, LOGIN_REQUIRED)], session_id, None

    session_id = _ensure_session(session_id, user)

    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        stt = voice.transcribe_audio(audio_bytes, filename="question.wav")
        transcript = stt["transcript"]
        language = stt.get("language_code") or "unknown"

        if not transcript.strip():
            history = history + [(None, "I couldn't hear a question in that clip — please try again.")]
            return history, session_id, None

        db.save_message(session_id, "user", transcript, input_mode="voice", language_code=language)

        result = rag.answer_question(session_id, transcript)
        db.save_message(session_id, "assistant", result["answer"], citations=result["citations"],
                         input_mode="voice", language_code=language)

        tts_language = language if language != "unknown" else "en-IN"
        answer_audio_bytes = voice.synthesize_speech(result["answer"], language_code=tts_language)

        out_path = "/tmp/janmat_answer.wav"
        with open(out_path, "wb") as f:
            f.write(answer_audio_bytes)

        display_answer = _format_answer_with_sources(result["answer"], result["citations"])
        history = history + [(transcript, display_answer)]
        return history, session_id, out_path

    except Exception as exc:
        logger.exception("Voice turn failed")
        history = history + [(None, f"Voice processing failed: {exc}")]
        return history, session_id, None


def analyze_comment_fn(comment_id, access_token):
    """
    Called by the website right after a signed-in user posts a comment.
    Labels the comment's sentiment, summarises it, and refreshes the bill's
    overall summary. Returns the result as JSON for the page to show at once.
    """
    user = db.get_user_from_token(access_token)
    if not user:
        return {"ok": False, "error": "login required"}
    try:
        cid = int(str(comment_id).strip())
    except ValueError:
        return {"ok": False, "error": "bad comment id"}

    comment = db.get_comment(cid)
    if not comment:
        return {"ok": False, "error": "comment not found"}
    if comment.get("analyzed_at"):
        # Already done: don't spend Groq calls again.
        return {"ok": True, "comment_id": cid, "sentiment": comment["sentiment"],
                "score": comment["sentiment_score"], "summary": comment["summary"], "cached": True}

    try:
        result = analysis.analyze_comment(cid)
        topic = analysis.refresh_topic(comment["topic_key"])
        analysis.refresh_all_topics_summary()
    except Exception as exc:
        logger.exception("Comment analysis failed")
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "comment_id": cid, "sentiment": result["sentiment"], "score": result["score"],
            "summary": result["summary"], "engine": result["engine"],
            "topic_summary": (topic or {}).get("overall_summary")}


def analyze_all_fn(secret):
    if not CRON_SECRET or secret != CRON_SECRET:
        return "❌ Incorrect secret."
    try:
        r = analysis.analyze_pending_and_refresh()
    except Exception as exc:
        logger.exception("Batch analysis failed")
        return f"Analysis failed: {exc}"
    return (f"✅ Labelled {r['analysed']} new comment(s) ({r['failed']} failed). "
            f"Summaries refreshed for {r['topics']} bill(s)/topic(s).")


def run_ingestion_fn(secret):
    if not CRON_SECRET or secret != CRON_SECRET:
        return "❌ Incorrect secret."

    with _ingestion_lock:
        if _ingestion_state["running"]:
            return "⏳ Ingestion is already running — check back shortly."
        _ingestion_state["running"] = True

    def _background_run():
        try:
            summary = run_ingestion()
            _ingestion_state["last_summary"] = summary
            logger.info("Ingestion finished: %s", summary)
        except Exception:
            logger.exception("Ingestion run crashed")
        finally:
            _ingestion_state["running"] = False

    threading.Thread(target=_background_run, daemon=True).start()
    return "✅ Ingestion started in the background. This can take a few minutes for a full run."


def ingestion_status_fn(secret):
    if not CRON_SECRET or secret != CRON_SECRET:
        return "❌ Incorrect secret."
    if _ingestion_state["running"]:
        return "⏳ Still running..."
    summary = _ingestion_state["last_summary"]
    if not summary:
        return "No ingestion has completed yet in this session."
    return (
        f"Last run — seen: {summary.get('documents_seen', 0)}, "
        f"ingested: {summary.get('ingested', 0)}, "
        f"unchanged: {summary.get('unchanged', 0)}, "
        f"skipped: {summary.get('skipped', 0)}, "
        f"failed: {summary.get('failed', 0)}"
        + _tinyfish_status_line(summary)
    )


def _tinyfish_status_line(summary) -> str:
    by_src = summary.get("ingested_by_source") or {}
    tf = summary.get("tinyfish") or {}
    if not tf and not any(k.startswith("tinyfish") for k in by_src):
        return ""
    return (
        "\nTinyFish — "
        f"Search: {tf.get('search_calls', 0)} queries → {tf.get('search_results', 0)} results "
        f"({by_src.get('tinyfish_search', 0)} ingested) | "
        f"Fetch fallback: {tf.get('fetch_ok', 0)}/{tf.get('fetch_calls', 0)} pages recovered | "
        f"Agent: {tf.get('agent_runs', 0)} runs, {tf.get('agent_steps', 0)} steps → "
        f"{tf.get('agent_comments', 0)} stakeholder comments ({by_src.get('tinyfish_agent', 0)} docs ingested)"
    )


def tinyfish_demo_fn(secret, mode, target):
    """Admin-only live check of each TinyFish API, so the integration can be shown working."""
    if not CRON_SECRET or secret != CRON_SECRET:
        return "❌ Incorrect secret."
    if not tinyfish_client.enabled():
        return "TINYFISH_API_KEY is not set. Add it as a Space secret and restart."
    target = (target or "").strip()
    if not target:
        return "Enter a search query (Search) or a URL (Fetch / Agent)."
    try:
        if mode.startswith("Search"):
            hits = tinyfish_client.search(target, max_results=5)
            if not hits:
                return "Search returned no results."
            return "\n\n".join(f"{i}. {h['title']}\n   {h['url']}\n   {h['snippet'][:200]}" for i, h in enumerate(hits, 1))
        if mode.startswith("Fetch"):
            page = tinyfish_client.fetch_text(target)
            text = page["text"]
            return f"Title: {page['title']}\nFinal URL: {page['final_url']}\nCharacters: {len(text)}\n\n{text[:3000]}"
        comments = tinyfish_client.collect_comments(target)
        if not comments:
            return "Agent finished but found no public comments on that page."
        return f"Agent extracted {len(comments)} comments:\n\n" + "\n\n".join(
            f"• {c['stakeholder']}: {c['comment'][:300]}" for c in comments[:10])
    except Exception as exc:
        return f"TinyFish call failed: {exc}"


with gr.Blocks(title="JanMat — Ask about Indian Bills") as demo:
    gr.Markdown(
        "# 🏛️ JanMat\n"
        "Ask questions about Indian legislative bills and their PRS Legislative Research "
        "briefs, by text or voice, and see sentiment analysis of public comments.\n\n"
        "**The chatbot is for signed-in users of the JanMat website.** This page is the "
        "backend; use the website to chat and comment."
    )

    # Hidden Textbox rather than gr.State: gr.State values are NOT returned over the /call/<api>
    # HTTP API, so the website never received the session id and every message started a
    # brand-new conversation (no chat memory). A hidden Textbox round-trips normally.
    session_state = gr.Textbox(value="", visible=False)
    # Supabase access token sent by the website; the chat refuses to answer without a valid one.
    token_box = gr.Textbox(value="", visible=False)

    chatbot = gr.Chatbot(height=460, label="Conversation")

    with gr.Row():
        msg = gr.Textbox(placeholder="e.g. What does the Digital Data Protection Bill say about consent?",
                          scale=4, show_label=False)
        send_btn = gr.Button("Send", scale=1, variant="primary")

    with gr.Row():
        mic = gr.Audio(sources=["microphone"], type="filepath", label="Or ask by voice")
        answer_audio = gr.Audio(label="Spoken answer", autoplay=True)

    send_btn.click(chat_fn, [msg, chatbot, session_state, token_box], [chatbot, msg, session_state], api_name="chat")
    msg.submit(chat_fn, [msg, chatbot, session_state, token_box], [chatbot, msg, session_state], api_name=False)
    mic.stop_recording(voice_fn, [mic, chatbot, session_state, token_box], [chatbot, session_state, answer_audio],
                       api_name="chat_voice")

    # API-only endpoint used by the website after a comment is posted.
    with gr.Row(visible=False):
        comment_id_box = gr.Textbox()
        analyze_token_box = gr.Textbox()
        analyze_out = gr.JSON()
        analyze_btn = gr.Button()
    analyze_btn.click(analyze_comment_fn, [comment_id_box, analyze_token_box], [analyze_out],
                      api_name="analyze_comment")

    with gr.Accordion("Admin: refresh the knowledge base", open=False):
        gr.Markdown(
            "Triggers a fresh scrape + ingest of PRS bill pages and their PDFs. "
            "Requires the CRON_SECRET you set as a Space secret."
        )
        secret_box = gr.Textbox(label="Cron secret", type="password")
        with gr.Row():
            run_btn = gr.Button("Run ingestion now")
            status_btn = gr.Button("Check status")
        status_box = gr.Textbox(label="Status", interactive=False)
        run_btn.click(run_ingestion_fn, [secret_box], [status_box])
        status_btn.click(ingestion_status_fn, [secret_box], [status_box])

        gr.Markdown(
            "### Comment sentiment analysis\n"
            "Labels every comment that hasn't been analysed yet (positive / negative / neutral + "
            "one-line summary) and rebuilds the per-bill and overall summaries."
        )
        analyze_all_btn = gr.Button("Analyse all comments now")
        analyze_all_out = gr.Textbox(label="Result", interactive=False)
        analyze_all_btn.click(analyze_all_fn, [secret_box], [analyze_all_out], api_name=False)

        gr.Markdown(
            "### TinyFish live-web check\n"
            "Try each TinyFish API directly. **Search** and **Fetch** are free; **Agent** uses "
            "TinyFish credits (about 1 credit per step). Uses the secret above."
        )
        tf_mode = gr.Radio(["Search (query)", "Fetch (URL)", "Agent: extract comments (URL)"],
                           value="Search (query)", label="TinyFish API")
        tf_target = gr.Textbox(label="Query or URL", placeholder="draft bill public consultation stakeholder comments India")
        tf_btn = gr.Button("Run TinyFish")
        tf_out = gr.Textbox(label="Result", lines=12, interactive=False)
        tf_btn.click(tinyfish_demo_fn, [secret_box, tf_mode, tf_target], [tf_out], api_name=False)


if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860, show_error=True)
