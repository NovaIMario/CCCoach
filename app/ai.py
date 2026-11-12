"""AI hints through the Gemini API.

Quick actions (hint / review / solution) use fixed prompts. Free-text chat is allowed too,
but it is scoped: the prompt pins the model to the current problem and to programming
help, messages and history are length-capped, and the endpoint is rate limited. (The old
AlgoReady "custom question" mode forwarded any text unscoped, which let anyone use the
server's API key as a free general chatbot.)

Gemini models sometimes return 503 ("high demand") or 429 (rate limited). When that
happens we try the next model in a fallback list instead of failing.
"""
import logging
import time
from collections import defaultdict, deque

log = logging.getLogger(__name__)

PROMPTS = {
    "hint": "Give ONE short hint (2-3 sentences) that points toward the key idea. "
            "Do not reveal the full algorithm or any code.",
    "review": "Review the user's code for this problem. Point out bugs, wrong edge cases or "
              "complexity problems, in at most 5 bullet points. Do not rewrite the whole solution.",
    "solution": "Explain the intended solution step by step, state its time complexity, "
                "then give a clean, commented C++ solution.",
}

# Tried in order after the configured model when it is overloaded. The Lite models are
# smaller and much less often overloaded (in testing they answered in ~1s while every
# full Flash model was timing out), so they make a good safety net.
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
RETRYABLE = (404, 429, 500, 503, 504)  # 404: model retired for this key
PER_MODEL_TIMEOUT_MS = 25_000          # an overloaded model can hang ~60s before a 504


class AIUnavailable(Exception):
    """Every model we tried was overloaded."""


class RateLimiter:
    """At most `limit` calls per `window` seconds per key (e.g. client IP)."""

    def __init__(self, limit: int = 10, window: float = 60):
        self.limit, self.window = limit, window
        self.calls: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now, q = time.time(), self.calls[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


CHAT_RULES = (
    "Answer the user's latest message. Only help with this problem, its algorithms, the user's code "
    "and closely related programming topics; if asked about anything else, briefly decline in your own "
    "words and steer back to the problem. Unless the user explicitly asks for the full solution, guide "
    "them with hints and questions rather than giving it away. Be concise; use Markdown, and $...$ for maths."
)
MAX_MESSAGE = 2000        # characters in the user's chat message
MAX_HISTORY = 10          # earlier turns sent back to the model
MAX_HISTORY_CHARS = 3000  # per earlier turn


def format_history(history: list[dict] | None) -> str:
    lines = []
    for turn in (history or [])[-MAX_HISTORY:]:
        who = "User" if turn.get("role") == "user" else "Coach"
        lines.append(f"{who}: {str(turn.get('text', ''))[:MAX_HISTORY_CHARS]}")
    return "\n\n".join(lines)


def build_prompt(mode: str, problem_name: str, statement: str, code: str,
                 message: str = "", history: list[dict] | None = None) -> str:
    parts = [
        "You are a competitive programming coach.",
        f"Problem: {problem_name}",
        f"Statement:\n{statement[:6000] or '(not available)'}",
        f"User's current code:\n{code[:8000] or '(empty)'}",
    ]
    convo = format_history(history)
    if convo:
        parts.append(f"Conversation so far:\n{convo}")
    if mode == "chat":
        parts.append(f"Task: {CHAT_RULES}")
        parts.append(f"User's latest message:\n{message[:MAX_MESSAGE]}")
    else:
        parts.append(f"Task: {PROMPTS[mode]}")
    return "\n\n".join(parts)


def status_code(err: Exception) -> int | None:
    return getattr(err, "code", None) or getattr(err, "status_code", None)


class HintService:
    def __init__(self, api_key: str, model: str, fallbacks: list[str] | None = None, client=None):
        self.models = [model] + [m for m in (fallbacks if fallbacks is not None else FALLBACK_MODELS) if m != model]
        self.client = client
        if self.client is None and api_key:
            from google import genai
            from google.genai import types
            # one quick attempt per model; we move on to the next model instead of retrying the busy one
            self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
                timeout=PER_MODEL_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)))

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def ask(self, mode: str, problem_name: str, statement: str, code: str,
            message: str = "", history: list[dict] | None = None) -> str:
        if mode not in PROMPTS and mode != "chat":
            raise ValueError(f"Unknown mode: {mode}")
        if mode == "chat" and not message.strip():
            raise ValueError("Type a message first")
        if not self.enabled:
            return "AI hints are off: set GEMINI_API_KEY in .env to turn them on."
        prompt = build_prompt(mode, problem_name, statement, code, message, history)
        for model in self.models:
            try:
                resp = self.client.models.generate_content(model=model, contents=prompt)
                self.last_model = model
                return resp.text or "(empty response)"
            except Exception as e:
                if status_code(e) in RETRYABLE:
                    log.warning("Gemini model %s unavailable (%s), trying the next one", model, status_code(e))
                    continue  # this model is busy, try the next one
                raise
        raise AIUnavailable("All Gemini models are busy right now. Try again in a minute.")
