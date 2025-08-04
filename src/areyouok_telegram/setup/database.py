"""Database setup and initialization."""

import logfire
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateSchema

from areyouok_telegram.config import ENV
from areyouok_telegram.config import PG_CONNECTION_STRING


def database_setup():
    """Setup the database connection and create tables if they do not exist."""

    from areyouok_telegram.data import Base  # noqa: PLC0415

    engine = create_engine(f"postgresql://{PG_CONNECTION_STRING}")

    with engine.begin() as conn:
        # Create schemas if they do not exist
        conn.execute(CreateSchema(ENV, if_not_exists=True))

        # Create all tables in the specified schema
        Base.metadata.create_all(conn)

    logfire.info(f"Database setup complete. All tables created in schema '{ENV}'.")
