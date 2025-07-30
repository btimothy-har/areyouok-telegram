import asyncio
import hashlib
import logging
from collections import defaultdict
from datetime import UTC
from datetime import datetime

import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.agent import AgentResponse
from areyouok_telegram.agent import ChatAgentDependencies
from areyouok_telegram.agent import chat_agent
from areyouok_telegram.agent import convert_telegram_message_to_model_message
from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.jobs.exceptions import NoActiveSessionError

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
        """
        self.chat_id = chat_id

        self._last_response = None
        self._run_timestamp = datetime.now(UTC)
        self._run_count = 0

    @property
    def name(self) -> str:
        """Generate a consistent job name for this chat."""
        return f"conversation_processor:{self.chat_id}"

    @property
    def _id(self) -> str:
        return hashlib.md5(self.name.encode()).hexdigest()

    async def _get_active_session(self, conn) -> Sessions | None:
        """Retrieve the active session for this chat."""
        return await Sessions.get_active_session(conn, self.chat_id)

    async def run(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        """Process conversation for this chat."""

        self._run_count += 1
        self._run_timestamp = datetime.now(UTC)

        logger.info(f"Processing conversation for chat {self.chat_id}. Run count: {self._run_count}")

        async with async_database_session() as conn:
            chat_session = await self._get_active_session(conn)

            if not chat_session:
                # This is unexpected behaviour, could imply race conditions in play.
                raise NoActiveSessionError(self.chat_id)

            elif chat_session.has_bot_responded:
                logger.debug(f"No new updates in {self.chat_id}, skipping processing.")
                return

            else:
                await self._generate_response(conn, context, chat_session)

    async def _generate_response(self, conn, context: ContextTypes.DEFAULT_TYPE, chat_session: Sessions) -> bool:
        """Process messages for this chat and send appropriate replies.

        Returns:
            bool: True if action was taken (message sent), False otherwise
        """
        messages = await chat_session.get_messages(conn)
        messages.sort(key=lambda msg: msg.date)  # Sort messages by date

        try:
            agent_run_payload = await chat_agent.run(
                message_history=[
                    convert_telegram_message_to_model_message(context, msg, self._run_timestamp) for msg in messages
                ],
                deps=ChatAgentDependencies(
                    tg_context=context,
                    tg_chat_id=self.chat_id,
                    last_response_type=self._last_response,
                    db_connection=conn,
                ),
            )

            agent_response: AgentResponse = agent_run_payload.data

        except Exception:
            # TODO: Handle LLM errors
            logger.exception(f"Failed to generate response for chat {self.chat_id}")
            return False

        try:
            self._last_response = agent_response.response_type

            response_message = await agent_response.execute(
                db_connection=conn,
                context=context,
                chat_id=self.chat_id,
            )

        except Exception:
            # TODO: Handle response execution errors
            logger.exception(f"Failed to execute response for chat {self.chat_id}")
            return False

        else:
            await chat_session.new_activity(
                timestamp=self._run_timestamp,
                activity_type="bot",
            )

            if response_message:
                await Messages.new_or_update(
                    session=conn,
                    user_id=str(context.bot.id),  # Bot's user ID as the sender
                    chat_id=self.chat_id,
                    message=response_message,
                )

                if isinstance(response_message, telegram.Message):
                    await chat_session.new_message(
                        timestamp=response_message.date,
                        message_type="bot",
                    )
                return True

        return False


async def schedule_conversation_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int, interval: int = 10) -> None:
    """
    Schedule a conversation processing job for a specific chat.

    Args:
        context: The bot context
        chat_id: The chat ID to process
        interval: The interval in seconds between job runs (default: 10 seconds)
    """
    processor = ConversationJob(chat_id)

    async with JOB_LOCK[str(chat_id)]:
        # Check if a job already exists for this chat
        existing_jobs = context.job_queue.get_jobs_by_name(processor.name)
        if existing_jobs:
            logger.debug(f"Job already scheduled for chat {chat_id}, skipping.")
            return

        # Schedule the job to run once after the specified delay
        context.job_queue.run_repeating(
            callback=processor.run,
            interval=interval,
            first=int(interval / 2),
            name=processor.name,
            chat_id=chat_id,
            job_kwargs={
                "id": processor.name,
                "coalesce": True,
                "max_instances": 1,
            },
        )
