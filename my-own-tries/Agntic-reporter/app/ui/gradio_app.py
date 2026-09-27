"""Gradio UI: Chat, Add Report, History, Reports (Daily/Weekly/Monthly)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

import gradio as gr

from app.agent.agent import generate_weekly_report, run_agent
from app.database import get_db
from app.jalali import (
    format_jalali,
    format_time_display,
    make_choice,
    parse_choice_key,
    work_week_for,
    jalali_month_for,
    jalali_to_gregorian,
)
from app.reports.aggregation import (
    generate_daily_markdown_for_date,
    generate_monthly_markdown,
    generate_weekly_markdown,
    list_available_dates,
    list_available_months,
    list_available_weeks,
)
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


def _normalize_chat_history(history: list | None) -> list[dict[str, str]]:
    """Convert Gradio history to messages format ({role, content})."""
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
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


# ---------- Chat (messages format — do not regress) ----------

def chat_respond(message: str, history: list) -> tuple[str, list[dict[str, str]]]:
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


# ---------- Add Report ----------

def _recent_date_choices(n: int = 45) -> list[str]:
    """Jalali labels for the last n calendar days (including today)."""
    today = date.today()
    choices = []
    for i in range(n):
        d = today - timedelta(days=i)
        choices.append(make_choice(format_jalali(d), d.isoformat()))
    return choices


def submit_report(
    person: str,
    date_choice: str,
    start_str: str,
    end_str: str,
    raw_text: str,
) -> tuple[str, str]:
    """Parse, generate English daily Markdown, save. No DB id in status."""
    try:
        if not person or not person.strip():
            return "❌ Person is required.", ""
        if not raw_text or not raw_text.strip():
            return "❌ Report text is required.", ""

        key = parse_choice_key(date_choice)
        report_date = date.fromisoformat(key) if key else date.today()
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
            report_person = report.person
            report_gdate = report.report_date
            report_start = report.start_time
            report_end = report.end_time
            generated = report.generated_report or ""

        status = (
            f"✅ Report saved\n"
            f"Person: {report_person}\n"
            f"Date: {format_jalali(report_gdate)}\n"
            f"Hours: {format_time_display(report_start)} – {format_time_display(report_end)}"
        )
        return status, generated
    except ValueError as exc:
        return f"❌ Invalid input: {exc}", ""
    except Exception as exc:
        logger.exception("submit_report failed")
        return f"❌ Error: {type(exc).__name__}: {exc}", ""


# ---------- History (serialize inside session — do not regress) ----------

def load_history(person: str, date_from_choice: str, date_to_choice: str) -> str:
    try:
        key_from = parse_choice_key(date_from_choice)
        key_to = parse_choice_key(date_to_choice)
        date_from = date.fromisoformat(key_from) if key_from else None
        date_to = date.fromisoformat(key_to) if key_to else None

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
            rd = d["report_date"]
            g = date.fromisoformat(rd) if isinstance(rd, str) else rd
            jlabel = format_jalali(g) if g else rd
            st = d.get("start_time") or "—"
            et = d.get("end_time") or "—"
            blocks.append(
                f"{'=' * 50}\n"
                f"{d['person']} | {jlabel}\n"
                f"Hours: {st} – {et}\n\n"
                f"--- Generated ---\n{d['generated_report'] or '(none)'}\n\n"
                f"--- Raw ---\n{d['raw_text']}\n"
            )
        return "\n".join(blocks)
    except Exception as exc:
        logger.exception("load_history failed")
        return f"Error: {type(exc).__name__}: {exc}"


# ---------- Period dropdown helpers ----------

def refresh_period_choices(report_type: str) -> gr.Dropdown:
    """Rebuild period dropdown for Daily / Weekly / Monthly."""
    report_type = (report_type or "Daily").strip()
    choices: list[str] = []
    try:
        with get_db() as session:
            if report_type == "Daily":
                dates = list_available_dates(session)
                if not dates:
                    dates = [date.today() - timedelta(days=i) for i in range(14)]
                choices = [make_choice(format_jalali(d), d.isoformat()) for d in dates]
                label = "Select Date"
            elif report_type == "Weekly":
                weeks = list_available_weeks(session)
                if not weeks:
                    weeks = [work_week_for(date.today())]
                choices = [
                    make_choice(w.label(), w.start.isoformat()) for w in weeks
                ]
                label = "Select Week"
            else:
                months = list_available_months(session)
                if not months:
                    months = [jalali_month_for(date.today())]
                choices = [
                    make_choice(m.label(), f"{m.year}-{m.month:02d}") for m in months
                ]
                label = "Select Month"
    except Exception as exc:
        logger.warning("period choices failed: %s", exc)
        choices = [make_choice(format_jalali(date.today()), date.today().isoformat())]
        label = "Select Period"

    return gr.Dropdown(choices=choices, value=choices[0] if choices else None, label=label)


def generate_period_report(
    report_type: str,
    period_choice: str,
    person: str,
) -> str:
    """Generate Daily / Weekly / Monthly English Markdown for the selected period."""
    try:
        report_type = (report_type or "Daily").strip()
        key = parse_choice_key(period_choice)
        person_filter = person.strip() or None

        with get_db() as session:
            if report_type == "Daily":
                g = date.fromisoformat(key) if key else date.today()
                return generate_daily_markdown_for_date(
                    session, report_date=g, person=person_filter
                )
            if report_type == "Weekly":
                g = date.fromisoformat(key) if key else date.today()
                week = work_week_for(g)
                return generate_weekly_markdown(
                    session, week=week, person=person_filter
                )
            # Monthly — key is "jy-jm"
            if key and "-" in key:
                parts = key.split("-")
                jy, jm = int(parts[0]), int(parts[1])
                from app.jalali import JalaliMonth

                month = JalaliMonth(year=jy, month=jm)
            else:
                month = jalali_month_for(date.today())
            return generate_monthly_markdown(
                session, month=month, person=person_filter
            )
    except Exception as exc:
        logger.exception("generate_period_report failed")
        return f"Error: {type(exc).__name__}: {exc}"


# ---------- Build UI ----------

def _make_chatbot() -> gr.Chatbot:
    kwargs: dict[str, Any] = {"label": "Agent", "height": 420}
    try:
        return gr.Chatbot(type="messages", **kwargs)
    except TypeError:
        return gr.Chatbot(**kwargs)


def build_ui() -> gr.Blocks:
    date_choices = _recent_date_choices()
    empty_period = date_choices[:14] if date_choices else []

    with gr.Blocks(title="Team Reporting Agent") as demo:
        gr.Markdown(
            "# Team Reporting Agent\n"
            "Daily / Weekly / Monthly reports · Jalali dates · English Markdown · Agentic retrieval"
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
                    ["Show everything related to Agentic Vulnerability Detection"],
                ],
                inputs=chat_input,
            )

        with gr.Tab("Add Report"):
            person_in = gr.Textbox(label="Person", placeholder="Amin")
            date_in = gr.Dropdown(
                label="Select Date",
                choices=date_choices,
                value=date_choices[0] if date_choices else None,
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
                    "- OpenRouter را بررسی کردم"
                ),
            )
            submit_btn = gr.Button("Generate & Save Report", variant="primary")
            status_out = gr.Textbox(label="Status", lines=4)
            generated_out = gr.Textbox(label="Generated Report (English Markdown)", lines=14)
            submit_btn.click(
                submit_report,
                inputs=[person_in, date_in, start_in, end_in, raw_in],
                outputs=[status_out, generated_out],
            )

        with gr.Tab("History"):
            hist_person = gr.Textbox(label="Person filter", placeholder="Amin")
            with gr.Row():
                hist_from = gr.Dropdown(
                    label="From",
                    choices=["(any)||"] + date_choices,
                    value="(any)||",
                )
                hist_to = gr.Dropdown(
                    label="To",
                    choices=["(any)||"] + date_choices,
                    value="(any)||",
                )
            hist_btn = gr.Button("Load Reports")
            hist_out = gr.Textbox(label="Reports", lines=20)
            hist_btn.click(
                load_history,
                inputs=[hist_person, hist_from, hist_to],
                outputs=hist_out,
            )

        with gr.Tab("Reports"):
            gr.Markdown(
                "Generate **English Markdown** daily / weekly / monthly reports. "
                "Select the period from the list — no manual date typing."
            )
            report_type = gr.Radio(
                choices=["Daily", "Weekly", "Monthly"],
                value="Weekly",
                label="Report Type",
            )
            period_dd = gr.Dropdown(
                label="Select Week",
                choices=empty_period,
                value=empty_period[0] if empty_period else None,
            )
            report_person = gr.Textbox(
                label="Person (optional — leave empty for whole team)",
                placeholder="Amin",
            )
            gen_btn = gr.Button("Generate Report", variant="primary")
            report_out = gr.Textbox(label="Markdown Report", lines=28)

            report_type.change(
                refresh_period_choices,
                inputs=[report_type],
                outputs=[period_dd],
            )
            demo.load(refresh_period_choices, inputs=[report_type], outputs=[period_dd])
            gen_btn.click(
                generate_period_report,
                inputs=[report_type, period_dd, report_person],
                outputs=[report_out],
            )

    return demo
