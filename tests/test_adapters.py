import base64

import pytest

from transitlens import adapters
from transitlens.adapters import GeminiAdapter, OpenAICompatibleAdapter, PROMPT

TASK = {"question": "How many stations are on the Red Line?", "answer_type": "int"}
PNG = b"\x89PNG-fake"


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._body


def test_gemini_sends_prompt_and_image_and_reads_text(monkeypatch):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, payload=json)
        return FakeResponse(body={"candidates": [{"content": {"parts": [{"text": "7"}]}}]})

    monkeypatch.setattr(adapters.requests, "post", fake_post)
    reply = GeminiAdapter("gemini-test", api_key="k").answer(TASK, PNG)
    assert reply == "7"
    assert "gemini-test:generateContent" in sent["url"]
    assert sent["headers"] == {"x-goog-api-key": "k"}  # key goes in a header, never in the URL
    assert "k" not in sent["url"]
    parts = sent["payload"]["contents"][0]["parts"]
    assert TASK["question"] in parts[0]["text"]
    assert base64.b64decode(parts[1]["inline_data"]["data"]) == PNG
    assert sent["payload"]["generationConfig"]["temperature"] == 0


def test_openai_compatible_sends_data_url(monkeypatch):
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, headers=headers, payload=json)
        return FakeResponse(body={"choices": [{"message": {"content": "Red, Blue"}}]})

    monkeypatch.setattr(adapters.requests, "post", fake_post)
    reply = OpenAICompatibleAdapter("https://llm.example/v1/", "m", api_key="secret").answer(TASK, PNG)
    assert reply == "Red, Blue"
    assert sent["url"] == "https://llm.example/v1/chat/completions"
    assert sent["headers"] == {"Authorization": "Bearer secret"}
    image = sent["payload"]["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


def test_retries_on_rate_limit_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(1)
        if len(calls) < 3:
            return FakeResponse(status=429)
        return FakeResponse(body={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr(adapters.requests, "post", fake_post)
    monkeypatch.setattr(adapters.time, "sleep", lambda s: None)
    assert GeminiAdapter("m", api_key="k").answer(TASK, PNG) == "ok"
    assert len(calls) == 3


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(adapters.requests, "post", lambda *a, **k: FakeResponse(status=503))
    monkeypatch.setattr(adapters.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        GeminiAdapter("m", api_key="k").answer(TASK, PNG)


def test_missing_keys_fail_fast(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        GeminiAdapter("m")
    with pytest.raises(RuntimeError):
        OpenAICompatibleAdapter("https://x", "m")


def test_prompt_states_the_no_station_no_connection_rule():
    assert "NOT connected" in PROMPT and "{question}" in PROMPT


def test_truncated_gemini_reply_is_empty_not_a_crash(monkeypatch):
    body = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"role": "model"}}]}
    monkeypatch.setattr(adapters.requests, "post", lambda *a, **k: FakeResponse(body=body))
    assert GeminiAdapter("m", api_key="k").answer(TASK, PNG) == ""


def test_throttle_spaces_calls_apart(monkeypatch):
    from transitlens.adapters import Adapter, ThrottledAdapter

    class Inner(Adapter):
        name = "inner"

        def answer(self, task, png):
            return "x"

    sleeps = []
    clock = [100.0]
    monkeypatch.setattr(adapters.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(adapters.time, "sleep", lambda s: sleeps.append(s))
    throttled = ThrottledAdapter(Inner(), delay=2.0)
    assert throttled.name == "inner"
    for _ in range(3):
        assert throttled.answer({}, b"") == "x"
    assert sleeps == [2.0, 4.0]  # first call goes straight through, then 2s and 4s behind it
