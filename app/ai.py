"""AI hints through the Gemini API.

Only fixed prompt types are allowed (hint / review / solution). The old AlgoReady
"custom question" mode forwarded any text to Gemini, which let anyone use the
server's API key as a free chatbot.

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


def build_prompt(mode: str, problem_name: str, statement: str, code: str) -> str:
    return (
        "You are a competitive programming coach.\n"
        f"Problem: {problem_name}\n\n"
        f"Statement:\n{statement[:6000] or '(not available)'}\n\n"
        f"User's current code:\n{code[:8000] or '(empty)'}\n\n"
        f"Task: {PROMPTS[mode]}"
    )


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

    def ask(self, mode: str, problem_name: str, statement: str, code: str) -> str:
        if mode not in PROMPTS:
            raise ValueError(f"Unknown mode: {mode}")
        if not self.enabled:
            return "AI hints are off: set GEMINI_API_KEY in .env to turn them on."
        prompt = build_prompt(mode, problem_name, statement, code)
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
