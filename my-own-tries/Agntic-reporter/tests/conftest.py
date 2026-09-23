"""Shared fixtures. Uses SQLite in-memory so tests need no PostgreSQL or API key."""

from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Report


@pytest.fixture()
def db_session():
    """In-memory SQLite session (compatible subset of Postgres for unit tests)."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def sample_reports(db_session):
    """Insert a few sample reports for retrieval tests."""
    reports = [
        Report(
            person="Amin",
            report_date=date(2026, 9, 20),
            start_time=time(8, 30),
            end_time=time(17, 15),
            raw_text="کار روی Agentic Vulnerability Detection و Tool Calling",
            generated_report="توسعه Agentic Vulnerability Detection و پیاده‌سازی Tool Calling",
        ),
        Report(
            person="Amin",
            report_date=date(2026, 9, 21),
            start_time=time(9, 0),
            end_time=time(18, 0),
            raw_text="بررسی OpenRouter و مطالعه مقاله https://example.com/article",
            generated_report="بررسی OpenRouter و مطالعه مقاله مرتبط",
        ),
        Report(
            person="Sara",
            report_date=date(2026, 9, 21),
            start_time=time(10, 0),
            end_time=time(16, 0),
            raw_text="UI improvements for dashboard",
            generated_report="UI improvements for dashboard",
        ),
    ]
    for r in reports:
        db_session.add(r)
    db_session.commit()
    for r in reports:
        db_session.refresh(r)
    return reports


@pytest.fixture()
def mock_llm_client():
    """OpenAI-compatible mock that returns a fixed completion."""
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = (
        "گزارش روزانه\n\n⏰ ساعت کاری: 08:30 تا 17:15\n\n"
        "فعالیت‌ها:\n• توسعه Agentic Vulnerability Detection\n\n"
        "خلاصه:\nتمرکز روی Agentic AI بود."
    )
    choice.message.tool_calls = None
    response = MagicMock()
    response.choices = [choice]
    client.chat.completions.create.return_value = response
    return client
