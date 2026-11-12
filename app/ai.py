"""AI hints through the Gemini API.

Only fixed prompt types are allowed (hint / review / solution). The old AlgoReady
"custom question" mode forwarded any text to Gemini, which let anyone use the
server's API key as a free chatbot.
"""
import time
from collections import defaultdict, deque

PROMPTS = {
    "hint": "Give ONE short hint (2-3 sentences) that points toward the key idea. "
            "Do not reveal the full algorithm or any code.",
    "review": "Review the user's code for this problem. Point out bugs, wrong edge cases or "
              "complexity problems, in at most 5 bullet points. Do not rewrite the whole solution.",
    "solution": "Explain the intended solution step by step, state its time complexity, "
                "then give a clean, commented C++ solution.",
}


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


class HintService:
    def __init__(self, api_key: str, model: str):
        self.model = model
        self.client = None
        if api_key:
            from google import genai
            self.client = genai.Client(api_key=api_key)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def ask(self, mode: str, problem_name: str, statement: str, code: str) -> str:
        if mode not in PROMPTS:
            raise ValueError(f"Unknown mode: {mode}")
        if not self.enabled:
            return "AI hints are off: set GEMINI_API_KEY in .env to turn them on."
        resp = self.client.models.generate_content(model=self.model, contents=build_prompt(mode, problem_name, statement, code))
        return resp.text or "(empty response)"
