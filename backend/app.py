"""
JanMat — single Gradio Space.

Replaces the old bills/themes/sentiment dashboard with a chat interface that
answers questions using Groq, grounded in the full text of scraped PRS bill
pages + PDFs + articles (stored in Supabase), with optional voice in/out via
Sarvam AI.

Everything lives in this one Space, same as your original setup — no
separate frontend needed.
"""
import logging
import threading

import gradio as gr

import db
import rag
import voice
from config import CRON_SECRET
from ingest_pipeline import run_ingestion

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


def _ensure_session(session_id):
    return session_id or db.create_session()


def _format_answer_with_sources(answer: str, citations: list) -> str:
    if not citations:
        return answer
    lines = "\n".join(
        f"[{c['n']}] {c['title']} ({c['kind']}) — {c['url']}" for c in citations
    )
    return f"{answer}\n\n**Sources:**\n{lines}"


def chat_fn(message, history, session_id):
    if not message or not message.strip():
        return history, "", session_id

    session_id = _ensure_session(session_id)
    db.save_message(session_id, "user", message, input_mode="text")

    result = rag.answer_question(session_id, message)
    db.save_message(session_id, "assistant", result["answer"], citations=result["citations"], input_mode="text")

    display_answer = _format_answer_with_sources(result["answer"], result["citations"])
    history = history + [(message, display_answer)]
    return history, "", session_id


def voice_fn(audio_path, history, session_id):
    if audio_path is None:
        return history, session_id, None

    session_id = _ensure_session(session_id)

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
        f"failed: {summary.get('failed', 0)}"
    )


with gr.Blocks(title="JanMat — Ask about Indian Bills") as demo:
    gr.Markdown(
        "# 🏛️ JanMat\n"
        "Ask questions about Indian legislative bills, their full PDF briefs, "
        "related articles, and public opinion — by text or voice. Answers are "
        "grounded in what's actually been read into the knowledge base, with sources cited."
    )

    session_state = gr.State(value=None)

    chatbot = gr.Chatbot(height=460, label="Conversation")

    with gr.Row():
        msg = gr.Textbox(placeholder="e.g. What does the Digital Data Protection Bill say about consent?",
                          scale=4, show_label=False)
        send_btn = gr.Button("Send", scale=1, variant="primary")

    with gr.Row():
        mic = gr.Audio(sources=["microphone"], type="filepath", label="Or ask by voice")
        answer_audio = gr.Audio(label="Spoken answer", autoplay=True)

    send_btn.click(chat_fn, [msg, chatbot, session_state], [chatbot, msg, session_state], api_name="chat")
    msg.submit(chat_fn, [msg, chatbot, session_state], [chatbot, msg, session_state], api_name=False)
    mic.stop_recording(voice_fn, [mic, chatbot, session_state], [chatbot, session_state, answer_audio], api_name="chat_voice")

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


if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
