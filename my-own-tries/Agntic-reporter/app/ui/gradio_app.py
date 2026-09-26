"""Gradio UI: Chat, Add Report, History, Weekly Report."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any, Optional

import gradio as gr

from app.agent.agent import generate_weekly_report, run_agent
from app.database import get_db
from app.reports.retrieval import search_reports
from app.reports.service import create_report

logger = logging.getLogger(__name__)


def _parse_optional_time(value: str | None) -> Optional[time]:
    if not value or not str(value).strip():
        return None
    value = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%H.%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time: {value!r}. Use HH:MM")


def _parse_optional_date(value: str | None) -> Optional[date]:
    if not value or not str(value).strip():
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {value!r}. Use YYYY-MM-DD")


def _normalize_chat_history(history: list | None) -> list[dict[str, str]]:
    """Convert Gradio history (tuples or message dicts) to messages format.

    Output is always a list of {"role": "...", "content": "..."} dicts,
    which is what Gradio Chatbot(type=\"messages\") expects.
    """
    messages: list[dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict) and item.get("role") is not None:
            content = item.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        parts.append(str(block["text"]))
                    else:
                        parts.append(str(block))
                content = "".join(parts)
            messages.append({"role": str(item["role"]), "content": str(content or "")})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            if item[0]:
                messages.append({"role": "user", "content": str(item[0])})
            if item[1]:
                messages.append({"role": "assistant", "content": str(item[1])})
    return messages


def _history_to_openai(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Map Gradio messages to OpenAI-style history for run_agent."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


def chat_respond(message: str, history: list) -> tuple[str, list[dict[str, str]]]:
    """Gradio chatbot callback — returns messages-format history.

    Gradio Chatbot(type=\"messages\") requires each entry to be a dict with
    'role' and 'content' keys. Tuple pairs [[user, assistant], ...] cause:
    \"Data incompatible with messages format\".
    """
    messages = _normalize_chat_history(history)

    if not message or not message.strip():
        return "", messages

    openai_history = _history_to_openai(messages)

    try:
        with get_db() as session:
            answer = run_agent(message.strip(), session, history=openai_history)
    except Exception as exc:
        logger.exception("chat error")
        answer = f"Error: {type(exc).__name__}: {exc}"

    messages = messages + [
        {"role": "user", "content": message.strip()},
        {"role": "assistant", "content": answer},
    ]
    return "", messages


def submit_report(
    person: str,
    report_date_str: str,
    start_str: str,
    end_str: str,
    raw_text: str,
) -> tuple[str, str]:
    """Parse, generate, save. Returns (status, generated_report)."""
    try:
        if not person or not person.strip():
            return "❌ Person is required.", ""
        if not raw_text or not raw_text.strip():
            return "❌ Report text is required.", ""

        report_date = _parse_optional_date(report_date_str) or date.today()
        start_time = _parse_optional_time(start_str)
        end_time = _parse_optional_time(end_str)

        with get_db() as session:
            report = create_report(
                session,
                person=person.strip(),
                raw_text=raw_text.strip(),
                report_date=report_date,
                start_time=start_time,
                end_time=end_time,
                generate=True,
            )
            report_id = report.id
            report_person = report.person
            report_date_iso = report.report_date.isoformat()
            report_start = report.start_time
            report_end = report.end_time
            generated = report.generated_report or ""

        status = (
            f"✅ Report saved (id={report_id})\n"
            f"Person: {report_person}\n"
            f"Date: {report_date_iso}\n"
            f"Hours: {report_start} – {report_end}"
        )
        return status, generated
    except ValueError as exc:
        return f"❌ Invalid input: {exc}", ""
    except Exception as exc:
        logger.exception("submit_report failed")
        return f"❌ Error: {type(exc).__name__}: {exc}", ""


def load_history(
    person: str,
    date_from_str: str,
    date_to_str: str,
) -> str:
    """Load reports and format them as plain text.

    ORM objects are converted to dicts *inside* the active session so that
    no attribute access happens after the session is closed
    (which would raise DetachedInstanceError).
    """
    try:
        date_from = _parse_optional_date(date_from_str)
        date_to = _parse_optional_date(date_to_str)

        with get_db() as session:
            reports = search_reports(
                session,
                person=person.strip() or None,
                date_from=date_from,
                date_to=date_to,
                limit=50,
            )
            report_data = [r.to_dict() for r in reports]

        if not report_data:
            return "No reports found."

        blocks: list[str] = []
        for d in report_data:
            blocks.append(
                f"{'=' * 50}\n"
                f"ID: {d['id']} | {d['person']} | {d['report_date']}\n"
                f"Hours: {d['start_time']} – {d['end_time']}\n\n"
                f"--- Generated ---\n{d['generated_report'] or '(none)'}\n\n"
                f"--- Raw ---\n{d['raw_text']}\n"
            )
        return "\n".join(blocks)
    except Exception as exc:
        logger.exception("load_history failed")
        return f"Error: {type(exc).__name__}: {exc}"


def weekly_report_ui(person: str, days: int) -> str:
    if not person or not person.strip():
        return "Person is required."
    try:
        days = int(days) if days else 7
        with get_db() as session:
            return generate_weekly_report(session, person.strip(), days=days)
    except Exception as exc:
        logger.exception("weekly_report_ui failed")
        return f"Error: {type(exc).__name__}: {exc}"


def _make_chatbot() -> gr.Chatbot:
    """Create Chatbot in messages mode (required by current Gradio).

    Gradio 4/5 accept type=\"messages\". Gradio 6 made messages the only
    format and dropped the type= keyword — fall back gracefully.
    """
    kwargs: dict[str, Any] = {"label": "Agent", "height": 420}
    try:
        return gr.Chatbot(type="messages", **kwargs)
    except TypeError:
        return gr.Chatbot(**kwargs)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Team Reporting Agent") as demo:
        gr.Markdown(
            "# Team Reporting Agent\n"
            "Daily reports knowledge base with an Agentic AI assistant."
        )

        with gr.Tab("Chat"):
            chatbot = _make_chatbot()
            with gr.Row():
                chat_input = gr.Textbox(
                    placeholder=(
                        "Amin هفته گذشته چه کارهایی کرده؟ / "
                        "What did the team work on this week?"
                    ),
                    scale=5,
                    show_label=False,
                )
                chat_btn = gr.Button("Send", variant="primary", scale=1)
            chat_btn.click(
                chat_respond,
                inputs=[chat_input, chatbot],
                outputs=[chat_input, chatbot],
            )
            chat_input.submit(
                chat_respond,
                inputs=[chat_input, chatbot],
                outputs=[chat_input, chatbot],
            )
            gr.Examples(
                examples=[
                    ["Amin هفته گذشته چه کارهایی کرده؟"],
                    ["What did the team work on this week?"],
                    ["Show me everything related to Agentic Vulnerability Detection"],
                    ["What evidence supports this summary?"],
                ],
                inputs=chat_input,
            )

        with gr.Tab("Add Report"):
            person_in = gr.Textbox(label="Person", placeholder="Amin")
            date_in = gr.Textbox(
                label="Date (YYYY-MM-DD)",
                placeholder=date.today().isoformat(),
            )
            with gr.Row():
                start_in = gr.Textbox(label="Start time (HH:MM)", placeholder="08:30")
                end_in = gr.Textbox(label="End time (HH:MM)", placeholder="17:15")
            raw_in = gr.Textbox(
                label="Raw Report",
                lines=10,
                placeholder=(
                    "ورود: 08:30\nخروج: 17:15\n\nکارها:\n"
                    "- روی Agentic Vulnerability Detection کار کردم\n"
                    "- Tool Calling را پیاده‌سازی کردم\n"
                    "- OpenRouter را بررسی کردم\n"
                    "https://example.com/article"
                ),
            )
            submit_btn = gr.Button("Generate & Save Report", variant="primary")
            status_out = gr.Textbox(label="Status", lines=4)
            generated_out = gr.Textbox(label="Generated Report", lines=12)
            submit_btn.click(
                submit_report,
                inputs=[person_in, date_in, start_in, end_in, raw_in],
                outputs=[status_out, generated_out],
            )

        with gr.Tab("History"):
            with gr.Row():
                hist_person = gr.Textbox(label="Person filter", placeholder="Amin")
                hist_from = gr.Textbox(label="From (YYYY-MM-DD)")
                hist_to = gr.Textbox(label="To (YYYY-MM-DD)")
            hist_btn = gr.Button("Load Reports")
            hist_out = gr.Textbox(label="Reports", lines=20)
            hist_btn.click(
                load_history,
                inputs=[hist_person, hist_from, hist_to],
                outputs=hist_out,
            )

        with gr.Tab("Weekly Report"):
            wk_person = gr.Textbox(label="Person", placeholder="Amin")
            wk_days = gr.Number(label="Last N days", value=7, precision=0)
            wk_btn = gr.Button("Generate Weekly Report", variant="primary")
            wk_out = gr.Textbox(label="Weekly Report", lines=20)
            wk_btn.click(weekly_report_ui, inputs=[wk_person, wk_days], outputs=wk_out)

    return demo
