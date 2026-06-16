"""Anthropic Claude backend."""

from __future__ import annotations

import base64

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


class AnthropicBackend(Backend):
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model)
        try:
            from anthropic import Anthropic  # imported lazily
        except ImportError as e:
            raise BackendError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from e
        self._client = Anthropic(api_key=api_key)

    # ----------------------------------------------------------------- vision
    def detect_and_extract_question(self, png_bytes: bytes) -> DetectionResult:
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=DETECT_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Inspect this screenshot. Return the JSON object as specified."
                                ),
                            },
                        ],
                    }
                ],
            )
        except Exception as e:
            raise BackendError(str(e)) from e

        return parse_detection_json(_extract_text(msg))

    # ----------------------------------------------------------------- answer
    def answer_question(self, question: str, context: str | None = None) -> AnswerResult:
        user_text = build_followup_prompt(context, question) if context else question
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=ANSWER_SYSTEM,
                messages=[{"role": "user", "content": user_text}],
            )
        except Exception as e:
            raise BackendError(str(e)) from e
        return parse_answer_text(_extract_text(msg))


def _extract_text(msg) -> str:
    parts: list[str] = []
    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "\n".join(parts).strip()
