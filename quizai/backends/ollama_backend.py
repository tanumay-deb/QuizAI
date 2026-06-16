"""Ollama local-LLM backend.

Talks to a locally running Ollama server (https://ollama.com) over HTTP.
No third-party SDK required — just stdlib urllib.

Setup (one-time):
  1. Install Ollama:  https://ollama.com/download
  2. Pull a vision model:
        ollama pull qwen2.5vl:7b           # recommended on 8 GB VRAM
        ollama pull minicpm-v:8b           # alternate
        ollama pull llama3.2-vision:11b    # if you have 12 GB+ VRAM
  3. In QuizAI Settings → Provider, pick "Ollama (local)".
     Leave host blank to use the default http://localhost:11434.

Privacy: every prompt stays on your machine. No data leaves the host.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from quizai.backends.base import (
    ANSWER_SYSTEM,
    DETECT_SYSTEM,
    AnswerResult,
    Backend,
    BackendError,
    DetectionResult,
    build_followup_prompt,
    parse_answer_text,
    parse_detection_json,
)
from quizai.logger import get_logger

log = get_logger(__name__)

DEFAULT_HOST = "http://localhost:11434"
_TIMEOUT_S = 180.0  # vision calls on CPU can take a while; be generous

# Pin the context window ourselves instead of inheriting the Ollama app's
# default (the desktop app's "Context length" slider can be set to 256k, which
# allocates a huge KV cache that overflows VRAM and tanks performance). A single
# screenshot + answer fits comfortably in 8k.
_NUM_CTX = 8192
# Keep the model resident between captures so we don't pay a cold reload each
# time (default unloads after 5 min idle).
_KEEP_ALIVE = "30m"


class OllamaBackend(Backend):
    """Local LLM through an Ollama HTTP server.

    `api_key` is repurposed as the host URL (e.g. ``http://localhost:11434``).
    An empty value falls back to ``DEFAULT_HOST``. Ollama itself has no auth.
    """

    name = "ollama"

    def __init__(self, api_key: str, model: str) -> None:
        # Bypass the base ABC's "api_key required" check — Ollama doesn't need one.
        host = (api_key or "").strip().rstrip("/") or DEFAULT_HOST
        if "://" not in host:
            host = "http://" + host
        self._host = host
        self._api_key = api_key  # stored for symmetry with the ABC
        self._model = model or "qwen2.5vl:7b"

    # ----------------------------------------------------------------- vision
    def detect_and_extract_question(self, png_bytes: bytes) -> DetectionResult:
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        body = {
            "model": self._model,
            "stream": False,
            "format": "json",  # forces valid JSON output — perfect for DETECT
            "keep_alive": _KEEP_ALIVE,
            "options": {"temperature": 0.0, "num_predict": 1024, "num_ctx": _NUM_CTX},
            "messages": [
                {"role": "system", "content": DETECT_SYSTEM},
                {
                    "role": "user",
                    "content": "Inspect this screenshot. Return the JSON object as specified.",
                    "images": [b64],
                },
            ],
        }
        text = self._chat(body)
        return parse_detection_json(text)

    # ----------------------------------------------------------------- answer
    def answer_question(self, question: str, context: str | None = None) -> AnswerResult:
        user_text = build_followup_prompt(context, question) if context else question
        body = {
            "model": self._model,
            "stream": False,
            "keep_alive": _KEEP_ALIVE,
            "options": {"temperature": 0.2, "num_predict": 2048, "num_ctx": _NUM_CTX},
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM},
                {"role": "user", "content": user_text},
            ],
        }
        text = self._chat(body)
        return parse_answer_text(text)

    # ----------------------------------------------------------------- warmup
    def warmup(self) -> None:
        """Preload the model + vision encoder so the first real capture is fast.

        Sends one throwaway image request: this pays the cold-start cost (weight
        load + vision projector + CUDA graph) up front. Best-effort — any failure
        (server down, model not pulled) is logged and swallowed.
        """
        try:
            from io import BytesIO

            from PIL import Image

            buf = BytesIO()
            Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="PNG")
            b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
            body = {
                "model": self._model,
                "stream": False,
                "keep_alive": _KEEP_ALIVE,
                "options": {"num_predict": 1, "num_ctx": _NUM_CTX},
                "messages": [
                    {"role": "user", "content": "warmup", "images": [b64]},
                ],
            }
            self._chat(body)
            log.info("Ollama model '%s' warmed up", self._model)
        except Exception as exc:  # never let warmup break startup
            log.debug("Ollama warmup skipped/failed: %s", exc)

    # ----------------------------------------------------------------- HTTP
    def _chat(self, body: dict) -> str:
        url = f"{self._host}/api/chat"
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body_txt = exc.read().decode("utf-8", errors="replace")
            raise BackendError(_pretty_http_error(exc.code, body_txt, self._model)) from exc
        except urllib.error.URLError as exc:
            raise BackendError(
                f"Could not reach Ollama at {self._host}. Is it running? "
                f"Start it with `ollama serve` or open the Ollama app. "
                f"Underlying error: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise BackendError(f"Ollama request failed: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackendError(f"Ollama returned non-JSON response: {raw[:200]}") from exc

        msg = (data or {}).get("message") or {}
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        return str(content or "").strip()


# ---------------------------------------------------------------- helpers
def _pretty_http_error(code: int, body: str, model: str) -> str:
    low = body.lower()
    if code == 404 or "model" in low and ("not found" in low or "no such" in low):
        return (
            f"Ollama doesn't have model '{model}' pulled yet. "
            f"Run in a terminal:  ollama pull {model}"
        )
    if code == 400 and "image" in low:
        return (
            f"Model '{model}' doesn't support images. Pick a vision model in "
            "Settings (e.g. qwen2.5vl:7b or minicpm-v:8b)."
        )
    if code in (502, 503, 504):
        return "Ollama server is temporarily unavailable. Try again in a moment."
    snippet = body.strip().replace("\n", " ")
    if len(snippet) > 200:
        snippet = snippet[:197] + "…"
    return f"Ollama HTTP {code}: {snippet}"
