"""Tests for the overlay's multi-question paginator state machine.

These use the offscreen Qt platform (set in conftest) — no real window pops up.
"""

from __future__ import annotations


def test_paginator_starts_at_first(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    ov.show_questions(["Q1", "Q2", "Q3"])
    assert ov.total_entries() == 3
    assert ov.current_index() == 0


def test_set_answer_updates_specific_slot(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    ov.show_questions(["Q1", "Q2"])
    ov.set_answer_for(0, "A1", "explain")
    ov.set_answer_for(1, "A2", "explain2")
    assert ov._entries[0].answer == "A1"
    assert ov._entries[1].answer == "A2"


def test_set_answer_out_of_range_is_noop(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    ov.show_questions(["Q1"])
    ov.set_answer_for(99, "x", "y")  # should not crash
    assert ov._entries[0].answer is None


def test_show_single_answer_compat(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    ov.show_single_answer("Q", "A", "explain")
    assert ov.total_entries() == 1
    assert ov._entries[0].answer == "A"


def test_show_questions_with_empty_list(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    # Empty list should fall back to the "no question" state, not crash.
    ov.show_questions([])
    assert ov.total_entries() == 0


def test_filters_whitespace_only_questions(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    ov.show_questions(["Q1", "  ", "", "Q2"])
    assert ov.total_entries() == 2


def test_set_error_for_specific_slot(qapp):
    from quizai.overlay import OverlayWindow

    ov = OverlayWindow()
    ov.show_questions(["Q1", "Q2"])
    ov.set_error_for(1, "rate limited")
    assert ov._entries[1].answer is not None
    assert "rate limited" in ov._entries[1].answer
