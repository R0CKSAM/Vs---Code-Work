"""
network.py – Intercepts network responses specifically relevant to FanCode schedule data.

Filters out noise, tracking, ad platforms, and safely extracts JSON response bodies
from observed schedule/match endpoints. Never captures cookies, tokens, or credentials.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page, Response

logger = logging.getLogger(__name__)

# Endpoints or paths containing schedule/match structured data
SCHEDULE_API_PATTERNS = re.compile(
    r"/api/|/schedule|/matches|/fixtures|/events|/tournaments|/sports",
    re.IGNORECASE,
)

# Ad / analytics / tracking domains to ignore
IGNORE_DOMAINS = re.compile(
    r"google|doubleclick|clarity|segment|facebook|hotjar|sentry|datadog|branch\.io",
    re.IGNORECASE,
)


class ScheduleNetworkInterceptor:
    """
    Listens to Playwright Page response events, identifying and parsing
    public structured JSON payloads containing schedule/match data.
    """

    def __init__(self, page: Page) -> None:
        self.page = page
        self.captured_payloads: List[Dict[str, Any]] = []
        self._attached = False

    def attach(self) -> None:
        if self._attached:
            return
        self.page.on("response", self._on_response)
        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            return
        try:
            self.page.remove_listener("response", self._on_response)
        except Exception:
            pass
        self._attached = False

    def _on_response(self, response: Response) -> None:
        try:
            url = response.url
            if IGNORE_DOMAINS.search(url):
                return

            ct = response.headers.get("content-type", "")
            if not ("application/json" in ct or "text/json" in ct):
                return

            if response.status != 200:
                return

            # Check if this URL matches potential schedule/match paths
            if SCHEDULE_API_PATTERNS.search(url):
                try:
                    body_text = response.text()
                    data = json.loads(body_text)
                    if isinstance(data, (dict, list)):
                        self.captured_payloads.append({
                            "url": url,
                            "status": response.status,
                            "data": data,
                        })
                except Exception as exc:
                    logger.debug("Failed parsing JSON from %s: %s", url, exc)
        except Exception as exc:
            logger.debug("Error in response handler: %s", exc)

    def get_payloads(self) -> List[Dict[str, Any]]:
        return list(self.captured_payloads)

    def clear(self) -> None:
        self.captured_payloads.clear()
