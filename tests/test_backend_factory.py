"""Tests for backend factory + provider-specific error mapping."""

from __future__ import annotations

import pytest


def test_factory_unknown_provider_raises():
    from quizai.backends import create_backend

    with pytest.raises(ValueError, match="Unknown provider"):
        create_backend("nonexistent-provider", "k", "m")


def test_factory_requires_key():
    from quizai.backends import create_backend

    with pytest.raises(ValueError, match="API key"):
        create_backend("gemini", "", "gemini-2.5-flash")
    with pytest.raises(ValueError, match="API key"):
        create_backend("anthropic", "", "claude-sonnet-4-6")


def test_factory_accepts_provider_aliases():
    from quizai.backends import create_backend

    # Aliases that should map to known providers without raising
    g = create_backend("google", "fake", "gemini-2.5-flash")
    assert g.name == "gemini"
    c = create_backend("claude", "fake", "claude-sonnet-4-6")
    assert c.name == "anthropic"


def test_provider_registry_has_required_fields():
    from quizai.backends import PROVIDER_INFO

    for pid, info in PROVIDER_INFO.items():
        assert "label" in info, pid
        assert info.get("models"), pid
        assert "key_help" in info, pid


def test_gemini_error_prettifier():
    from quizai.backends.gemini_backend import _pretty_gemini_error

    assert "Invalid Gemini" in _pretty_gemini_error(Exception("API key not valid"))
    assert "quota" in _pretty_gemini_error(Exception("RESOURCE_EXHAUSTED: 429")).lower()
    assert "safety" in _pretty_gemini_error(Exception("Response blocked due to safety")).lower()
    assert "Network" in _pretty_gemini_error(Exception("could not resolve host"))


def test_gemini_extract_text_shortcut_path():
    from quizai.backends.gemini_backend import _extract_text

    class Resp:
        text = "  hello world  "

    assert _extract_text(Resp()) == "hello world"


def test_gemini_extract_text_candidates_path():
    """Fallback when .text is None — walk candidates -> content.parts."""
    from quizai.backends.gemini_backend import _extract_text

    class Part:
        def __init__(self, t):
            self.text = t

    class Content:
        def __init__(self, parts):
            self.parts = parts

    class Cand:
        def __init__(self, parts):
            self.content = Content(parts)

    class Resp:
        text = None
        candidates = [Cand([Part("hi"), Part("there")])]

    assert _extract_text(Resp()) == "hi\nthere"


def test_gemini_extract_text_empty():
    from quizai.backends.gemini_backend import _extract_text

    class Resp:
        text = None
        candidates = []

    assert _extract_text(Resp()) == ""
