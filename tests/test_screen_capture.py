"""Tests for quizai.screen_capture (no actual screen grab — that needs a display)."""

from __future__ import annotations


def test_downscale_large_image():
    from PIL import Image

    from quizai.screen_capture import MAX_DIM, _downscale

    big = Image.new("RGB", (4000, 2000), "red")
    small = _downscale(big, MAX_DIM)
    assert max(small.size) <= MAX_DIM
    # Aspect preserved
    assert small.size == (MAX_DIM, MAX_DIM // 2)


def test_downscale_skips_small_image():
    from PIL import Image

    from quizai.screen_capture import MAX_DIM, _downscale

    tiny = Image.new("RGB", (100, 50), "blue")
    same = _downscale(tiny, MAX_DIM)
    assert same.size == (100, 50)


def test_downscale_exactly_max():
    from PIL import Image

    from quizai.screen_capture import _downscale

    exact = Image.new("RGB", (1568, 800), "green")
    result = _downscale(exact, 1568)
    assert result.size == (1568, 800)  # unchanged
