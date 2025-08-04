import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
import pydantic_ai
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.data import Context
from areyouok_telegram.data import LLMUsage
from areyouok_telegram.data import Messages
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database_session
from areyouok_telegram.jobs.exceptions import NoActiveSessionError
from areyouok_telegram.llms.analytics import DynamicContextCompression
from areyouok_telegram.llms.chat import AgentResponse
from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.llms.utils import convert_telegram_message_to_model_message

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

        logfire.debug(f"Running conversation job for chat {self.chat_id}. Run count: {self._run_count}")

        async with async_database_session() as conn:
            chat_session = await self._get_active_session(conn)

            if not chat_session:
                # This is unexpected behaviour, could imply race conditions in play.
                raise NoActiveSessionError(self.chat_id)

            elif chat_session.has_bot_responded:
                logfire.debug(f"No new updates in {self.chat_id}, skipping processing.")

            else:
                await self._generate_response(conn, context, chat_session)
                return

            # If the last user activity was more than an hour ago, stop the job
            if chat_session.last_user_activity and (self._run_timestamp - chat_session.last_user_activity) > timedelta(
                seconds=60 * 60  # 1 hour
            ):
                with logfire.span(
                    f"Terminating chat session {self.chat_id} due to inactivity.",
                    last_user_activity=chat_session.last_user_activity,
                    run_timestamp=self._run_timestamp,
                    inactivity_duration=(self._run_timestamp - chat_session.last_user_activity).total_seconds(),
                ):
                    await self._compress_session_context(conn, chat_session)

                    await chat_session.close_session(
                        session=conn,
                        timestamp=self._run_timestamp,
                    )

                    await self._stop(context)

    async def _generate_response(self, conn, context: ContextTypes.DEFAULT_TYPE, chat_session: Sessions) -> bool:
        """Process messages for this chat and send appropriate replies.

        Returns:
            bool: True if action was taken (message sent), False otherwise
        """

        last_context = await Context.retrieve_context_by_chat(
            session=conn,
            chat_id=self.chat_id,
            ctype="session",
        )

        last_context.sort(key=lambda c: c.created_at)  # Sort by creation time

        context_content = [
            pydantic_ai.messages.ModelResponse(
                parts=[
                    pydantic_ai.messages.TextPart(
                        content=json.dumps(
                            {
                                "timestamp": (
                                    f"{(context.created_at - self._run_timestamp).total_seconds()} seconds ago"
                                ),
                                "content": f"Summary of prior conversation:\n\n{context.content}",
                            }
                        ),
                        part_kind="text",
                    )
                ],
            )
            for context in last_context
        ]

        messages = await chat_session.get_messages(conn)
        messages.sort(key=lambda msg: msg.date)  # Sort messages by date

        context_content.extend(
            [convert_telegram_message_to_model_message(context, msg, self._run_timestamp) for msg in messages]
        )

        try:
            agent_run_payload = await chat_agent.run(
                message_history=context_content,
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
            logfire.exception(f"Failed to generate response for chat {self.chat_id}")
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
            logfire.exception(f"Failed to execute response for chat {self.chat_id}")
            return False

        else:
            await chat_session.new_activity(
                timestamp=self._run_timestamp,
                is_user=False,  # This is a bot response
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
                        is_user=False,  # This is a bot response
                    )
                return True
        finally:
            # Track LLM usage for this chat
            await LLMUsage.track_pydantic_usage(
                session=conn,
                chat_id=self.chat_id,
                session_id=chat_session.session_key,
                agent=chat_agent,
                data=agent_run_payload.usage(),
            )

        return False

    async def _stop(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Stop the conversation job for this chat."""
        async with JOB_LOCK[str(self.chat_id)]:
            existing_jobs = context.job_queue.get_jobs_by_name(self.name)
            if not existing_jobs:
                logfire.warning(f"No existing job found for chat {self.chat_id}, nothing to stop.")
                return

            for job in existing_jobs:
                job.schedule_removal()

        logfire.info(f"Stopped conversation job for chat {self.chat_id} due to inactivity.")

    async def _compress_session_context(self, conn, chat_session: Sessions) -> None:
        """
        Compress the session context for this chat.
        Uses it's own database connection to avoid conflicts with other jobs.
        """

        context_compression = DynamicContextCompression()

        context = await Context.get_by_session_id(
            session=conn,
            session_id=chat_session.session_key,
            ctype="session",
        )

        if context:
            logfire.debug(f"Context already exists for session {chat_session.session_key}, skipping compression.")
            return

        messages = await chat_session.get_messages(conn)
        messages.sort(key=lambda msg: msg.date)

        result = await asyncio.to_thread(
            context_compression,
            messages=messages,
        )

        await Context.new_or_update(
            session=conn,
            chat_id=self.chat_id,
            session_id=chat_session.session_key,
            ctype="session",
            content=result.context,
        )

        await LLMUsage.track_dspy_usage(
            session=conn,
            chat_id=self.chat_id,
            session_id=chat_session.session_key,
            usage_type=context_compression,
            data=result.get_lm_usage(),
        )
        logfire.info(f"Compressed session context for chat {self.chat_id} with session key {chat_session.session_key}.")


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
            logfire.debug(f"Job already scheduled for chat {chat_id}, skipping.")
            return

        # Schedule the job to run once after the specified delay
        context.job_queue.run_repeating(
            callback=processor.run,
            interval=interval,
            first=int(interval / 2),
            name=processor.name,
            chat_id=chat_id,
            job_kwargs={
                "id": processor._id,
                "coalesce": True,
                "max_instances": 1,
            },
        )
        logfire.info(f"Scheduled conversation job for chat {chat_id} with interval {interval} seconds.")
