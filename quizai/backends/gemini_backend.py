"""Google Gemini backend using the google-genai SDK.

Free tier:
  - Gemini 2.5 Flash: ~250 requests/day, ~10 RPM (subject to change)
  - Gemini 2.5 Pro:   smaller daily quota, slower
  - Gemini 2.5 Flash-Lite: highest quota, fastest, slightly weaker reasoning

Get a free key at https://aistudio.google.com/apikey — no card required.
"""

from __future__ import annotations

from quizai.backends.base import (
    ANSWER_SYSTEM,
    DETECT_SYSTEM,
    AnswerResult,
    Backend,
    BackendError,
    DetectionResult,
    parse_answer_text,
    parse_detection_json,
)
from quizai.logger import get_logger

log = get_logger(__name__)


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

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                    "Inspect this screenshot. Return the JSON object as specified.",
                ],
                config=types.GenerateContentConfig(
                    system_instruction=DETECT_SYSTEM,
                    # Vision detection is short — keep ceiling tight to save quota.
                    max_output_tokens=1024,
                    temperature=0.0,
                ),
            )
        except Exception as e:
            raise BackendError(_pretty_gemini_error(e)) from e

        return parse_detection_json(_extract_text(response))

    # ----------------------------------------------------------------- answer
    def answer_question(self, question: str) -> AnswerResult:
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[question],
                config=types.GenerateContentConfig(
                    system_instruction=ANSWER_SYSTEM,
                    max_output_tokens=2048,
                    temperature=0.2,
                ),
            )
        except Exception as e:
            raise BackendError(_pretty_gemini_error(e)) from e

        return parse_answer_text(_extract_text(response))


# ---------------------------------------------------------------------- helpers
def _extract_text(response) -> str:
    """Pull text out of a generate_content response, handling the various
    shapes the SDK might return."""
    # Fast path: response.text is the SDK's convenience accessor.
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    # Manual path: walk candidates -> content.parts -> .text.
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
    """Best-effort cleanup of Gemini error messages for the UI."""
    text = str(e) or e.__class__.__name__
    low = text.lower()
    if "api key" in low or "api_key" in low or "permission" in low or "unauthorized" in low:
        return "Invalid Gemini API key. Get a free one at aistudio.google.com/apikey."
    if "quota" in low or "resource_exhausted" in low or "429" in text:
        return "Gemini free-tier quota hit. Try again in a minute, or upgrade in AI Studio."
    if "safety" in low or "blocked" in low:
        return "Gemini blocked the response for safety reasons. Try rephrasing."
    if "deadline" in low or "timeout" in low:
        return "Gemini API timed out. Try again."
    if "could not resolve" in low or "network" in low or "connection" in low:
        return "Network error reaching Gemini."
    if len(text) > 220:
        text = text[:217] + "…"
    return text
