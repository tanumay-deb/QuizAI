"""OpenAI-compatible backend.

Talks to any server that speaks the OpenAI Chat Completions API over HTTP:

  - OpenAI            (https://api.openai.com/v1)
  - Groq             (https://api.groq.com/openai/v1)
  - OpenRouter       (https://openrouter.ai/api/v1)
  - LM Studio        (http://localhost:1234/v1)
  - any self-hosted OpenAI-compatible server

No third-party SDK required — just stdlib urllib. Vision is sent as a
base64 `data:` image_url, the standard OpenAI multimodal format.

`base_url` selects the server; `api_key` is the Bearer token (local servers
ignore it — a placeholder is fine).
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

DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TIMEOUT_S = 180.0  # local vision servers can take a while on first load


class OpenAIBackend(Backend):
    """Any OpenAI Chat Completions-compatible endpoint."""

    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        # Allow an empty key (local servers don't need one) — bypass the ABC guard.
        self._api_key = (api_key or "").strip()
        self._model = model or "gpt-4o-mini"
        base = (base_url or "").strip().rstrip("/") or DEFAULT_BASE_URL
        if "://" not in base:
            base = "https://" + base
        self._base_url = base

    # ----------------------------------------------------------------- vision
    def detect_and_extract_question(self, png_bytes: bytes) -> DetectionResult:
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        body = {
            "model": self._model,
            "temperature": 0.0,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": DETECT_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Inspect this screenshot. Return the JSON object as specified.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                },
            ],
        }
        return parse_detection_json(self._chat(body))

    # ----------------------------------------------------------------- answer
    def answer_question(self, question: str, context: str | None = None) -> AnswerResult:
        user_text = build_followup_prompt(context, question) if context else question
        body = {
            "model": self._model,
            "temperature": 0.2,
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM},
                {"role": "user", "content": user_text},
            ],
        }
        return parse_answer_text(self._chat(body))

    # ----------------------------------------------------------------- HTTP
    def _chat(self, body: dict) -> str:
        url = f"{self._base_url}/chat/completions"
        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body_txt = exc.read().decode("utf-8", errors="replace")
            raise BackendError(_pretty_http_error(exc.code, body_txt, self._model)) from exc
        except urllib.error.URLError as exc:
            raise BackendError(
                f"Could not reach the OpenAI-compatible server at {self._base_url}. "
                f"Is it running and the Base URL correct? Underlying error: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise BackendError(f"OpenAI-compatible request failed: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackendError(f"Server returned non-JSON response: {raw[:200]}") from exc

        try:
            return str(data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            # Some servers nest errors differently; surface what we can.
            err = (data or {}).get("error")
            if err:
                msg = err.get("message") if isinstance(err, dict) else str(err)
                raise BackendError(f"Server error: {msg}") from exc
            raise BackendError(f"Unexpected response shape: {str(data)[:200]}") from exc


# ---------------------------------------------------------------- helpers
def _pretty_http_error(code: int, body: str, model: str) -> str:
    low = body.lower()
    if code == 401:
        return "Authentication failed (HTTP 401). Check your API key in Settings."
    if code == 404 and "model" in low:
        return f"Model '{model}' not found on this server (HTTP 404). Check the model name."
    if code == 400 and ("image" in low or "vision" in low or "multimodal" in low):
        return (
            f"Model '{model}' may not support images (HTTP 400). "
            "Pick a vision-capable model."
        )
    if code == 429:
        return "Rate limited (HTTP 429). Slow down or check your quota."
    if code in (502, 503, 504):
        return "Server temporarily unavailable. Try again in a moment."
    snippet = body.strip().replace("\n", " ")
    if len(snippet) > 200:
        snippet = snippet[:197] + "…"
    return f"HTTP {code}: {snippet}"
