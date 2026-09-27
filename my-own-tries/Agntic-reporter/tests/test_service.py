"""Tests for report creation and generation (LLM mocked)."""

from datetime import date, time

from app.reports.service import create_report, generate_professional_report
from app.reports.parser import parse_report


def test_create_report_persists(db_session, mock_llm_client):
    report = create_report(
        db_session,
        person="Amin",
        raw_text="ورود: 08:30\nخروج: 17:15\n- کار روی Agentic",
        report_date=date(2026, 9, 22),
        generate=True,
        client=mock_llm_client,
    )
    db_session.commit()
    assert report.id is not None
    assert report.person == "Amin"
    assert report.raw_text.startswith("ورود")
    assert report.generated_report is not None
    assert report.generated_report.startswith("#daily #")
    assert "id=" not in report.generated_report.lower()


def test_create_report_preserves_raw_without_generation(db_session):
    report = create_report(
        db_session,
        person="Sara",
        raw_text="simple note",
        report_date=date(2026, 9, 22),
        generate=False,
    )
    db_session.commit()
    assert report.raw_text == "simple note"
    assert report.generated_report is None


def test_generate_english_daily_markdown(mock_llm_client):
    parsed = parse_report(
        "ورود: 08:30\nخروج: 17:15\n- Agentic work",
        person="Amin",
        report_date=date(2026, 9, 22),
    )
    out = generate_professional_report(parsed, client=mock_llm_client)
    assert out.startswith("#daily # amin")
    assert "actions:" in out
    assert "entered at =" in out
