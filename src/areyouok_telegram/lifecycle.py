import logging

logger = logging.getLogger(__name__)

# Self-contained imports for setup and shutdown.
# ruff: noqa: PLC0415


def database_setup():
    """Setup the database connection and create tables if they do not exist."""
    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateSchema

    from areyouok_telegram.config import ENV
    from areyouok_telegram.config import PG_CONNECTION_STRING
    from areyouok_telegram.data import Base

    engine = create_engine(f"postgresql://{PG_CONNECTION_STRING}")

    with engine.begin() as conn:
        # Create schemas if they do not exist
        conn.execute(CreateSchema(ENV, if_not_exists=True))

        # Create all tables in the specified schema
        Base.metadata.create_all(conn)

    logger.info(f"Database setup complete. All tables created in schema '{ENV}'.")


def logging_setup():
    """Setup logging configuration."""
    import logging
    from importlib.metadata import version

    import logfire

    from areyouok_telegram.config import ENV
    from areyouok_telegram.config import GITHUB_REPOSITORY
    from areyouok_telegram.config import GITHUB_SHA
    from areyouok_telegram.config import LOGFIRE_TOKEN

    controlled_environments = ["production", "staging"]

    logging.basicConfig(level=logging.INFO, handlers=[logfire.LogfireLoggingHandler()])

    logging.getLogger("httpx").setLevel(logging.WARNING)
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
