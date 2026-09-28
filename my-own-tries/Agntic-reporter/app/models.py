"""SQLAlchemy 2.x ORM models.

The schema is intentionally minimal but extensible:
- raw_text is ALWAYS preserved
- generated_report holds the LLM-polished Markdown version
- path links a daily report to a learning/work track (optional)
- ProgressPath defines named tracks with optional total_items for % calculation
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
    path: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
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
            "path": self.path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def short_label(self) -> str:
        """Human-readable label for agent context (no database id)."""
        base = f"{self.report_date.isoformat()} — {self.person}"
        if self.path:
            return f"{base} [{self.path}]"
        return base


class ProgressPath(Base):
    """A named learning/work path (e.g. Agentic AI Course, Hack The Box).

    total_items is optional. When set, percentage can be derived from the
    number of completed action items recorded against this path.
    When unset, percentage is only shown if an explicit % appears in reports.
    """

    __tablename__ = "progress_paths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_items: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "total_items": self.total_items,
        }


# Seed defaults used when the table is empty
DEFAULT_PATHS: list[tuple[str, str | None, int | None]] = [
    ("Agentic AI Course", "Agentic AI learning track", 20),
    ("Hack The Box", "HTB labs and machines", 50),
    ("PortSwigger", "Web Security Academy", 40),
    ("AI Security", "AI security research path", 15),
    ("General", "Uncategorized daily work", None),
]
