"""Report creation, generation, and persistence service."""

from __future__ import annotations

import logging
from datetime import date, time
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Report
from app.reports.formatting import _actions_from_report, format_daily_markdown
from app.reports.parser import ParsedReport, parse_report

logger = logging.getLogger(__name__)


def _get_llm_client() -> OpenAI:
    settings = get_settings()
    settings.validate_for_llm()
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def _extract_english_actions(parsed: ParsedReport, client: OpenAI | None) -> list[str]:
    settings = get_settings()
    activities_block = "\n".join(f"- {a}" for a in parsed.activities) or "(none)"
    system = (
        "You extract daily work activities from an employee's raw report. "
        "Output ONLY a bullet list in English (3-8 items max). "
        "Each line must start with '- '. "
        "Do NOT invent work that is not present. "
        "Translate Persian content into clear professional English. "
        "Do not include times, headers, or commentary — only action bullets."
    )
    user = (
        f"Person: {parsed.person}\n"
        f"Date: {parsed.report_date.isoformat()}\n"
        f"Extracted bullets:\n{activities_block}\n\n"
        f"Raw report:\n{parsed.raw_text}"
    )
    try:
        llm = client or _get_llm_client()
        response = llm.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        content = (response.choices[0].message.content or "").strip()
        actions = _actions_from_report(content, None)
        if actions:
            return actions
    except Exception as exc:
        logger.warning("English action extraction failed: %s", exc)

    if parsed.activities:
        return list(parsed.activities)[:8]
    snippet = (parsed.raw_text or "").strip().splitlines()
    return [s.strip() for s in snippet if s.strip() and not s.strip().startswith("ورود")][:5]


def generate_professional_report(
    parsed: ParsedReport, *, client: OpenAI | None = None
) -> str:
    actions = _extract_english_actions(parsed, client)
    return format_daily_markdown(
        person=parsed.person,
        report_date=parsed.report_date,
        start_time=parsed.start_time,
        end_time=parsed.end_time,
        actions=actions,
    )


def _fallback_report(parsed: ParsedReport) -> str:
    actions = list(parsed.activities) if parsed.activities else ["See raw report notes"]
    return format_daily_markdown(
        person=parsed.person,
        report_date=parsed.report_date,
        start_time=parsed.start_time,
        end_time=parsed.end_time,
        actions=actions,
    )


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
    logger.info(
        "report saved id=%s person=%s date=%s",
        report.id,
        report.person,
        report.report_date,
    )
    return report
