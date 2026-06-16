"""Tests for the OCR-first router and OCR reading-order helper (no Ollama/OCR engine needed)."""

from __future__ import annotations


def test_plain_text_routes_to_text():
    from quizai.routing import decide_route

    d = decide_route("What is 25% of 200? a) 25 b) 50 c) 75", 0.97, 30)
    assert d.use_vision is False


def test_referential_phrase_routes_to_vision():
    from quizai.routing import decide_route

    for text in [
        "Refer to the figure above. What is the slope?",
        "Which graph represents f(x)=x^2?",
        "In the circuit shown, find the resistance.",
        "Based on the diagram below, name the part.",
    ]:
        assert decide_route(text, 0.99, 40).use_vision is True, text


def test_rendered_math_glyphs_route_to_vision():
    from quizai.routing import decide_route

    # Multiple math glyphs OCR tends to corrupt → vision.
    assert decide_route("Evaluate ∫ x² dx and √144", 0.95, 25).use_vision is True


def test_single_stray_glyph_does_not_trip():
    from quizai.routing import decide_route

    # One degree sign alone shouldn't force vision.
    assert decide_route("The angle is 90° — what is its complement?", 0.97, 40).use_vision is False


def test_low_confidence_routes_to_vision():
    from quizai.routing import decide_route

    assert decide_route("some garbled text here", 0.30, 20, conf_floor=0.55).use_vision is True


def test_empty_ocr_routes_to_vision():
    from quizai.routing import decide_route

    assert decide_route("", 0.0, 0).use_vision is True


def test_reading_order_single_column_sorts_by_y():
    from quizai.ocr import OCRLine, _reading_order

    lines = [
        OCRLine("third", 0.9, x=20, y=300),
        OCRLine("first", 0.9, x=22, y=10),
        OCRLine("second", 0.9, x=21, y=150),
    ]
    assert [ln.text for ln in _reading_order(lines)] == ["first", "second", "third"]


def test_reading_order_two_columns_left_then_right():
    from quizai.ocr import OCRLine, _reading_order

    # Left column x~30, right column x~540 — should read all of left, then right.
    lines = [
        OCRLine("L1", 0.9, x=30, y=20),
        OCRLine("R1", 0.9, x=540, y=20),
        OCRLine("L2", 0.9, x=31, y=90),
        OCRLine("R2", 0.9, x=541, y=90),
    ]
    assert [ln.text for ln in _reading_order(lines)] == ["L1", "L2", "R1", "R2"]
