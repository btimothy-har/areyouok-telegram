"""Logging setup and configuration."""

import logging
from importlib.metadata import version

import logfire

from areyouok_telegram.config import ENV
from areyouok_telegram.config import GITHUB_REPOSITORY
from areyouok_telegram.config import GITHUB_SHA
from areyouok_telegram.config import LOGFIRE_TOKEN

logger = logging.getLogger(__name__)


def logging_setup():
    """Setup logging configuration."""

    controlled_environments = ["production", "staging"]

    logging.basicConfig(level=logging.INFO, handlers=[logfire.LogfireLoggingHandler()])

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

    console = False
    code_source = None

    if ENV in controlled_environments:
        if GITHUB_REPOSITORY and GITHUB_SHA:
            code_source = logfire.CodeSource(
                repository=f"https://github.com/{GITHUB_REPOSITORY}",
                revision=GITHUB_SHA,
            )
    else:
        console = logfire.ConsoleOptions(
            span_style="show-parents",
            show_project_link=False,
        )

    logfire.configure(
        send_to_logfire=True if LOGFIRE_TOKEN else False,
        token=LOGFIRE_TOKEN,
        service_name="areyouok-telegram",
        service_version=version("areyouok-telegram"),
        environment=ENV,
        console=console,
        code_source=code_source,
        distributed_tracing=False,
        scrubbing=False,
    )

    logger.info("Logging setup complete.")
