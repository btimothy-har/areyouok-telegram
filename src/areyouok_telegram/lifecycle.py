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
