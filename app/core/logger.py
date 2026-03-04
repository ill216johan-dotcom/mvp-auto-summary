"""
Structured logging setup using structlog.

Replaces scattered print() calls and n8n execution logs with
consistent, machine-parseable log output.
"""
from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog with console renderer for Docker log output."""

    # Configure stdlib logging (used by APScheduler, httpx, etc.)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a named logger instance."""
    return structlog.get_logger(name)  # type: ignore[return-value]
