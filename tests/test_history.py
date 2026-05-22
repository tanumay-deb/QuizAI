"""Tests for quizai.history."""

from __future__ import annotations


def test_add_and_list():
    from quizai.history import add_entry, init_db, list_entries

    init_db()
    e = add_entry(
        source="manual",
        question="2+2?",
        answer="4",
        explanation="basic arithmetic",
        model="gemini:gemini-2.5-flash",
    )
    assert e.id > 0
    assert e.question == "2+2?"

    rows = list_entries()
    assert len(rows) == 1
    assert rows[0].answer == "4"


def test_list_returns_newest_first():
    from quizai.history import add_entry, init_db, list_entries

    init_db()
    add_entry(source="manual", question="first", answer="a1", explanation="", model="m")
    add_entry(source="manual", question="second", answer="a2", explanation="", model="m")
    rows = list_entries()
    assert rows[0].question == "second"
    assert rows[1].question == "first"


def test_search_filters():
    from quizai.history import add_entry, init_db, list_entries

    init_db()
    add_entry(
        source="manual",
        question="What is mitosis?",
        answer="cell division",
        explanation="",
        model="m",
    )
    add_entry(
        source="manual",
        question="What is photosynthesis?",
        answer="plant energy",
        explanation="",
        model="m",
    )

    rows = list_entries(search="mitosis")
    assert len(rows) == 1
    assert "mitosis" in rows[0].question.lower()

    rows = list_entries(search="cell")
    # Matches the answer field
    assert len(rows) == 1


def test_delete():
    from quizai.history import add_entry, delete_entry, init_db, list_entries

    init_db()
    e = add_entry(source="manual", question="q", answer="a", explanation="", model="m")
    assert len(list_entries()) == 1
    delete_entry(e.id)
    assert len(list_entries()) == 0


def test_clear_all():
    from quizai.history import add_entry, clear_all, init_db, list_entries

    init_db()
    for i in range(5):
        add_entry(source="manual", question=f"q{i}", answer=f"a{i}", explanation="", model="m")
    assert len(list_entries()) == 5
    clear_all()
    assert len(list_entries()) == 0


def test_get_entry():
    from quizai.history import add_entry, get_entry, init_db

    init_db()
    e = add_entry(source="manual", question="q", answer="a", explanation="x", model="m")
    fetched = get_entry(e.id)
    assert fetched is not None
    assert fetched.answer == "a"
    assert get_entry(99999) is None


def test_list_recovers_when_table_missing(tmp_path, monkeypatch):
    """If list_entries runs before init_db, it should recover gracefully
    rather than crash — this is the robustness fix from the earlier session."""
    from quizai import history

    # Wipe the DB file if it exists from another test, force re-create.
    if history.DB_PATH.exists():
        history.DB_PATH.unlink()

    # Should not raise even though we never called init_db.
    rows = history.list_entries()
    assert rows == []
