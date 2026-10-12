"""
context.py – Run and Stage Correlation Context for FanCode Monitor (Phase 11).

Provides thread-safe and async-safe context variable propagation for:
- monitor_run_id
- stage
- scrape_run_id
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

_run_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("monitor_run_id", default=None)
_stage_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("monitor_stage", default=None)
_scrape_run_id_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("scrape_run_id", default=None)


def set_correlation_context(
    run_id: Optional[str] = None,
    stage: Optional[str] = None,
    scrape_run_id: Optional[int] = None,
) -> None:
    """Sets current correlation values in contextvars."""
    if run_id is not None:
        _run_id_var.set(run_id)
    if stage is not None:
        _stage_var.set(stage)
    if scrape_run_id is not None:
        _scrape_run_id_var.set(scrape_run_id)


def get_correlation_context() -> Dict[str, Any]:
    """Retrieves current correlation dictionary."""
    return {
        "run_id": _run_id_var.get(),
        "stage": _stage_var.get(),
        "scrape_run_id": _scrape_run_id_var.get(),
    }


def clear_correlation_context() -> None:
    """Resets all correlation context variables to None."""
    _run_id_var.set(None)
    _stage_var.set(None)
    _scrape_run_id_var.set(None)


@contextmanager
def correlation_scope(
    run_id: Optional[str] = None,
    stage: Optional[str] = None,
    scrape_run_id: Optional[int] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Scoped context manager for correlation context."""
    token_run = _run_id_var.set(run_id) if run_id is not None else None
    token_stage = _stage_var.set(stage) if stage is not None else None
    token_scrape = _scrape_run_id_var.set(scrape_run_id) if scrape_run_id is not None else None
    try:
        yield get_correlation_context()
    finally:
        if token_run is not None:
            _run_id_var.reset(token_run)
        if token_stage is not None:
            _stage_var.reset(token_stage)
        if token_scrape is not None:
            _scrape_run_id_var.reset(token_scrape)
