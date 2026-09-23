"""Tests for agent tool dispatch and the tool-calling loop (LLM mocked)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

from app.agent.tools import (
    TOOL_DISPATCH,
    execute_tool,
    tool_get_person_activity,
    tool_search_reports,
)
from app.agent.agent import run_agent


def test_tool_search_reports(db_session, sample_reports):
    result = tool_search_reports(db_session, person="Amin")
    assert "Amin" in result
    assert "Report id=" in result


def test_tool_get_person_activity(db_session, sample_reports):
    result = tool_search_reports(
        db_session,
        person="Amin",
        date_from="2026-09-01",
        date_to="2026-09-30",
    )
    assert "Amin" in result


def test_execute_unknown_tool(db_session):
    out = execute_tool("nonexistent_tool", {}, db_session)
    assert "unknown tool" in out.lower()


def test_execute_fetch_url_no_session():
    out = execute_tool("fetch_url", {"url": "not-a-url"}, session=None)
    assert "Error" in out or "invalid" in out.lower()


def test_agent_loop_no_tools(db_session, sample_reports):
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "Amin worked on Agentic Vulnerability Detection."
    choice.message.tool_calls = None
    response = MagicMock()
    response.choices = [choice]
    client.chat.completions.create.return_value = response

    answer = run_agent(
        "What did Amin do?",
        db_session,
        client=client,
        max_rounds=3,
    )
    assert "Agentic" in answer
    client.chat.completions.create.assert_called()


def test_agent_loop_with_tool_call(db_session, sample_reports):
    client = MagicMock()

    tc = MagicMock()
    tc.id = "call_1"
    tc.function.name = "search_reports"
    tc.function.arguments = json.dumps({"person": "Amin", "text_query": "OpenRouter"})

    choice1 = MagicMock()
    choice1.message.content = ""
    choice1.message.tool_calls = [tc]
    resp1 = MagicMock()
    resp1.choices = [choice1]

    choice2 = MagicMock()
    choice2.message.content = (
        "Amin reviewed OpenRouter on 2026-09-21.\n\n"
        "Sources:\n• 2026-09-21 — Amin (id=2)"
    )
    choice2.message.tool_calls = None
    resp2 = MagicMock()
    resp2.choices = [choice2]

    client.chat.completions.create.side_effect = [resp1, resp2]

    answer = run_agent(
        "What did Amin do with OpenRouter?",
        db_session,
        client=client,
        max_rounds=4,
    )
    assert "OpenRouter" in answer
    assert client.chat.completions.create.call_count == 2


def test_tool_schemas_present():
    from app.agent.tools import TOOL_SCHEMAS

    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert "search_reports" in names
    assert "get_person_activity" in names
    assert "fetch_url" in names
