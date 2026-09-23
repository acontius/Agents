"""Core agentic loop with explicit tool calling.

Flow (educational, intentionally explicit):

  User message
       ↓
  LLM (with tool schemas)
       ↓
  tool_calls? ──yes──→ Python executes tool(s)
       ↓                      ↓
      no                 tool results appended
       ↓                      ↓
  Final answer  ←──────── LLM again
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agent.prompts import SYSTEM_PROMPT, WEEKLY_REPORT_PROMPT
from app.agent.tools import TOOL_SCHEMAS, execute_tool
from app.config import get_settings
from app.reports.retrieval import format_reports_for_llm, get_person_activity, get_reports_by_date_range

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


def _client() -> OpenAI:
    settings = get_settings()
    settings.validate_for_llm()
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def run_agent(
    user_message: str,
    session: Session,
    *,
    history: Optional[list[dict[str, Any]]] = None,
    client: OpenAI | None = None,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> str:
    """Run the tool-calling agent loop and return the final natural-language answer.

    `history` is optional prior chat turns (list of {role, content}).
    """
    settings = get_settings()
    llm = client or _client()
    logger.info("agent started")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if history:
        for turn in history:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    for round_idx in range(max_rounds):
        try:
            response = llm.chat.completions.create(
                model=settings.openrouter_model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=1500,
            )
        except Exception as exc:
            logger.error("OpenRouter API error: %s", exc)
            return (
                "Sorry, I could not reach the language model. "
                f"Error: {type(exc).__name__}. "
                "Check OPENROUTER_API_KEY and network connectivity."
            )

        choice = response.choices[0]
        msg = choice.message

        assistant_entry: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
        }
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            answer = (msg.content or "").strip()
            logger.info("agent completed (round %d, no more tools)", round_idx + 1)
            return answer or "(empty response from model)"

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
                tool_result = f"Error: invalid JSON arguments: {tc.function.arguments}"
            else:
                tool_result = execute_tool(name, args, session)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                }
            )

    logger.warning("agent hit max tool rounds (%d)", max_rounds)
    return (
        "I reached the maximum number of tool-call rounds without a final answer. "
        "Please rephrase your question or narrow the date range."
    )


def generate_weekly_report(
    session: Session,
    person: str,
    *,
    days: int = 7,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client: OpenAI | None = None,
) -> str:
    """Generate a structured weekly report for a person.

    Uses retrieval + a focused LLM call (not the full agent loop) so the
    output format stays consistent.
    """
    from datetime import date, timedelta

    settings = get_settings()
    llm = client or _client()

    if date_from and date_to:
        from app.agent.tools import _parse_date

        reports = get_reports_by_date_range(
            session,
            date_from=_parse_date(date_from),  # type: ignore
            date_to=_parse_date(date_to),  # type: ignore
            person=person,
        )
        period = f"{date_from} → {date_to}"
    else:
        reports = get_person_activity(session, person, days=days)
        today = date.today()
        period = f"{(today - timedelta(days=days - 1)).isoformat()} → {today.isoformat()}"

    if not reports:
        return (
            f"Weekly Report\n\nPeriod: {period}\nPerson: {person}\n\n"
            "No reports found for this period."
        )

    evidence = "\n".join(f"• {r.short_label()}" for r in reports)
    context = format_reports_for_llm(reports)

    user_content = (
        f"Person: {person}\nPeriod: {period}\n\n"
        f"Reports:\n{context}\n\n"
        f"Evidence list:\n{evidence}"
    )

    try:
        response = llm.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": WEEKLY_REPORT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("weekly report LLM failed: %s", exc)
        lines = [
            "Weekly Report",
            "",
            f"Period: {period}",
            f"Person: {person}",
            "",
            "Activities:",
        ]
        for r in reports:
            snippet = (r.generated_report or r.raw_text or "")[:200]
            lines.append(f"• {r.report_date}: {snippet}")
        lines.extend(["", "Evidence:", evidence])
        lines.append("")
        lines.append("Progress: Not enough data to estimate progress (LLM unavailable).")
        return "\n".join(lines)
