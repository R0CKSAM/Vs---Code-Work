"""
test_database.py – Playwright automated tests for Database Health & Diagnostic Endpoint.

Launches the minimal FastAPI test server in a background thread, uses Playwright
to navigate to /health/db and /health, and verifies:
1. HTTP 200 response
2. JSON content verification
3. Database connection status ("ok", "connected")
4. Tables initialized status (tables: true)
5. Repeated request stability
6. No console error logs
"""

from __future__ import annotations

import json
import threading
import time
from typing import Generator

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from app.api.app import app
from app.database.connection import init_db

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
BASE_TEST_API_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


class UvicornServerThread(threading.Thread):
    def __init__(self, host: str, port: int) -> None:
        super().__init__(daemon=True)
        config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config=config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


@pytest.fixture(scope="session", autouse=True)
def start_diagnostic_server() -> Generator[None, None, None]:
    """Start the test diagnostic server once per test session."""
    init_db()  # Ensure DB tables are initialized
    server_thread = UvicornServerThread(SERVER_HOST, SERVER_PORT)
    server_thread.start()

    # Wait up to 5 seconds for server to be responsive
    import urllib.request
    started = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE_TEST_API_URL}/health", timeout=0.2) as resp:
                if resp.status == 200:
                    started = True
                    break
        except Exception:
            time.sleep(0.1)

    if not started:
        raise RuntimeError("Diagnostic test API server failed to start in time.")

    yield

    server_thread.stop()
    server_thread.join(timeout=2)


class TestDatabasePlaywrightE2E:
    """Automated Playwright tests for Database Diagnostic Surface."""

    def test_health_endpoint_loads(self, page: Page) -> None:
        """Verify GET /health responds with status ok."""
        response = page.goto(f"{BASE_TEST_API_URL}/health")
        assert response is not None
        assert response.status == 200
        content = page.text_content("body")
        assert content is not None
        data = json.loads(content)
        assert data.get("status") == "ok"

    def test_db_health_endpoint_connectivity(self, page: Page) -> None:
        """Verify GET /health/db responds with database connected and tables true."""
        response = page.goto(f"{BASE_TEST_API_URL}/health/db")
        assert response is not None
        assert response.status == 200

        content = page.text_content("body")
        assert content is not None
        data = json.loads(content)

        assert data.get("status") == "ok"
        assert data.get("database") == "connected"
        assert data.get("tables") is True
        assert data.get("table_count", 0) >= 7

    def test_db_health_repeated_requests(self, page: Page) -> None:
        """Verify database health endpoint handles repeated navigation gracefully."""
        for _ in range(3):
            response = page.goto(f"{BASE_TEST_API_URL}/health/db")
            assert response is not None
            assert response.status == 200
            content = page.text_content("body")
            assert content is not None
            data = json.loads(content)
            assert data["database"] == "connected"

    def test_db_health_no_console_errors(self, page: Page) -> None:
        """Verify navigation to /health/db produces no unhandled browser console errors."""
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        response = page.goto(f"{BASE_TEST_API_URL}/health/db")
        assert response is not None
        assert response.status == 200
        assert len(console_errors) == 0
