"""Regression tests for Gradio UI session/history bugs."""

from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock, patch

from app.models import Report
from app.ui.gradio_app import (
    _normalize_chat_history,
    chat_respond,
    load_history,
)


# ---------- Bug 1: Chatbot messages format ----------

def test_normalize_chat_history_from_pairs():
    history = [["hello", "hi there"], ["second", "reply"]]
    msgs = _normalize_chat_history(history)
    assert all(isinstance(m, dict) for m in msgs)
    assert all("role" in m and "content" in m for m in msgs)
    assert msgs[0] == {"role": "user", "content": "hello"}
    assert msgs[1] == {"role": "assistant", "content": "hi there"}
    assert len(msgs) == 4


def test_normalize_chat_history_from_messages():
    history = [
        {"role": "user", "content": "Amin چه کرد؟"},
        {"role": "assistant", "content": "کار روی Agentic"},
    ]
    msgs = _normalize_chat_history(history)
    assert msgs == history


def test_normalize_chat_history_empty():
    assert _normalize_chat_history(None) == []
    assert _normalize_chat_history([]) == []


def test_chat_respond_returns_messages_format():
    """chat_respond must return list of {role, content} dicts, not tuples."""
    mock_answer = "Amin worked on Tool Calling."

    with patch("app.ui.gradio_app.get_db") as mock_get_db, patch(
        "app.ui.gradio_app.run_agent", return_value=mock_answer
    ) as mock_agent:
        session = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        cleared, history = chat_respond("What did Amin do?", [])

    assert cleared == ""
    assert isinstance(history, list)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "What did Amin do?"}
    assert history[1] == {"role": "assistant", "content": mock_answer}
    mock_agent.assert_called_once()
    assert mock_agent.call_args[0][0] == "What did Amin do?"


def test_chat_respond_preserves_prior_history():
    prior = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
    ]
    with patch("app.ui.gradio_app.get_db") as mock_get_db, patch(
        "app.ui.gradio_app.run_agent", return_value="reply2"
    ) as mock_agent:
        session = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _, history = chat_respond("second", prior)

    assert len(history) == 4
    assert history[0]["content"] == "first"
    assert history[2] == {"role": "user", "content": "second"}
    assert history[3] == {"role": "assistant", "content": "reply2"}
    openai_hist = mock_agent.call_args[1].get("history") or mock_agent.call_args.kwargs.get(
        "history"
    )
    assert openai_hist is not None
    assert any(t.get("content") == "first" for t in openai_hist)


def test_chat_respond_persian_message():
    with patch("app.ui.gradio_app.get_db") as mock_get_db, patch(
        "app.ui.gradio_app.run_agent", return_value="پاسخ"
    ):
        session = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        _, history = chat_respond("امین هفته گذشته چه کرد؟", [])

    assert history[0]["role"] == "user"
    assert "امین" in history[0]["content"]
    assert history[1]["role"] == "assistant"


# ---------- Bug 2: DetachedInstanceError / session lifecycle ----------

def test_load_history_serializes_inside_session(db_session, sample_reports):
    """load_history must not access ORM objects after the session closes."""
    from contextlib import contextmanager

    @contextmanager
    def fake_get_db():
        yield db_session

    with patch("app.ui.gradio_app.get_db", fake_get_db):
        text = load_history("Amin", "2026-09-01", "2026-09-30")

    assert "DetachedInstanceError" not in text
    assert "Error:" not in text or "No reports" in text
    assert "Amin" in text
    assert "2026-09-20" in text or "2026-09-21" in text


def test_load_history_empty_result(db_session):
    from contextlib import contextmanager

    @contextmanager
    def fake_get_db():
        yield db_session

    with patch("app.ui.gradio_app.get_db", fake_get_db):
        text = load_history("NobodyExistsXYZ", "", "")

    assert text == "No reports found."


def test_to_dict_usable_after_session_close(db_session, sample_reports):
    """Prove the preferred pattern: to_dict inside session, use dicts after."""
    data = [r.to_dict() for r in sample_reports]
    db_session.close()
    assert data[0]["person"] == "Amin"
    assert "raw_text" in data[0]
    assert data[0]["id"] is not None
