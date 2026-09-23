"""Database engine, session factory, and connection retry logic."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_engine(url: str | None = None, *, echo: bool = False):
    """Create (or return cached) SQLAlchemy engine."""
    global _engine, _SessionLocal
    if _engine is not None and url is None:
        return _engine

    settings = get_settings()
    db_url = url or settings.database_url
    engine = create_engine(
        db_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    if url is None:
        _engine = engine
        _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return engine


def get_session_factory(url: str | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is not None and url is None:
        return _SessionLocal
    engine = get_engine(url)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    if url is None:
        _SessionLocal = factory
    return factory


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager that yields a session and commits / rolls back."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def wait_for_db(max_retries: int = 30, delay: float = 2.0) -> None:
    """Block until PostgreSQL accepts connections (used by Docker entrypoint)."""
    settings = get_settings()
    settings.validate_for_db()
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("database connection established (attempt %d)", attempt)
            return
        except Exception as exc:
            last_err = exc
            logger.warning(
                "database not ready (attempt %d/%d): %s",
                attempt,
                max_retries,
                exc,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"Could not connect to PostgreSQL after {max_retries} attempts: {last_err}"
    )


def init_db() -> None:
    """Create tables if they do not exist."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("database tables ensured")


def reset_engine() -> None:
    """Reset cached engine (useful in tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
