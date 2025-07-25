import asyncio
import hashlib
import logging
from collections import defaultdict
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session

logger = logging.getLogger(__name__)

JOB_LOCK = defaultdict(asyncio.Lock)


class ConversationJob:
    """
    A class-based job for handling conversations in a specific chat.

    This job:
    1. Fetches recent messages for a specific chat
    2. Processes messages and determines if a reply is needed
    3. Sends replies and saves them to the database
    """

    def __init__(self, chat_id: str):
        """
        Initialize the conversation job for a specific chat.

        Args:
            chat_id: The chat ID to process
            delay_seconds: How long to wait before processing (default: 30 seconds)
        """
        self.chat_id = chat_id

        self._reply_lock: bool = True
        self._run_count = 0

    @property
    def name(self) -> str:
        """Generate a consistent job name for this chat."""
        return f"conversation_processor:{self.chat_id}"

    @property
    def _id(self) -> str:
        return hashlib.md5(self.name.encode()).hexdigest()

    @property
    def sleep_time(self) -> float:
        """Calculate exponential backoff sleep time based on run count."""
        # TODO: Make max_sleep_time configurable per user (see issue #7)
        max_sleep_time = 15
        return min(2**self._run_count, max_sleep_time)

    async def _get_active_session(self, conn) -> Sessions | None:
        """Retrieve the active session for this chat."""
        return await Sessions.get_active_session(conn, self.chat_id)

    async def run(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        """Process conversation for this chat."""

        self._run_count += 1
        now = datetime.now(UTC)

        logger.info(f"Processing conversation for chat {self.chat_id}. Run count: {self._run_count}")

        action_taken = False
        async with async_database_session() as conn:
            chat_session = await self._get_active_session(conn)

            if not chat_session:
                logger.debug(f"No active session found for chat {self.chat_id}")
            elif chat_session.has_bot_responded:
                logger.debug(f"Bot has already responded to chat {self.chat_id}, skipping processing")
            else:
                # If last message was sent more than 30 seconds ago, release reply lock
                if (now - chat_session.last_user_message) > timedelta(seconds=30):
                    self._reply_lock = False

                messages = await chat_session.get_messages(conn)

                if not messages:
                    logger.debug(f"No messages found for chat {self.chat_id}")
                else:
                    action_taken = await self._generate_response(conn, context, messages)

        # Exponential backoff when no action is taken
        if not action_taken:
            logger.debug(f"No action taken for chat {self.chat_id}, sleeping for {self.sleep_time}s")
            await asyncio.sleep(self.sleep_time)
        else:
            # Reset run count when action is taken
            self._run_count = 0

    async def _generate_response(
        self, conn, context: ContextTypes.DEFAULT_TYPE, messages: list[telegram.Message]
    ) -> bool:
        """Process messages for this chat and send appropriate replies.

        Returns:
            bool: True if action was taken (message sent), False otherwise
        """
        logger.debug(f"Processing {len(messages)} messages for chat {self.chat_id}")

        # For now, send a simple "Are you ok?" reply to the most recent message
        # This is where we'll add more sophisticated conversation logic later

        if self._reply_lock:
            return False

        messages.sort(key=lambda msg: msg.date)  # Sort messages by date

        latest_message = messages[-1]

        try:
            # Send reply to the latest message
            reply_text = "Are you ok? 🤔"

            response_message = await context.bot.send_message(
                chat_id=int(self.chat_id), text=reply_text, reply_to_message_id=int(latest_message.message_id)
            )

            # Save the sent message to database
            await Messages.new_or_update(
                session=conn,
                user_id=str(context.bot.id),  # Bot's user ID as the sender
                chat_id=self.chat_id,
                message=response_message,
            )

            active_session = await self._get_active_session(conn)
            if active_session:
                # Record the bot's reply in the session
                await active_session.new_message(timestamp=response_message.date, message_type="bot")

            logger.info(f"Sent reply to chat {self.chat_id}, message {latest_message.message_id}")

        except Exception:
            logger.exception(f"Failed to send reply to chat {self.chat_id}")
            return False
        else:
            return True


async def schedule_conversation_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int, delay_seconds: int = 5) -> None:
    """
    Schedule a conversation processing job for a specific chat.

    Args:
        context: The bot context
        chat_id: The chat ID to process
        delay_seconds: How long to wait before processing (default: 5 seconds)
    """
    processor = ConversationJob(chat_id)

    async with JOB_LOCK[str(chat_id)]:
        # Check if a job already exists for this chat
        existing_jobs = context.job_queue.get_jobs_by_name(processor.name)
        if existing_jobs:
            logger.debug(f"Job already scheduled for chat {chat_id}, skipping")
            return

        # Schedule the job to run once after the specified delay
        context.job_queue.run_repeating(
            callback=processor.run,
            interval=1,
            first=delay_seconds,
            name=processor.name,
            chat_id=chat_id,
            job_kwargs={
                "id": processor.name,
                "coalesce": True,
                "max_instances": 1,
            },
        )
