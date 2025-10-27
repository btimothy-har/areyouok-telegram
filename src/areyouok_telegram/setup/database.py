"""Database setup and initialization."""

import logfire
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateSchema

from areyouok_telegram.config import ENV, PG_CONNECTION_STRING
from areyouok_telegram.logging import traced


@traced(extract_args=False)
def database_setup():
    """Setup the database connection and create tables if they do not exist."""

    from areyouok_telegram.data.database import Base  # noqa: PLC0415

    engine = create_engine(f"postgresql://{PG_CONNECTION_STRING}")

    with engine.begin() as conn:
        # Create schemas if they do not exist
        conn.execute(CreateSchema(ENV, if_not_exists=True))

        # Create all tables in the specified schema
        Base.metadata.create_all(conn)

    logfire.info(f"Database setup complete. All tables created in schema '{ENV}'.")


@traced(extract_args=False)
async def create_bot_user(bot_id: int):
    """Create or update the bot user for bot-generated messages.

    Args:
        bot_id: The Telegram bot user ID
    """
    from areyouok_telegram.data.models import User  # noqa: PLC0415

    # Check if bot user already exists
    bot_user = await User.get_by_id(telegram_user_id=bot_id)
    if bot_user:
        logfire.info(f"Bot user already exists with id={bot_user.id}")
        return

    # Create bot user
    bot_user = User(
        telegram_user_id=bot_id,
        is_bot=True,
        is_premium=False,
    )
    bot_user = await bot_user.save()
    logfire.info(f"Created bot user with id={bot_user.id}, telegram_user_id={bot_id}")
