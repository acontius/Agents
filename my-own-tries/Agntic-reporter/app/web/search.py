"""Minimal web-fetch tool for URLs that appear in reports.

Uses httpx. Never fabricates content. Returns a short excerpt only.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_MAX_CHARS = 2000
_TIMEOUT = 12.0


def fetch_url_summary(url: str) -> str:
    """Fetch a URL and return a brief plain-text excerpt.

    On failure returns an explicit error message (no invented content).
    """
    url = (url or "").strip()
    if not url:
        return "Error: empty URL"

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return f"Error: invalid URL scheme or host: {url}"
    except Exception:
        return f"Error: malformed URL: {url}"

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_TIMEOUT,
            headers={"User-Agent": "AgnticReporter/0.1 (educational agent)"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type:
                return f"Fetched {url} (non-text content-type: {content_type}). No text summary available."

            text = resp.text
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
            text = re.sub(r"<[^>]+", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                return f"Fetched {url} but extracted no readable text."
            excerpt = text[:_MAX_CHARS]
            if len(text) > _MAX_CHARS:
                excerpt += "…"
            return f"URL: {url}\nExcerpt:\n{excerpt}"
    except httpx.TimeoutException:
        logger.warning("timeout fetching %s", url)
        return f"Error: timeout while fetching {url}"
    except httpx.HTTPStatusError as exc:
        logger.warning("HTTP %s for %s", exc.response.status_code, url)
        return f"Error: HTTP {exc.response.status_code} for {url}"
    except Exception as exc:
        logger.warning("fetch failed for %s: %s", url, exc)
        return f"Error: could not fetch {url}: {type(exc).__name__}"
