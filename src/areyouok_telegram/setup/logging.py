"""Logging setup and configuration."""

import logging
from importlib.metadata import version

import logfire

from areyouok_telegram.config import CONTROLLED_ENV
from areyouok_telegram.config import ENV
from areyouok_telegram.config import GITHUB_REPOSITORY
from areyouok_telegram.config import GITHUB_SHA
from areyouok_telegram.config import LOGFIRE_TOKEN


def logging_setup():
    """Setup logging configuration."""

    logging.getLogger().addHandler(logfire.LogfireLoggingHandler())

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

    console = False
    code_source = None

    if ENV in CONTROLLED_ENV:
        if GITHUB_REPOSITORY and GITHUB_SHA:
            code_source = logfire.CodeSource(
                repository=f"https://github.com/{GITHUB_REPOSITORY}",
                revision=GITHUB_SHA,
            )
    else:
        console = logfire.ConsoleOptions(
            span_style="show-parents",
            show_project_link=False,
            min_log_level="debug",
            verbose=True,
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
        scrubbing=False,
    )

    logfire.log_slow_async_callbacks(slow_duration=0.25)

    logfire.info("Logging setup complete.")
