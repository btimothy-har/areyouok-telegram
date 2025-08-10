from datetime import UTC
from datetime import datetime
from datetime import timedelta

import logfire
import pydantic_ai
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.config import CHAT_SESSION_TIMEOUT_MINS
from areyouok_telegram.data import Context
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.data import Messages
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs import BaseJob
from areyouok_telegram.jobs.exceptions import UserNotFoundForChatError
from areyouok_telegram.llms.chat import AgentResponse
from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import ReactionResponse
from areyouok_telegram.llms.chat import TextResponse
from areyouok_telegram.llms.context_compression import ContextTemplate
from areyouok_telegram.llms.context_compression import context_compression_agent
from areyouok_telegram.llms.utils import context_to_model_message
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.llms.utils import telegram_message_to_model_message
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import traced

from .utils import close_chat_session
from .utils import generate_chat_agent
from .utils import get_chat_session
from .utils import get_user_encryption_key
from .utils import log_bot_activity
from .utils import post_cleanup_tasks
from .utils import save_session_context


class ConversationJob(BaseJob):
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
        super().__init__()
        self.chat_id = str(chat_id)
        self.last_response = None

    @property
    def name(self) -> str:
        """Generate a consistent job name for this chat."""
        return f"conversation:{self.chat_id}"

    async def _run(self, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        """Process conversation for this chat."""

        # Get user encryption key - this will fail for non-private chats
        try:
            user_encryption_key = await get_user_encryption_key(self.chat_id)
        except UserNotFoundForChatError:
            logfire.warning(f"Stopping conversation job for chat {self.chat_id} - no user found (non-private chat).")
            await self.stop(context)
            return

        chat_session = await get_chat_session(chat_id=self.chat_id)

        if not chat_session:
            # If no active session is found, log a warning and stop the job
            # This can happen if the user submits a command without chatting
            logfire.warning("Conversation job started without an active session.")
            await self.stop(context)

        elif chat_session.has_bot_responded:
            logfire.debug("No new updates, nothing to do.")

            # If the last user activity was more than an hour ago, stop the job
            if chat_session.last_user_activity:
                inactivity_duration = self._run_timestamp - chat_session.last_user_activity

                if inactivity_duration > timedelta(minutes=CHAT_SESSION_TIMEOUT_MINS):
                    with logfire.span(
                        f"Closing chat session {chat_session.session_id} due to inactivity.",
                        _span_name="ConversationJob._run.close_session",
                        chat_id=self.chat_id,
                    ):
                        await self.close_session(user_encryption_key, chat_session=chat_session)
                        await self.stop(context)
                        await post_cleanup_tasks(context=context, chat_session=chat_session)

        else:
            with logfire.span(
                f"Generating response in {chat_session.session_id}.",
                _span_name="ConversationJob._run.respond",
                chat_id=self.chat_id,
            ):
                message_history, instructions = await self._prepare_conversation_input(
                    user_encryption_key, chat_session=chat_session, include_context=True
                )
                response = await self.generate_response(
                    context=context,
                    user_encryption_key=user_encryption_key,
                    chat_session=chat_session,
                    conversation_history=message_history,
                    instructions=instructions or None,
                )

                self.last_response = response.response_type

                response_message = await self.execute_response(user_encryption_key, context=context, response=response)

                await log_bot_activity(
                    bot_id=context.bot.id,
                    user_encryption_key=user_encryption_key,
                    chat_id=self.chat_id,
                    chat_session=chat_session,
                    response_message=response_message,
                )

    @traced(extract_args=["chat_session", "instructions"])
    async def generate_response(
        self,
        *,
        context: ContextTypes.DEFAULT_TYPE,
        user_encryption_key: str,
        chat_session: Sessions,
        conversation_history: list[pydantic_ai.messages.ModelMessage],
        instructions: str | None = None,
    ) -> AgentResponse | None:
        """Process messages for this chat and send appropriate replies.

        Returns:
            AgentResponse: The response generated by the chat agent, or None if an error occurred.
        """
        agent_run_payload = None

        agent = await generate_chat_agent(
            chat_session=chat_session,
        )

        try:
            agent_run_payload = await run_agent_with_tracking(
                agent,
                chat_id=self.chat_id,
                session_id=chat_session.session_id,
                run_kwargs={
                    "message_history": conversation_history,
                    "deps": ChatAgentDependencies(
                        tg_context=context,
                        tg_chat_id=self.chat_id,
                        tg_session_id=chat_session.session_id,
                        last_response_type=self.last_response,
                        user_encryption_key=user_encryption_key,
                        instruction=instructions or None,
                    ),
                },
            )

            agent_response: AgentResponse = agent_run_payload.output

        except Exception:
            # TODO: Handle LLM errors
            logfire.exception(f"Failed to generate response for chat {self.chat_id}")

        else:
            return agent_response

    @traced(extract_args=["response"], record_return=True)
    async def execute_response(
        self, user_encryption_key: str, *, context: ContextTypes.DEFAULT_TYPE, response: AgentResponse
    ) -> MessageTypes | None:
        """Execute the response action in the given context."""

        response_message = None

        if response.response_type == "TextResponse":
            response_message = await self._execute_text_response(context=context, response=response)

        elif response.response_type == "ReactionResponse":
            # Get the message to react to
            async with async_database() as db_conn:
                message, _ = await Messages.retrieve_message_by_id(
                    db_conn,
                    user_encryption_key,
                    message_id=response.react_to_message_id,
                    chat_id=self.chat_id,
                    include_reactions=False,
                )

            if not message:
                logfire.warning(
                    f"Message {response.react_to_message_id} not found in chat {self.chat_id}, skipping reaction."
                )
                return

            response_message = await self._execute_reaction_response(
                context=context, response=response, message=message
            )

        logfire.info(f"Response executed in chat {self.chat_id}: {response.response_type}.")

        return response_message

    @traced(extract_args=["chat_session"])
    async def close_session(self, user_encryption_key: str, *, chat_session: Sessions) -> None:
        """Closes the chat session and compresses the context."""

        async with async_database() as db_conn:
            context = await Context.get_by_session_id(
                db_conn, user_encryption_key, session_id=chat_session.session_key, ctype="session"
            )

        if context:
            logfire.warning(
                "Context already exists for session, skipping compression.",
                session_id=chat_session.session_id,
            )
            return

        message_history, _ = await self._prepare_conversation_input(
            user_encryption_key, chat_session=chat_session, include_context=False
        )

        if len(message_history) == 0:
            logfire.warning(f"No messages found in chat session {chat_session.session_id}, nothing to compress.")
            return

        compressed_context = await self._compress_session_context(
            chat_session=chat_session, message_history=message_history
        )

        await save_session_context(user_encryption_key, self.chat_id, chat_session, compressed_context)
        await close_chat_session(chat_session)

        logfire.info(f"Session {chat_session.session_id} closed due to inactivity.")

    @traced(extract_args=["chat_session", "include_context"])
    @db_retry()
    async def _prepare_conversation_input(
        self, user_encryption_key: str, *, chat_session: Sessions, include_context: bool = True
    ) -> tuple[list[pydantic_ai.messages.ModelMessage], str | None]:
        """Prepare the conversation input for the chat session.
        This method gathers the message history and checks for unsupported media types.
        Returns:
            tuple: A tuple containing the message history and any special instructions to the user.
        """
        async with async_database() as db_conn:
            message_history = []

            if include_context:
                # Gather chat context
                last_context = await Context.retrieve_context_by_chat(
                    db_conn, user_encryption_key, chat_id=self.chat_id, ctype="session"
                )
                if last_context:
                    last_context.sort(key=lambda c: c.created_at)

                    last_context = last_context or []
                    message_history.extend([context_to_model_message(c) for c in last_context])

            # Get all messages from the session
            media_instruction = None
            unsupported_media_types = []

            raw_messages = await chat_session.get_messages(db_conn)
            messages = [msg.to_telegram_object(user_encryption_key) for msg in raw_messages]
            messages.sort(key=lambda msg: msg.date)  # Sort messages by date

            for msg in messages:
                if isinstance(msg, telegram.Message):
                    media = await MediaFiles.get_by_message_id(
                        db_conn, user_encryption_key, chat_id=self.chat_id, message_id=str(msg.message_id)
                    )
                    user = msg.from_user.id
                elif isinstance(msg, telegram.MessageReactionUpdated):
                    media = []
                    user = msg.user.id

                as_model_message = telegram_message_to_model_message(
                    message=msg,
                    media=media,
                    ts_reference=self._run_timestamp,
                    is_user=user != self._bot_id,
                )
                message_history.append(as_model_message)

                if media:
                    unsupported_media = [m for m in media if not m.is_anthropic_supported]
                    unsupported_media_types.extend([
                        m.mime_type for m in unsupported_media if not m.mime_type.startswith("audio/")
                    ])

            if len(unsupported_media_types) == 1:
                media_instruction = (
                    f"The user sent a {unsupported_media_types[0]} file, but you can only view images and PDFs."
                )
            elif len(unsupported_media_types) > 1:
                media_instruction = (
                    f"The user sent {', '.join(unsupported_media_types)} files, but you can only view images and PDFs."
                )

            return message_history, media_instruction

    async def _execute_text_response(
        self, context: ContextTypes.DEFAULT_TYPE, response: TextResponse
    ) -> telegram.Message | None:
        """
        Send a text response to the chat.
        """
        if response.reply_to_message_id:
            reply_parameters = telegram.ReplyParameters(
                message_id=int(response.reply_to_message_id),
                allow_sending_without_reply=True,
            )
        else:
            reply_parameters = None

        try:
            reply_message = await context.bot.send_message(
                chat_id=int(self.chat_id),
                text=response.message_text,
                reply_parameters=reply_parameters,
            )
        except Exception:
            logfire.exception(f"Failed to send text reply to chat {self.chat_id}")
            raise

        return reply_message

    async def _execute_reaction_response(
        self, context: ContextTypes.DEFAULT_TYPE, response: ReactionResponse, message: telegram.Message
    ):
        try:
            react_sent = await context.bot.set_message_reaction(
                chat_id=int(self.chat_id),
                message_id=int(response.react_to_message_id),
                reaction=response.emoji,
            )

        except Exception:
            logfire.exception(
                f"Failed to send reaction to message {response.react_to_message_id} in chat {self.chat_id}"
            )
            raise

        else:
            if react_sent:
                # Manually create MessageReactionUpdated object as Telegram API does not return it
                reaction_message = telegram.MessageReactionUpdated(
                    chat=message.chat,
                    message_id=int(response.react_to_message_id),
                    date=datetime.now(UTC),
                    old_reaction=(),
                    new_reaction=(telegram.ReactionTypeEmoji(emoji=response.emoji),),
                    user=await context.bot.get_me(),
                )
                return reaction_message

        return None

    async def _compress_session_context(
        self, chat_session: Sessions, message_history: list[pydantic_ai.messages.ModelMessage]
    ) -> ContextTemplate:
        """
        Compress the session context for this chat.
        """

        context_run_payload = None

        try:
            context_run_payload = await run_agent_with_tracking(
                context_compression_agent,
                chat_id=self.chat_id,
                session_id=chat_session.session_id,
                run_kwargs={
                    "message_history": message_history,
                },
            )

            context_report: ContextTemplate = context_run_payload.output

        except Exception:
            logfire.exception(
                f"Failed to compress context for chat {self.chat_id} with session key {chat_session.session_key}."
            )

        else:
            return context_report
