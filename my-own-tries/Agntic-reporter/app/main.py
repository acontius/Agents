"""Application entrypoint.

Waits for PostgreSQL, creates tables, then launches Gradio.
"""

from __future__ import annotations

import logging
import sys

from app.config import get_settings, setup_logging
from app.database import init_db, wait_for_db
from app.ui.gradio_app import build_ui

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    settings = get_settings()
    logger.info("starting Team Reporting Agent")

    try:
        settings.validate_for_db()
        wait_for_db()
        init_db()
    except Exception as exc:
        logger.error("database startup failed: %s", exc)
        sys.exit(1)

    if not settings.openrouter_api_key:
        logger.warning(
            "OPENROUTER_API_KEY is not set — report generation and agent chat will fail until it is provided"
        )

    demo = build_ui()
    demo.launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
        share=False,
    )


if __name__ == "__main__":
    main()
