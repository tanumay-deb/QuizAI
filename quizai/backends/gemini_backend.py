"""Google Gemini backend using the google-genai SDK.

Free tier:
  - Gemini 2.5 Flash:      best balance of capability and quota
  - Gemini 2.5 Pro:        smartest, smaller daily quota
  - Gemini 2.5 Flash-Lite: highest quota, fastest, lighter on reasoning;
                           most resistant to 503 overload errors

Get a free key at https://aistudio.google.com/apikey — no card required.

Transient errors (503 UNAVAILABLE, overloaded, deadline exceeded) are
retried automatically with exponential backoff before being surfaced to
the user.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

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

T = TypeVar("T")

# Retry config for transient errors. 3 attempts, 1s/2s/4s waits.
_MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_S = 1.0


class GeminiBackend(Backend):
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model)
        try:
            from google import genai  # imported lazily
            from google.genai import types  # noqa: F401  (used in methods)
        except ImportError as e:
            raise BackendError(
                "The 'google-genai' package is not installed. Run: pip install google-genai"
            ) from e
        try:
            self._client = genai.Client(api_key=api_key)
        except Exception as e:
            raise BackendError(f"Failed to initialise Gemini client: {e}") from e

    # ----------------------------------------------------------------- vision
    def detect_and_extract_question(self, png_bytes: bytes) -> DetectionResult:
        from google.genai import types

        def _call():
            return self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                    "Inspect this screenshot. Return the JSON object as specified.",
                ],
                config=types.GenerateContentConfig(
                    system_instruction=DETECT_SYSTEM,
                    max_output_tokens=1024,
                    temperature=0.0,
                ),
            )

        try:
            response = _with_retry(_call)
        except Exception as e:
            raise BackendError(_pretty_gemini_error(e)) from e

        return parse_detection_json(_extract_text(response))

    # ----------------------------------------------------------------- answer
    def answer_question(self, question: str, context: str | None = None) -> AnswerResult:
        from google.genai import types

        user_text = build_followup_prompt(context, question) if context else question

        def _call():
            return self._client.models.generate_content(
                model=self._model,
                contents=[user_text],
                config=types.GenerateContentConfig(
                    system_instruction=ANSWER_SYSTEM,
                    max_output_tokens=2048,
                    temperature=0.2,
                ),
            )

        try:
            response = _with_retry(_call)
        except Exception as e:
            raise BackendError(_pretty_gemini_error(e)) from e

        return parse_answer_text(_extract_text(response))


# ---------------------------------------------------------------------- retry
def _with_retry(fn: Callable[[], T]) -> T:
    """Retry transient Gemini errors with exponential backoff.

    Retries on 503 UNAVAILABLE, "overloaded", and "deadline exceeded".
    Other errors (auth, quota, safety, malformed requests) bubble up
    immediately — retrying those would just waste API calls.
    """
    delay = _INITIAL_BACKOFF_S
    last_err: Exception | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if not _is_transient(e) or attempt == _MAX_ATTEMPTS:
                raise
            log.info(
                "Gemini transient error (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                _MAX_ATTEMPTS,
                _short_error(e),
                delay,
            )
            time.sleep(delay)
            delay *= 2

    # Defensive — _MAX_ATTEMPTS >= 1 means we either returned or raised above.
    assert last_err is not None
    raise last_err


def _is_transient(e: Exception) -> bool:
    """True if the error looks like one a retry might fix."""
    text = str(e).lower()
    return (
        "unavailable" in text
        or "503" in str(e)
        or "overloaded" in text
        or "deadline" in text
        or "timeout" in text
        # Google sometimes returns 500 on transient backend issues.
        or "internal error" in text
        or "500" in str(e)
    )


def _short_error(e: Exception) -> str:
    """One-line error string for logs."""
    s = str(e).replace("\n", " ").strip()
    return s if len(s) <= 120 else s[:117] + "…"


# ---------------------------------------------------------------------- helpers
def _extract_text(response) -> str:
    """Pull text out of a generate_content response, handling both shapes
    the SDK can return (text shortcut vs candidates → parts)."""
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    parts_text: list[str] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        for c in candidates:
            content = getattr(c, "content", None)
            parts = getattr(content, "parts", None) or []
            for p in parts:
                t = getattr(p, "text", None)
                if t:
                    parts_text.append(t)
    except Exception:
        pass
    return "\n".join(parts_text).strip()


def _pretty_gemini_error(e: Exception) -> str:
    """Convert raw Gemini exceptions into human-readable UI messages."""
    text = str(e) or e.__class__.__name__
    low = text.lower()

    if "api key" in low or "api_key" in low or "permission" in low or "unauthorized" in low:
        return "Invalid Gemini API key. Get a free one at aistudio.google.com/apikey."
    if "quota" in low or "resource_exhausted" in low or "429" in text:
        return "Gemini free-tier quota hit. Try again in a minute, or upgrade in AI Studio."
    if "unavailable" in low or "503" in text or "overloaded" in low:
        return (
            "Gemini is overloaded right now (even after retries). Try again "
            "shortly, or switch to gemini-2.5-flash-lite in Settings for "
            "better availability."
        )
    if "500" in text or "internal error" in low:
        return "Gemini hit a server error. Try again in a moment."
    if "safety" in low or "blocked" in low:
        return "Gemini blocked the response for safety reasons. Try rephrasing."
    if "deadline" in low or "timeout" in low:
        return "Gemini API timed out. Try again."
    if "could not resolve" in low or "network" in low or "connection" in low:
        return "Network error reaching Gemini."
    if len(text) > 220:
        text = text[:217] + "…"
    return text
