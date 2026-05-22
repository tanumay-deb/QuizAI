"""LLM backend abstraction.

Lets the rest of the app use any provider through one interface. Currently
ships Anthropic Claude and Google Gemini implementations.

Usage:

    from quizai.backends import create_backend
    backend = create_backend(provider="gemini", api_key=..., model=...)
    det = backend.detect_and_extract_question(png_bytes)
    if det.has_question:
        ans = backend.answer_question(det.question)
"""

from __future__ import annotations

from quizai.backends.base import (
    AnswerResult,
    Backend,
    BackendError,
    DetectionResult,
)


def create_backend(provider: str, api_key: str, model: str) -> Backend:
    """Build a backend by name. Raises ValueError if the name is unknown."""
    p = (provider or "").strip().lower()
    if p in ("anthropic", "claude"):
        from quizai.backends.anthropic_backend import AnthropicBackend

        return AnthropicBackend(api_key=api_key, model=model)
    if p in ("gemini", "google"):
        from quizai.backends.gemini_backend import GeminiBackend

        return GeminiBackend(api_key=api_key, model=model)
    raise ValueError(f"Unknown provider: {provider!r}")


# Map of provider id -> human-readable label and default model list shown in
# Settings. The first entry in each tuple is the default.
PROVIDER_INFO: dict[str, dict] = {
    "gemini": {
        "label": "Google Gemini (free tier available)",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash-lite",
        ],
        "key_help": (
            "Get a free key at https://aistudio.google.com/apikey. No credit card required."
        ),
    },
    "anthropic": {
        "label": "Anthropic Claude (paid)",
        "models": [
            "claude-sonnet-4-6",
            "claude-opus-4-7",
            "claude-haiku-4-5-20251001",
        ],
        "key_help": ("Get a key at https://console.anthropic.com/. Requires billing."),
    },
}


__all__ = [
    "PROVIDER_INFO",
    "AnswerResult",
    "Backend",
    "BackendError",
    "DetectionResult",
    "create_backend",
]
