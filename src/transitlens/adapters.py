"""Model adapters. An adapter takes a task and its image and returns the model's raw reply.

`oracle` and `random` are not models: the oracle shows the tasks are solvable from the drawing,
and the random baseline shows they cannot be solved by guessing.
"""

from __future__ import annotations

import base64
import json
import os
import random
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

import requests

from .parse_svg import parse_svg
from .questions import answer_for

PROMPT = (
    "You are looking at a schematic transit map. Each coloured line is a transit line, and the "
    "legend names the colours. White circles are stations; a larger circle is an interchange "
    "where you can change between the lines that meet there. Two lines that cross without a "
    "station circle at the crossing are NOT connected. Use only the map to answer.\n\n"
    "Question: {question}\n\n"
    "Reply with the final answer only: a number, a comma-separated list of line colours, a "
    "station name written exactly as on the map (in Devanagari if the map uses it), or the "
    "word 'impossible'. No explanation."
)

REQUEST_TIMEOUT_S = 90
MAX_RETRIES = 6
MAX_OUTPUT_TOKENS = 4096  # thinking models spend part of this on reasoning before they answer


class Adapter(ABC):
    name: str

    @abstractmethod
    def answer(self, task: dict[str, object], png: bytes) -> str: ...


class OracleAdapter(Adapter):
    """Answers from the SVG alone. It must score 100%, which proves the tasks are solvable."""

    name = "oracle"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def answer(self, task: dict[str, object], png: bytes) -> str:
        svg = (self.data_dir / str(task["svg"])).read_text(encoding="utf-8")
        parsed = parse_svg(svg)
        return answer_for(str(task["kind"]), dict(task["params"]), parsed.network)  # type: ignore[arg-type]


class RandomAdapter(Adapter):
    """Chance baseline: sees no image, so it can only guess from the question text."""

    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def answer(self, task: dict[str, object], png: bytes) -> str:
        kind = str(task["answer_type"])
        if kind == "int":
            return str(self.rng.randint(0, 4))
        if kind == "set":
            colours = ["Red", "Blue", "Green", "Orange", "Purple", "Brown"]
            return ", ".join(self.rng.sample(colours, 2))
        return "Unknown"


def _post_with_retry(url: str, headers: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
    for attempt in range(MAX_RETRIES):
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_S)
        if response.status_code in (429, 500, 502, 503) and attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt * 2)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("unreachable")


class GeminiAdapter(Adapter):
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.name = f"gemini:{model}"
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

    def answer(self, task: dict[str, object], png: bytes) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [
                {"text": PROMPT.format(question=task["question"])},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
            ]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": MAX_OUTPUT_TOKENS},
        }
        data = _post_with_retry(url, {"x-goog-api-key": self.api_key}, payload)
        # A reply cut off before any text (finishReason MAX_TOKENS) has no "parts": treat it as empty.
        content = data["candidates"][0].get("content", {})  # type: ignore[index]
        return "".join(part.get("text", "") for part in content.get("parts", []))


class OpenAICompatibleAdapter(Adapter):
    """Any server that speaks the OpenAI chat-completions API with image input."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None) -> None:
        self.name = f"openai-compatible:{model}"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set")

    def answer(self, task: dict[str, object], png: bytes) -> str:
        image = "data:image/png;base64," + base64.b64encode(png).decode()
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT.format(question=task["question"])},
                {"type": "image_url", "image_url": {"url": image}},
            ]}],
        }
        data = _post_with_retry(
            f"{self.base_url}/chat/completions", {"Authorization": f"Bearer {self.api_key}"}, payload
        )
        return str(data["choices"][0]["message"]["content"])  # type: ignore[index]


class ReplayAdapter(Adapter):
    """Scores replies collected outside the harness (e.g. a model that read the images in a chat
    session). Each line of the file is {"task_id": ..., "reply": ...}."""

    def __init__(self, path: Path, name: str = "replay") -> None:
        self.name = name
        self.replies: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                self.replies[str(row["task_id"])] = str(row["reply"])

    def answer(self, task: dict[str, object], png: bytes) -> str:
        try:
            return self.replies[str(task["id"] if "id" in task else task["task_id"])]
        except KeyError as exc:
            raise LookupError(f"no reply recorded for {exc}") from exc


class ThrottledAdapter(Adapter):
    """Spaces calls at least `delay` seconds apart, to stay under a provider's rate limit."""

    def __init__(self, inner: Adapter, delay: float) -> None:
        self.inner, self.delay, self.name = inner, delay, inner.name
        self._lock = threading.Lock()
        self._next = 0.0

    def answer(self, task: dict[str, object], png: bytes) -> str:
        with self._lock:
            wait = self._next - time.monotonic()
            self._next = max(self._next, time.monotonic()) + self.delay
        if wait > 0:
            time.sleep(wait)
        return self.inner.answer(task, png)
