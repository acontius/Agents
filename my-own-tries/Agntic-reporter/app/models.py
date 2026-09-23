"""SQLAlchemy 2.x ORM models.

The schema is intentionally minimal but extensible:
- raw_text is ALWAYS preserved
- generated_report holds the LLM-polished version
- Future: embeddings, projects, tags, extracted activities
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, String, Text, Time, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Report(Base):
    """Daily report submitted by a team member."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    end_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Report id={self.id} person={self.person!r} "
            f"date={self.report_date}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "person": self.person,
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "raw_text": self.raw_text,
            "generated_report": self.generated_report,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def short_label(self) -> str:
        """Human-readable label used in evidence lists."""
        return f"{self.report_date.isoformat()} — {self.person} (id={self.id})"
