import pytest

from app.ai import AIUnavailable, HintService


class APIError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content(self, model, contents):
        self.calls.append(model)
        result = self.behaviour[model]
        if isinstance(result, Exception):
            raise result
        return type("Resp", (), {"text": result})()


def service(behaviour):
    client = type("Client", (), {"models": FakeModels(behaviour)})()
    return HintService("", "main", fallbacks=["backup", "last"], client=client), client.models


def test_uses_main_model_when_available():
    h, models = service({"main": "hi", "backup": "no", "last": "no"})
    assert h.ask("hint", "P", "", "") == "hi"
    assert models.calls == ["main"]


def test_falls_back_when_overloaded_or_retired():
    h, models = service({"main": APIError(503), "backup": APIError(404), "last": "from last"})
    assert h.ask("hint", "P", "", "") == "from last"
    assert models.calls == ["main", "backup", "last"]
    assert h.last_model == "last"


def test_all_busy_raises_friendly_error():
    h, _ = service({"main": APIError(503), "backup": APIError(504), "last": APIError(429)})
    with pytest.raises(AIUnavailable):
        h.ask("hint", "P", "", "")


def test_other_errors_are_not_hidden():
    h, models = service({"main": APIError(400), "backup": "x", "last": "x"})
    with pytest.raises(APIError):
        h.ask("hint", "P", "", "")
    assert models.calls == ["main"]


def test_chat_sends_message_and_recent_history_only():
    from app.ai import CHAT_RULES, MAX_HISTORY, build_prompt
    history = [{"role": "user" if i % 2 == 0 else "coach", "text": f"turn {i}"} for i in range(MAX_HISTORY + 4)]
    prompt = build_prompt("chat", "P", "stmt", "code", "why TLE?", history)
    assert "why TLE?" in prompt and CHAT_RULES in prompt
    assert "turn 0" not in prompt and f"turn {MAX_HISTORY + 3}" in prompt  # oldest turns dropped


def test_chat_needs_a_message():
    h, models = service({"main": "hi", "backup": "x", "last": "x"})
    with pytest.raises(ValueError):
        h.ask("chat", "P", "", "", message="   ")
    assert h.ask("chat", "P", "", "", message="help") == "hi"
