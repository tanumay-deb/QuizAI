"""Tests for the ApiWorker job dispatch logic.

We don't want to make real API calls in tests, so we stub the backend with a
fake that returns canned responses.
"""

from __future__ import annotations


class _FakeBackend:
    """A stand-in for AnthropicBackend / GeminiBackend."""

    name = "fake"
    model = "fake-model"

    def __init__(self, multi=False, raise_on_answer=False):
        self.multi = multi
        self.raise_on_answer = raise_on_answer

    def detect_and_extract_question(self, png_bytes):
        from quizai.backends.base import DetectionResult

        qs = ["Q1", "Q2", "Q3"] if self.multi else ["Q1"]
        return DetectionResult(has_question=True, questions=qs)

    def answer_question(self, q, context=None):
        from quizai.backends.base import AnswerResult, BackendError

        if self.raise_on_answer:
            raise BackendError("simulated failure")
        tag = "followup " if context else ""
        return AnswerResult(answer=f"A for {tag}{q}", explanation=f"because {q}")


def test_no_backend_emits_error(qapp):
    from quizai.app import ApiWorker, _AnswerJob, _ManualJob, _ScreenJob

    worker = ApiWorker()
    errs = []
    worker.api_error.connect(lambda m, i: errs.append((m, i)))

    worker.run_job(_ScreenJob(png=b""))
    worker.run_job(_ManualJob(text="hi"))
    worker.run_job(_AnswerJob(index=2, question="x"))
    worker.run_job("garbage")

    assert len(errs) == 4
    for m, i in errs:
        assert "API key" in m
        assert i == -1


def test_screen_job_single_question(qapp):
    from quizai.app import ApiWorker, _ScreenJob

    worker = ApiWorker()
    worker._backend = _FakeBackend(multi=False)

    questions = []
    answers = []
    worker.questions_extracted.connect(lambda qs: questions.append(list(qs)))
    worker.answer_ready.connect(lambda s, q, a, e, i: answers.append((s, q, a, e, i)))

    worker.run_job(_ScreenJob(png=b"fake"))
    assert questions == [["Q1"]]
    assert len(answers) == 1
    assert answers[0][4] == 0  # index 0
    assert answers[0][1] == "Q1"


def test_screen_job_multi_question(qapp):
    from quizai.app import ApiWorker, _ScreenJob

    worker = ApiWorker()
    worker._backend = _FakeBackend(multi=True)

    questions = []
    answers = []
    worker.questions_extracted.connect(lambda qs: questions.append(list(qs)))
    worker.answer_ready.connect(lambda s, q, a, e, i: answers.append((s, q, a, e, i)))

    worker.run_job(_ScreenJob(png=b"fake"))

    # All 3 questions reported but only the first one auto-answered
    assert questions == [["Q1", "Q2", "Q3"]]
    assert len(answers) == 1
    assert answers[0][4] == 0
    assert answers[0][1] == "Q1"


def test_paginator_answer_job(qapp):
    from quizai.app import ApiWorker, _AnswerJob

    worker = ApiWorker()
    worker._backend = _FakeBackend()
    answers = []
    worker.answer_ready.connect(lambda s, q, a, e, i: answers.append((s, q, a, e, i)))

    worker.run_job(_AnswerJob(index=2, question="Q3"))
    assert len(answers) == 1
    assert answers[0][4] == 2
    assert answers[0][1] == "Q3"


def test_manual_job(qapp):
    from quizai.app import ApiWorker, _ManualJob

    worker = ApiWorker()
    worker._backend = _FakeBackend()
    answers = []
    worker.answer_ready.connect(lambda s, q, a, e, i: answers.append((s, q, a, e, i)))

    worker.run_job(_ManualJob(text="custom Q"))
    assert len(answers) == 1
    assert answers[0][4] == -1  # manual = no index
    assert answers[0][0] == "manual"


def test_unknown_job_with_backend(qapp):
    from quizai.app import ApiWorker

    worker = ApiWorker()
    worker._backend = _FakeBackend()
    errs = []
    worker.api_error.connect(lambda m, i: errs.append((m, i)))
    worker.run_job("garbage")
    assert errs and "Unknown job" in errs[0][0]


def test_backend_error_in_screen_job(qapp):
    from quizai.app import ApiWorker, _ScreenJob

    worker = ApiWorker()
    worker._backend = _FakeBackend(raise_on_answer=True)
    errs = []
    worker.api_error.connect(lambda m, i: errs.append((m, i)))
    worker.run_job(_ScreenJob(png=b"fake"))
    assert errs and "simulated" in errs[0][0]


def test_backend_error_in_paginator_job_carries_index(qapp):
    from quizai.app import ApiWorker, _AnswerJob

    worker = ApiWorker()
    worker._backend = _FakeBackend(raise_on_answer=True)
    errs = []
    worker.api_error.connect(lambda m, i: errs.append((m, i)))
    worker.run_job(_AnswerJob(index=3, question="x"))
    assert errs
    assert errs[0][1] == 3  # error index matches the failed slot
