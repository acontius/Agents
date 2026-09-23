"""Gradio UI: Chat, Add Report, History, Weekly Report."""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any, Optional

import gradio as gr

from app.agent.agent import generate_weekly_report, run_agent
from app.database import get_db
from app.models import Report
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


def chat_respond(message: str, history: list) -> tuple[str, list]:
    """Gradio chatbot callback. history is list of [user, assistant] pairs."""
    if not message or not message.strip():
        return "", history

    openai_history: list[dict[str, Any]] = []
    for pair in history:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            if pair[0]:
                openai_history.append({"role": "user", "content": pair[0]})
            if pair[1]:
                openai_history.append({"role": "assistant", "content": pair[1]})

    try:
        with get_db() as session:
            answer = run_agent(message.strip(), session, history=openai_history)
    except Exception as exc:
        logger.exception("chat error")
        answer = f"Error: {type(exc).__name__}: {exc}"

    history = history + [[message, answer]]
    return "", history


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
            generated = report.generated_report or ""
            status = (
                f"✅ Report saved (id={report.id})\n"
                f"Person: {report.person}\n"
                f"Date: {report.report_date.isoformat()}\n"
                f"Hours: {report.start_time} – {report.end_time}"
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
        if not reports:
            return "No reports found."
        blocks: list[str] = []
        for r in reports:
            blocks.append(
                f"{'='*50}\n"
                f"ID: {r.id} | {r.person} | {r.report_date.isoformat()}\n"
                f"Hours: {r.start_time} – {r.end_time}\n\n"
                f"--- Generated ---\n{r.generated_report or '(none)'}\n\n"
                f"--- Raw ---\n{r.raw_text}\n"
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


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Team Reporting Agent") as demo:
        gr.Markdown(
            "# Team Reporting Agent\n"
            "Daily reports knowledge base with an Agentic AI assistant."
        )

        with gr.Tab("Chat"):
            chatbot = gr.Chatbot(label="Agent", height=420)
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
