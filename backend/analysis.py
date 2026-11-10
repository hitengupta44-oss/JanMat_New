"""
Comment analysis for SIH 2025 PS SIH25035 ("Sentiment analysis of comments
received through E-consultation module").

For every public comment on a bill this module produces:
  - a sentiment label (positive / negative / neutral) with a confidence score
  - a one-line summary of the comment
and for every bill (and for all bills together):
  - an overall summary of what commenters are saying, plus key points.

The word cloud is drawn on the website from the comment text itself, so it
works instantly even before analysis has run.

Groq does the analysis. If Groq is unavailable, a local VADER lexicon model
gives the sentiment so comments still get labelled.
"""
import json
import logging
import re
from typing import List, Optional

import requests

import db
from config import GROQ_API_KEY, GROQ_CHAT_MODEL

logger = logging.getLogger("janmat.analysis")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ALL_TOPICS_KEY = "janmat:all"
SENTIMENTS = ("positive", "negative", "neutral")

COMMENT_PROMPT = """You analyse public comments submitted on draft Indian legislation \
(an e-consultation). Read the comment and return ONLY a JSON object:
{"sentiment": "positive" | "negative" | "neutral",
 "confidence": <number 0 to 1>,
 "summary": "<one plain-English sentence, max 25 words, saying what the commenter wants or thinks>"}

Guidance:
- positive = supports the bill or a provision, welcomes it, or praises it.
- negative = opposes, objects, raises a concern, or says something will cause harm.
- neutral = asks a question, gives a factual note, or a suggestion with no clear stance.
- A suggestion to improve a provision the commenter otherwise supports is positive; \
a suggestion because the provision is harmful is negative.
- Comments may be in Hindi or Hinglish; still answer in English.
"""

TOPIC_PROMPT = """You summarise public feedback received on a draft Indian bill for \
the officials who must review it. You get every comment, each tagged with its \
sentiment. Return ONLY a JSON object:
{"summary": "<3-5 sentences: overall mood, the main points of support, the main objections>",
 "key_points": ["<short point>", ... up to 6]}

Be faithful to the comments; don't invent points. Mention roughly how opinion is \
split. Use plain language.
"""

ALL_PROMPT = """You summarise public feedback across several draft Indian bills for \
officials. You get, for each bill, its comment counts by sentiment and a summary of \
its comments. Return ONLY a JSON object:
{"summary": "<3-5 sentences on the overall picture: which bills draw most support or \
opposition and the recurring themes>",
 "key_points": ["<short point>", ... up to 6]}
"""


# ------------------------------------------------------------------ helpers

def _groq_json(system: str, user: str, temperature: float = 0.1) -> dict:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_CHAT_MODEL,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"] or ""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError(f"Groq did not return JSON: {content[:200]}")
    return json.loads(match.group(0))


_vader = None


def _vader_sentiment(text: str):
    """Local fallback: VADER compound score -> label."""
    global _vader
    if _vader is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
    compound = _vader.polarity_scores(text)["compound"]
    if compound >= 0.05:
        return "positive", round(min(1.0, 0.5 + compound / 2), 2)
    if compound <= -0.05:
        return "negative", round(min(1.0, 0.5 - compound / 2), 2)
    return "neutral", round(1 - abs(compound) * 10, 2)


