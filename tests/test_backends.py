"""Tests for quizai.backends.base parsers."""

from __future__ import annotations

import pytest


# ============================================================ detection parser
def test_detection_clean_multi():
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json('{"has_question":true,"questions":["Q1","Q2","Q3"]}')
    assert r.has_question
    assert r.questions == ["Q1", "Q2", "Q3"]
    # Singular field mirrors the first.
    assert r.question == "Q1"


def test_detection_legacy_single():
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json('{"has_question":true,"question":"only one"}')
    assert r.has_question
    assert r.questions == ["only one"]
    assert r.question == "only one"


def test_detection_empty_array_means_no_question():
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json('{"has_question":true,"questions":[]}')
    assert not r.has_question


def test_detection_caps_at_five():
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json('{"has_question":true,"questions":["a","b","c","d","e","f","g","h"]}')
    assert len(r.questions) == 5


def test_detection_filters_non_strings():
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json('{"has_question":true,"questions":["good",null,123,"alsogood"]}')
    assert r.questions == ["good", "alsogood"]


def test_detection_filters_empty_strings():
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json('{"has_question":true,"questions":["good","  ",""]}')
    assert r.questions == ["good"]


def test_detection_markdown_fenced():
    from quizai.backends.base import parse_detection_json

    raw = '```json\n{"has_question":true,"questions":["Q1","Q2"]}\n```'
    r = parse_detection_json(raw)
    assert r.has_question
    assert len(r.questions) == 2


def test_detection_json_inside_prose():
    from quizai.backends.base import parse_detection_json

    raw = 'Sure thing! Here is the JSON: {"has_question":true,"question":"X"} all done'
    r = parse_detection_json(raw)
    assert r.has_question
    assert r.question == "X"


@pytest.mark.parametrize("junk", ["", "not json", "{ broken", "[]"])
def test_detection_handles_junk(junk):
    from quizai.backends.base import parse_detection_json

    r = parse_detection_json(junk)
    assert not r.has_question


# ================================================================ answer parser
def test_answer_clean():
    from quizai.backends.base import parse_answer_text

    r = parse_answer_text("ANSWER:\nB. Mitochondria\n\nEXPLANATION:\nThey produce ATP.")
    assert r.answer == "B. Mitochondria"
    assert "ATP" in r.explanation


def test_answer_case_insensitive_labels():
    from quizai.backends.base import parse_answer_text

    r = parse_answer_text("answer: yes\nexplanation: because reasons")
    assert r.answer == "yes"
    assert r.explanation == "because reasons"


def test_answer_fallback_no_labels():
    from quizai.backends.base import parse_answer_text

    r = parse_answer_text("just a plain response")
    assert r.answer == "just a plain response"
    assert r.explanation == ""


def test_answer_empty():
    from quizai.backends.base import parse_answer_text

    r = parse_answer_text("")
    assert r.answer == "(no response)"
    assert r.explanation == ""


# ================================================================== DetectionResult
def test_detection_result_normalises_legacy_call():
    """If callers construct with question=... only, questions should populate."""
    from quizai.backends.base import DetectionResult

    r = DetectionResult(has_question=True, question="only one")
    assert r.questions == ["only one"]


def test_detection_result_normalises_list_only():
    """And vice versa."""
    from quizai.backends.base import DetectionResult

    r = DetectionResult(has_question=True, questions=["a", "b"])
    assert r.question == "a"
