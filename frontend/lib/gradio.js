/**
 * Minimal client for the Gradio Space's auto-generated HTTP API
 * (POST /call/<api> then read the SSE stream), using only fetch().
 * Shared by the chat widget and the comment-analysis call.
 */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Accepts either the direct app URL (https://user-space.hf.space) or the
 * huggingface.co/spaces/user/space page URL and returns the direct URL.
 * The page URL cannot be called from a browser (it is an HTML page, not the app).
 */
export function normalizeSpaceUrl(url) {
  const u = (url || "").trim().replace(/\/$/, "");
  const m = u.match(/^https?:\/\/huggingface\.co\/spaces\/([^/]+)\/([^/?#]+)/i);
  if (m) {
    const slug = (s) => s.toLowerCase().replace(/[._]/g, "-");
    return `https://${slug(m[1])}-${slug(m[2])}.hf.space`;
  }
  return u;
}

export class ChatError extends Error {
  constructor(message, { retryable = false } = {}) {
    super(message);
    this.retryable = retryable;
  }
}

async function startCall(base, apiName, payload, signal) {
  let res;
  try {
    res = await fetch(`${base}/call/${apiName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data: payload }),
      signal,
    });
  } catch (e) {
    // Network failure, CORS block, or a Space that is still booting.
    throw new ChatError(`Network error reaching ${base} (${e.message})`, { retryable: true });
  }
  if (!res.ok) {
    throw new ChatError(`Space answered HTTP ${res.status} when starting the call`, {
      retryable: res.status >= 500 || res.status === 429,
    });
  }
  let body;
  try {
    body = await res.json();
  } catch {
    // HF serves an HTML "Space is starting / sleeping" page while waking up.
    throw new ChatError("Space returned a non-JSON page (it is probably still waking up)", { retryable: true });
  }
  if (!body || !body.event_id) throw new ChatError("Space did not return an event_id");
  return body.event_id;
}

async function readStream(base, apiName, eventId, signal) {
  const streamRes = await fetch(`${base}/call/${apiName}/${eventId}`, { signal });
  if (!streamRes.ok || !streamRes.body) throw new ChatError(`Stream failed with HTTP ${streamRes.status}`);

  const reader = streamRes.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastData = null;
  let currentEvent = "";
  let errorMessage = null;

  // Gradio's SSE stream sends "generating", "complete", "error" and
  // heartbeats. We keep the last NON-NULL payload, and for "error" events we
  // capture the message that Gradio puts on the data line that follows.
  const handleLine = (line) => {
    const t = line.trim();
    if (!t) return;
    if (t.startsWith("event:")) {
      currentEvent = t.slice(6).trim();
      if (currentEvent === "error" && !errorMessage) errorMessage = "The Space reported an error while answering";
      return;
    }
    if (!t.startsWith("data:")) return;
    const raw = t.slice(5).trim();
    if (!raw || raw === "null") return;
    try {
      const parsed = JSON.parse(raw);
      if (currentEvent === "error") {
        errorMessage = typeof parsed === "string" ? parsed : JSON.stringify(parsed);
      } else if (parsed !== null && parsed !== undefined) {
        lastData = parsed;
      }
    } catch {
      /* partial line; completed on the next chunk */
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n")) !== -1) {
      handleLine(buffer.slice(0, i));
      buffer = buffer.slice(i + 1);
    }
  }
  handleLine(buffer);

  if (errorMessage && lastData === null) throw new ChatError(errorMessage);
  if (lastData === null) throw new ChatError("The Space finished without sending an answer");
  return lastData;
}

/**
 * Calls a Gradio endpoint. Retries the START of the call (not the answer)
 * a few times, because a sleeping free-tier Space needs 20-60s to wake up.
 */
export async function callGradioApi(spaceUrl, apiName, payload, { onStatus } = {}) {
  const base = normalizeSpaceUrl(spaceUrl);
  if (!base) throw new ChatError("NEXT_PUBLIC_JANMAT_SPACE_URL is not set");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const waits = [0, 5000, 10000, 20000];
    let eventId = null;
    let lastErr = null;
    for (let attempt = 0; attempt < waits.length; attempt++) {
      if (waits[attempt]) {
        onStatus?.("Waking up the server, this can take up to a minute…");
        await sleep(waits[attempt]);
      }
      try {
        eventId = await startCall(base, apiName, payload, controller.signal);
        break;
      } catch (e) {
        lastErr = e;
        if (!e.retryable) throw e;
      }
    }
    if (!eventId) throw lastErr || new ChatError("Could not start the call");
    onStatus?.("Thinking…");
    return await readStream(base, apiName, eventId, controller.signal);
  } finally {
    clearTimeout(timer);
  }
}
