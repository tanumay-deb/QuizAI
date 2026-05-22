"""Tests for quizai.scheduler."""

from __future__ import annotations

import time


def test_disabled_does_nothing():
    from quizai.scheduler import AutoCaptureScheduler

    hits = []
    sched = AutoCaptureScheduler(lambda: hits.append(1))
    sched.set_interval(0)
    time.sleep(0.2)
    assert hits == []
    sched.stop()


def test_fires_at_interval():
    from quizai.scheduler import AutoCaptureScheduler

    hits = []
    sched = AutoCaptureScheduler(lambda: hits.append(1))
    sched.set_interval(1)
    time.sleep(2.3)
    sched.stop()
    assert len(hits) >= 1, f"expected at least one tick, got {hits}"


def test_reconfigure_changes_interval():
    from quizai.scheduler import AutoCaptureScheduler

    hits = []
    sched = AutoCaptureScheduler(lambda: hits.append(1))
    sched.set_interval(10)  # long
    time.sleep(0.3)
    assert hits == []
    sched.set_interval(1)  # short
    time.sleep(1.5)
    sched.stop()
    assert len(hits) >= 1


def test_callback_exception_does_not_kill_loop():
    from quizai.scheduler import AutoCaptureScheduler

    hits = [0]

    def trigger():
        hits[0] += 1
        if hits[0] == 1:
            raise RuntimeError("first call boom")

    sched = AutoCaptureScheduler(trigger)
    sched.set_interval(1)
    time.sleep(2.3)
    sched.stop()
    # First call raised, but the second should still have fired.
    assert hits[0] >= 2
