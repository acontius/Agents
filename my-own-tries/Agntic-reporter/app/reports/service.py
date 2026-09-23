"""Report creation, generation, and persistence service."""

from __future__ import annotations

import logging
from datetime import date, time
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Report
from app.reports.parser import ParsedReport, parse_report

logger = logging.getLogger(__name__)


def _get_llm_client() -> OpenAI:
    settings = get_settings()
    settings.validate_for_llm()
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def generate_professional_report(parsed: ParsedReport, *, client: OpenAI | None = None) -> str:
    """Ask the LLM to produce a concise professional daily report.

    Never invents details that are not in the raw text.
    """
    settings = get_settings()
    llm = client or _get_llm_client()

    hours = parsed.working_hours_str()
    activities_block = "\n".join(f"- {a}" for a in parsed.activities) or "(none extracted)"
    urls_block = "\n".join(parsed.urls) or "(none)"

    system = (
        "You are a professional report writer for a software team. "
        "Given a raw daily report, produce a concise, well-structured professional "
        "summary in the SAME language as the input (Persian or English). "
        "Rules:\n"
        "- Do NOT invent activities, times, or details that are not present.\n"
        "- If a field is missing, omit it or say it was not provided.\n"
        "- Keep the summary short (3-6 bullet points max for activities).\n"
        "- Preserve any URLs that appear.\n"
        "- Structure:\n"
        "  گزارش روزانه / Daily Report\n"
        "  ⏰ ساعت کاری: ...\n"
        "  فعالیت‌ها: / Activities:\n"
        "  • ...\n"
        "  خلاصه: / Summary:\n"
        "  ..."
    )
    user = (
        f"Person: {parsed.person}\n"
        f"Date: {parsed.report_date.isoformat()}\n"
        f"Working hours (extracted): {hours}\n"
        f"Activities (extracted):\n{activities_block}\n"
        f"URLs:\n{urls_block}\n\n"
        f"Raw report:\n{parsed.raw_text}"
    )

    try:
        response = llm.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as exc:
        logger.error("LLM report generation failed: %s", exc)
        return _fallback_report(parsed)


def _fallback_report(parsed: ParsedReport) -> str:
    lines = [
        "گزارش روزانه",
        "",
        f"⏰ ساعت کاری: {parsed.working_hours_str()}",
        "",
        "فعالیت‌ها:",
    ]
    if parsed.activities:
        for a in parsed.activities:
            lines.append(f"• {a}")
    else:
        lines.append("• (جزئیات در متن خام)")
    lines.extend(["", "خلاصه:", parsed.raw_text[:400]])
    if parsed.urls:
        lines.append("")
        lines.append("لینک‌ها:")
        for u in parsed.urls:
            lines.append(f"• {u}")
    return "\n".join(lines)


def create_report(
    session: Session,
    *,
    person: str,
    raw_text: str,
    report_date: date | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
    generate: bool = True,
    client: OpenAI | None = None,
) -> Report:
    """Parse, optionally generate, and persist a daily report."""
    logger.info("report received for person=%s", person)
    parsed = parse_report(
        raw_text=raw_text,
        person=person,
        report_date=report_date,
        start_time=start_time,
        end_time=end_time,
    )

    generated: Optional[str] = None
    if generate:
        try:
            generated = generate_professional_report(parsed, client=client)
        except Exception as exc:
            logger.warning("generation skipped due to error: %s", exc)
            generated = _fallback_report(parsed)

    report = Report(
        person=parsed.person,
        report_date=parsed.report_date,
        start_time=parsed.start_time,
        end_time=parsed.end_time,
        raw_text=parsed.raw_text,
        generated_report=generated,
    )
    session.add(report)
    session.flush()
    logger.info("report saved id=%s person=%s date=%s", report.id, report.person, report.report_date)
    return report