def _fallback_summary(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", text.strip())[0]
    words = first.split()
    return " ".join(words[:25]) + ("…" if len(words) > 25 else "")


# ------------------------------------------------------------ one comment

def analyze_text(text: str) -> dict:
    """Returns {"sentiment", "score", "summary", "engine"}."""
    text = (text or "").strip()
    try:
        out = _groq_json(COMMENT_PROMPT, f"COMMENT:\n{text[:4000]}")
        sentiment = str(out.get("sentiment", "")).lower().strip()
        if sentiment not in SENTIMENTS:
            raise ValueError(f"bad sentiment {sentiment!r}")
        try:
            score = max(0.0, min(1.0, float(out.get("confidence", 0.8))))
        except (TypeError, ValueError):
            score = 0.8
        summary = str(out.get("summary") or "").strip() or _fallback_summary(text)
        return {"sentiment": sentiment, "score": score, "summary": summary, "engine": "groq"}
    except Exception as exc:
        logger.warning("Groq comment analysis failed, using VADER: %s", exc)
        sentiment, score = _vader_sentiment(text)
        return {"sentiment": sentiment, "score": score, "summary": _fallback_summary(text), "engine": "vader"}


def analyze_comment(comment_id: int) -> Optional[dict]:
    comment = db.get_comment(comment_id)
    if not comment:
        return None
    result = analyze_text(comment["body"])
    db.save_comment_analysis(comment_id, result["sentiment"], result["score"], result["summary"])
    return {**comment, **result}


# ------------------------------------------------------------- one topic

def _counts(comments: List[dict]) -> dict:
    counts = {s: 0 for s in SENTIMENTS}
    for c in comments:
        if c.get("sentiment") in counts:
            counts[c["sentiment"]] += 1
    return counts


def refresh_topic(topic_key: str) -> Optional[dict]:
    """Re-summarise every comment on one bill and store it in topic_insights."""
    comments = db.list_comments(topic_key=topic_key)
    if not comments:
        return None
    title = next((c["topic_title"] for c in comments if c.get("topic_title")), topic_key)

    lines, used = [], 0
    for c in comments:
        line = f"- ({c.get('sentiment') or 'unlabelled'}) {c['body'].strip()}"
        if used + len(line) > 14000:
            break
        lines.append(line)
        used += len(line)

    counts = _counts(comments)
    header = (f"BILL: {title}\nCOMMENTS: {len(comments)} "
              f"(positive {counts['positive']}, negative {counts['negative']}, neutral {counts['neutral']})")
    try:
        out = _groq_json(TOPIC_PROMPT, f"{header}\n\n" + "\n".join(lines), temperature=0.2)
        summary = str(out.get("summary") or "").strip()
        points = [str(p).strip() for p in (out.get("key_points") or []) if str(p).strip()][:6]
    except Exception as exc:
        logger.warning("Groq topic summary failed for %s: %s", topic_key, exc)
        summary = (f"{len(comments)} comments: {counts['positive']} positive, "
                   f"{counts['negative']} negative, {counts['neutral']} neutral.")
        points = [c["summary"] for c in comments if c.get("summary")][:5]

    db.upsert_topic_insight(topic_key, title, summary, points, len(comments))
    return {"topic_key": topic_key, "topic_title": title, "overall_summary": summary,
            "key_points": points, "comment_count": len(comments), "counts": counts}


def refresh_all_topics_summary() -> Optional[dict]:
    """One summary across every bill, built from the per-bill summaries."""
    comments = db.list_comments()
    if not comments:
        return None
    insights = {i["topic_key"]: i for i in db.list_topic_insights() if i["topic_key"] != ALL_TOPICS_KEY}

    by_topic = {}
    for c in comments:
        by_topic.setdefault(c["topic_key"], []).append(c)

    blocks = []
    for key, items in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        counts = _counts(items)
        ins = insights.get(key) or {}
        title = ins.get("topic_title") or items[0].get("topic_title") or key
        blocks.append(f"BILL: {title}\nCounts: positive {counts['positive']}, negative {counts['negative']}, "
                      f"neutral {counts['neutral']}\nSummary: {ins.get('overall_summary') or '(none yet)'}")

    total = _counts(comments)
    try:
        out = _groq_json(ALL_PROMPT, "\n\n".join(blocks)[:15000], temperature=0.2)
        summary = str(out.get("summary") or "").strip()
        points = [str(p).strip() for p in (out.get("key_points") or []) if str(p).strip()][:6]
    except Exception as exc:
        logger.warning("Groq all-bills summary failed: %s", exc)
        summary = (f"{len(comments)} comments across {len(by_topic)} bills and topics: {total['positive']} positive, "
                   f"{total['negative']} negative, {total['neutral']} neutral.")
        points = []

    db.upsert_topic_insight(ALL_TOPICS_KEY, "All bills", summary, points, len(comments))
    return {"overall_summary": summary, "key_points": points, "comment_count": len(comments)}


# ----------------------------------------------------------- batch (admin)

def analyze_pending_and_refresh() -> dict:
    """Label every comment that hasn't been analysed yet, then rebuild all summaries."""
    pending = db.list_comments(only_unanalyzed=True)
    analysed, failed = 0, 0
    for c in pending:
        try:
            r = analyze_text(c["body"])
            db.save_comment_analysis(c["id"], r["sentiment"], r["score"], r["summary"])
            analysed += 1
        except Exception:
            logger.exception("Analysing comment %s failed", c["id"])
            failed += 1

    topics = {c["topic_key"] for c in db.list_comments()}
    for key in topics:
        try:
            refresh_topic(key)
        except Exception:
            logger.exception("Refreshing topic %s failed", key)
    refresh_all_topics_summary()
    return {"analysed": analysed, "failed": failed, "topics": len(topics)}
