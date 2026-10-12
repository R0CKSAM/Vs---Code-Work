"""
network_monitor.py – Playwright network event capture for FanCode.

Attaches request/response listeners to a Playwright Page and collects
safe, non-sensitive metadata about each network event.

Security rules:
- No cookies, auth tokens, or sensitive headers are recorded.
- Request/response bodies are NOT captured.
- Only URL, method, resource type, status, and content-type are stored.

Rate of events:
- A hard cap (MAX_EVENTS_PER_PAGE) prevents memory exhaustion on
  pages with many requests.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from playwright.sync_api import Page, Request, Response

from app.scraper.discovery.models import NetworkEvent

# Resource types we care about for API discovery
RELEVANT_RESOURCE_TYPES = {
    "fetch", "xhr", "document", "other"
}

# Types to completely ignore (media, fonts, tracking pixels)
IGNORE_RESOURCE_TYPES = {
    "image", "media", "font", "stylesheet", "manifest", "ping"
}

# Max events to collect per page (prevents memory bloat)
MAX_EVENTS_PER_PAGE = 200

# Domains to skip entirely (CDNs, analytics, ads — not FanCode API)
SKIP_DOMAINS_RE = re.compile(
    r"google-analytics|googletagmanager|facebook\.net|"
    r"doubleclick|googlesyndication|clarity\.ms|"
    r"hotjar|segment\.io|sentry\.io|newrelic|"
    r"akamai|cloudfront|fastly",
    re.IGNORECASE,
)

JSON_CONTENT_TYPES = re.compile(
    r"application/json|application/graphql|text/json",
    re.IGNORECASE,
)


class NetworkMonitor:
    """
    Attaches to a Playwright Page and records network metadata.

    Usage
    -----
    monitor = NetworkMonitor(page, page_url="https://www.fancode.com/")
    monitor.attach()
    page.goto(...)
    events = monitor.get_events()
    monitor.detach()
    """

    def __init__(self, page: Page, page_url: str = "") -> None:
        self._page = page
        self._page_url = page_url
        self._events: List[NetworkEvent] = []
        self._response_map: Dict[str, Response] = {}
        self._attached = False

    def attach(self) -> None:
        """Start listening to network events on the page."""
        if self._attached:
            return
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)
        self._attached = True

    def detach(self) -> None:
        """Stop listening to network events."""
        if not self._attached:
            return
        try:
            self._page.remove_listener("request", self._on_request)
            self._page.remove_listener("response", self._on_response)
        except Exception:
            pass
        self._attached = False

    def _on_request(self, request: Request) -> None:
        if len(self._events) >= MAX_EVENTS_PER_PAGE:
            return
        if request.resource_type in IGNORE_RESOURCE_TYPES:
            return
        if SKIP_DOMAINS_RE.search(request.url):
            return
        # Store partial event; will be completed in _on_response
        self._events.append(NetworkEvent(
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
            status=None,
            content_type=None,
            is_json=False,
            observed_on=self._page_url,
        ))

    def _on_response(self, response: Response) -> None:
        """Update the matching NetworkEvent with response data."""
        try:
            # Match to our recorded request by URL
            for evt in reversed(self._events):
                if evt.url == response.url and evt.status is None:
                    evt.status = response.status
                    ct = response.headers.get("content-type", "")
                    evt.content_type = ct.split(";")[0].strip() if ct else None
                    evt.is_json = bool(JSON_CONTENT_TYPES.search(ct))
                    break
        except Exception:
            pass

    def get_events(self) -> List[NetworkEvent]:
        """Return all captured events so far (shallow copy)."""
        return list(self._events)

    def clear(self) -> None:
        """Clear all captured events."""
        self._events.clear()
