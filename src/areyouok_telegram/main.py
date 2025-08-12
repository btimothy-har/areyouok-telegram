"""Main entry point for the Telegram bot application."""

import asyncio
import logging
from importlib.metadata import version
from typing import Any

import logfire
import telegram
import uvloop

from areyouok_telegram.app import create_application
from areyouok_telegram.config import CONTROLLED_ENV
from areyouok_telegram.config import ENV
from areyouok_telegram.config import GITHUB_REPOSITORY
from areyouok_telegram.config import GITHUB_SHA
from areyouok_telegram.config import LOGFIRE_TOKEN
from areyouok_telegram.setup import database_setup


def scrub_telegram_data(data: logfire.ScrubMatch) -> Any | None:
    sensitive_paths = [
        ("message", "text"),
        ("chat", "first_name"),
        ("chat", "last_name"),
        ("chat", "username"),
        ("from", "first_name"),
        ("from", "last_name"),
        ("from", "username"),
        ("user", "first_name"),
        ("user", "last_name"),
        ("user", "username"),
        ("return", "text"),
        ("response", "message_text"),
    ]

    if any(data.path[-len(path) :] == path for path in sensitive_paths):
        return "[REDACTED]"

    return data.value


if __name__ == "__main__":
    # Configure event loop policy for performance
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    # Setup logging
    logging.getLogger().addHandler(logfire.LogfireLoggingHandler())

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

    console = logfire.ConsoleOptions(
        span_style="show-parents",
        show_project_link=False,
        min_log_level="debug",
        verbose=True,
    )
    code_source = None

    if ENV in CONTROLLED_ENV:
        if GITHUB_REPOSITORY and GITHUB_SHA:
            code_source = logfire.CodeSource(
                repository=f"https://github.com/{GITHUB_REPOSITORY}",
                revision=GITHUB_SHA,
            )

    logfire.configure(
        send_to_logfire=True if LOGFIRE_TOKEN else False,
        min_level="debug" if ENV == "development" else "info",
        token=LOGFIRE_TOKEN,
        service_name="areyouok-telegram",
        service_version=version("areyouok-telegram"),
        environment=ENV,
        console=console,
        code_source=code_source,
        distributed_tracing=False,
        scrubbing=logfire.ScrubbingOptions(
            callback=scrub_telegram_data,
            extra_patterns=[
                "text",
                "first_name",
                "username",
                "message_text",
            ],
        ),
    )

    logfire.log_slow_async_callbacks(slow_duration=0.25)

    # Initialize infrastructure
    with logfire.span("Application is starting."):
        database_setup()
        application = create_application()

    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES, drop_pending_updates=True)
