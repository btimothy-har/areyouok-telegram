import asyncio
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Any

import logfire
import telegram

from areyouok_telegram.config import CHAT_SESSION_TIMEOUT_MINS
from areyouok_telegram.data import ChatEvent
from areyouok_telegram.data import Chats
from areyouok_telegram.data import Context
from areyouok_telegram.data import ContextType
from areyouok_telegram.data import GuidedSessionType
from areyouok_telegram.data import MediaFiles
from areyouok_telegram.data import Messages
from areyouok_telegram.data import MessageTypes
from areyouok_telegram.data import Notifications
from areyouok_telegram.data import Sessions
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.jobs.exceptions import UserNotFoundForChatError
from areyouok_telegram.llms import run_agent_with_tracking
from areyouok_telegram.llms.chat import AgentResponse
from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import OnboardingAgentDependencies
from areyouok_telegram.llms.chat import ReactionResponse
from areyouok_telegram.llms.chat import TextResponse
from areyouok_telegram.llms.chat import TextWithButtonsResponse
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.llms.chat import onboarding_agent
from areyouok_telegram.llms.context_compression import ContextTemplate
from areyouok_telegram.llms.context_compression import context_compression_agent
from areyouok_telegram.logging import traced
from areyouok_telegram.utils import db_retry
from areyouok_telegram.utils import telegram_call


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
        self.chat_encryption_key: str | None = None

        self.active_session: Sessions | None = None

    @property
    def name(self) -> str:
        """Generate a consistent job name for this chat."""
        return f"conversation:{self.chat_id}"

    async def run_job(self) -> None:  # noqa: ARG002
        """Process conversation for this chat."""

        # Get user encryption key - this will fail for non-private chats
        try:
            self.chat_encryption_key = await self._get_chat_encryption_key()
        except UserNotFoundForChatError:
            with logfire.span(
                f"Stopping conversation job for chat {self.chat_id} - no user found.",
                _span_name="ConversationJob._run.no_user",
                _level="warning",
                chat_id=self.chat_id,
            ):
                await self.stop()
                return

        self.active_session = await data_operations.get_or_create_active_session(
            chat_id=self.chat_id,
            create_if_not_exists=False,
        )

        if not self.active_session:
            # If no active session is found, log a warning and stop the job
            # This can happen if the user submits a command without chatting
            with logfire.span(
                "Conversation job started without an active session.",
                _span_name="ConversationJob._run.active_session",
                _level="warning",
                chat_id=self.chat_id,
            ):
                await self.stop()

        elif self.active_session.has_bot_responded:
            # If the last user activity was more than an hour ago, stop the job
            reference_ts = self.active_session.last_user_activity or self.active_session.session_start
            inactivity_duration = self._run_timestamp - reference_ts

            if inactivity_duration > timedelta(minutes=CHAT_SESSION_TIMEOUT_MINS):
                with logfire.span(
                    f"Closing chat session {self.active_session.session_id} due to inactivity.",
                    _span_name="ConversationJob._run.close_session",
                    chat_id=self.chat_id,
                ):
                    context = await self._get_session_context()
                    if context:
                        logfire.warning(
                            "Context already exists for session, skipping compression.",
                            session_id=self.active_session.session_id,
                        )
                    else:
                        message_history = await self._get_chat_history()

                        if len(message_history) > 0:
                            compressed_context = await self.compress_session_context(
                                message_history=message_history,
                            )
                            await self._save_session_context(
                                ctype=ContextType.SESSION,
                                data=compressed_context.content,
                            )

                        else:
                            logfire.warning(
                                f"No messages found in chat session {self.active_session.session_id}, "
                                "nothing to compress."
                            )

                    await data_operations.close_chat_session(chat_session=self.active_session)
                    logfire.info(f"Session {self.active_session.session_id} closed due to inactivity.")

                    await self.stop()

        else:
            with logfire.span(
                f"Generating response in {self.active_session.session_id}.",
                _span_name="ConversationJob._run.respond",
                chat_id=self.chat_id,
            ):
                run_count = 0

                while True:
                    run_count += 1

                    await telegram_call(
                        self._run_context.bot.send_chat_action,
                        chat_id=int(self.chat_id),
                        action=telegram.constants.ChatAction.TYPING,
                    )

                    message_history, dependencies = await self.prepare_conversation_input(
                        include_context=True,
                    )
                    agent_response = await self.generate_response(
                        conversation_history=message_history,
                        dependencies=dependencies,
                    )

                    if agent_response.response_type == "SwitchPersonalityResponse":
                        response_message = await self.execute_response(response=agent_response)
                        dependencies.restricted_responses.add(
                            "switch_personality"
                        )  # Disable personality switching for this run
                        run_count = 0
                        continue

                    elif run_count <= 3:
                        self.active_session = await data_operations.get_or_create_active_session(
                            chat_id=str(self.chat_id),
                            create_if_not_exists=False,
                        )
                        if (
                            self.active_session.last_user_message
                            and self.active_session.last_user_message > self._run_timestamp
                        ):
                            self._run_timestamp = self.active_session.last_user_message
                            await self.apply_response_delay()
                            continue

                    response_message = await self.execute_response(response=agent_response)
                    break

                if response_message:
                    if agent_response.response_type in ["TextWithButtonsResponse"]:
                        reasoning = agent_response.reasoning + agent_response.context
                    else:
                        reasoning = agent_response.reasoning

                    # Log the bot's response message
                    await data_operations.new_session_event(
                        session=self.active_session,
                        message=response_message,
                        user_id=str(self._bot_id),
                        is_user=False,
                        reasoning=reasoning,
                    )

                    if dependencies.notification and isinstance(response_message, telegram.Message):
                        await self._mark_notification_completed(dependencies.notification)

                # Always log bot activity
                await self._log_bot_activity()

            await self.apply_response_delay()

    @traced(extract_args=["include_context"])
    async def prepare_conversation_input(
        self,
        *,
        include_context: bool = True,
    ) -> tuple[list[ChatEvent], ChatAgentDependencies | OnboardingAgentDependencies]:
        """Prepare the conversation input for the chat session.
        This method gathers the message history and checks for unsupported media types.
        Returns:
            tuple: A tuple containing the message history and any special instructions to the user.
        """
        message_history = []
        latest_personality_context = None

        # Check for active onboarding sessions linked to this chat session
        get_onboarding_session = await data_operations.get_or_create_guided_session(
            chat_id=self.chat_id,
            session=self.active_session,
            stype=GuidedSessionType.ONBOARDING,
            create_if_not_exists=False,
        )

        onboarding_session = get_onboarding_session if getattr(get_onboarding_session, "is_active", False) else None

        if include_context:
            # Gather chat context
            chat_context_items = await self._get_chat_context()

            message_history.extend([ChatEvent.from_context(c) for c in chat_context_items])
            latest_personality_context = next(
                (c for c in chat_context_items if c.type == ContextType.PERSONALITY.value), None
            )

        chat_history = await self._get_chat_history()
        message_history.extend(chat_history)

        # Get next notification for this chat
        notification = await self._get_next_notification()

        deps_data = {
            "tg_context": self._run_context,
            "tg_chat_id": self.chat_id,
            "tg_session_id": self.active_session.session_id,
            "notification": notification,
        }

        if onboarding_session:
            deps_data["onboarding_session_key"] = onboarding_session.guided_session_key
            deps = OnboardingAgentDependencies(**deps_data)

        else:
            if latest_personality_context:
                latest_personality_context.decrypt_content(chat_encryption_key=self.chat_encryption_key)
                chat_personality = (
                    latest_personality_context.content.get("personality", "exploration")
                    if isinstance(latest_personality_context.content, dict)
                    else "exploration"
                )
            else:
                chat_personality = "exploration"

            deps_data["personality"] = chat_personality
            deps = ChatAgentDependencies(**deps_data)

        message_history.sort(key=lambda x: x.timestamp)

        deps.restricted_responses = self._check_restricted_responses(message_history, deps)

        return message_history, deps

    @traced(extract_args=False)
    async def generate_response(
        self,
        *,
        conversation_history: list[ChatEvent],
        dependencies: ChatAgentDependencies | OnboardingAgentDependencies,
    ) -> AgentResponse:
        """Process messages for this chat and send appropriate replies.

        Returns:
            AgentResponse: The response generated by the chat agent, or None if an error occurred.
        """

        agent_run_payload = None
        agent_run_time = datetime.now(UTC)

        agent = onboarding_agent if isinstance(dependencies, OnboardingAgentDependencies) else chat_agent

        agent_run_payload = await run_agent_with_tracking(
            agent,
            chat_id=self.chat_id,
            session_id=self.active_session.session_id,
            run_kwargs={
                "message_history": [
                    c.to_model_message(str(self._bot_id), agent_run_time) for c in conversation_history
                ],
                "deps": dependencies,
            },
        )

        agent_response: AgentResponse = agent_run_payload.output

        return agent_response

    @traced(extract_args=False)
    async def compress_session_context(self, message_history: list[ChatEvent]) -> ContextTemplate:
        """
        Compress the session context for this chat.
        """

        message_history.sort(key=lambda x: x.timestamp)
        agent_run_time = datetime.now(UTC)

        context_run_payload = await run_agent_with_tracking(
            context_compression_agent,
            chat_id=self.chat_id,
            session_id=self.active_session.session_id,
            run_kwargs={
                "message_history": [c.to_model_message(str(self._bot_id), agent_run_time) for c in message_history],
            },
        )

        context_report: ContextTemplate = context_run_payload.output
        return context_report

    async def apply_response_delay(self):
        user_metadata = await self._get_user_metadata()
        response_delay = getattr(user_metadata, "response_wait_time", 0) if user_metadata else 2
        if response_delay > 0:
            await asyncio.sleep(response_delay)

    @traced(extract_args=["response"], record_return=True)
    async def execute_response(
        self,
        *,
        response: AgentResponse,
    ) -> MessageTypes | None:
        """Execute the response action in the given context."""

        response_message = None

        if response.response_type in ["TextResponse", "TextWithButtonsResponse", "KeyboardResponse"]:
            response_message = await self._execute_text_response(response=response)

        elif response.response_type == "ReactionResponse":
            # Get the message to react to
            async with async_database() as db_conn:
                message, _ = await Messages.retrieve_message_by_id(
                    db_conn,
                    message_id=response.react_to_message_id,
                    chat_id=self.chat_id,
                    include_reactions=False,
                )

            if not message:
                logfire.warning(
                    f"Message {response.react_to_message_id} not found in chat {self.chat_id}, skipping reaction."
                )
                return

            # Decrypt the message to get the telegram object
            message.decrypt(self.chat_encryption_key)
            telegram_message = message.telegram_object

            response_message = await self._execute_reaction_response(response=response, message=telegram_message)

        elif response.response_type == "SwitchPersonalityResponse":
            await self._save_session_context(
                ctype=ContextType.PERSONALITY,
                data={
                    "personality": response.personality,
                    "reasoning": response.reasoning,
                },
            )

        elif response.response_type == "DoNothingResponse":
            await self._save_session_context(
                ctype=ContextType.RESPONSE,
                data={
                    "reasoning": response.reasoning,
                },
            )

        logfire.info(f"Response executed in chat {self.chat_id}: {response.response_type}.")
        return response_message

    async def _execute_text_response(self, response: TextResponse | TextWithButtonsResponse) -> telegram.Message | None:
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

        if response.response_type == "TextWithButtonsResponse":
            # Group buttons into rows based on buttons_per_row
            button_rows = []
            for i in range(0, len(response.buttons), response.buttons_per_row):
                row_buttons = [
                    telegram.InlineKeyboardButton(
                        text=btn.label,
                        callback_data=f"response::{btn.callback}",
                    )
                    for btn in response.buttons[i : i + response.buttons_per_row]
                ]
                button_rows.append(row_buttons)

            reply_markup = telegram.InlineKeyboardMarkup(inline_keyboard=button_rows)

        elif response.response_type == "KeyboardResponse":
            button_rows = []
            # If 3 or fewer buttons, arrange in single column (separate rows)
            if len(response.buttons) <= 3:
                for btn in response.buttons:
                    button_rows.append([telegram.KeyboardButton(text=btn.text)])
            else:
                # For more than 3 buttons, use 3-per-row layout
                for i in range(0, len(response.buttons), 3):
                    row_buttons = [telegram.KeyboardButton(text=btn.text) for btn in response.buttons[i : i + 3]]
                    button_rows.append(row_buttons)

            reply_markup = telegram.ReplyKeyboardMarkup(
                keyboard=button_rows,
                input_field_placeholder=response.tooltip_text,
                one_time_keyboard=True,
                resize_keyboard=True,
            )

        else:
            reply_markup = telegram.ReplyKeyboardRemove()

        reply_message = await telegram_call(
            self._run_context.bot.send_message,
            chat_id=int(self.chat_id),
            text=response.message_text,
            reply_parameters=reply_parameters,
            reply_markup=reply_markup,
        )

        return reply_message

    async def _execute_reaction_response(self, response: ReactionResponse, message: telegram.Message):
        react_sent = await telegram_call(
            self._run_context.bot.set_message_reaction,
            chat_id=int(self.chat_id),
            message_id=int(response.react_to_message_id),
            reaction=response.emoji,
        )

        if react_sent:
            bot_user = await telegram_call(self._run_context.bot.get_me)

            # Manually create MessageReactionUpdated object as Telegram API does not return it
            reaction_message = telegram.MessageReactionUpdated(
                chat=message.chat,
                message_id=int(response.react_to_message_id),
                date=datetime.now(UTC),
                old_reaction=(),
                new_reaction=(telegram.ReactionTypeEmoji(emoji=response.emoji),),
                user=bot_user,
            )
            return reaction_message

        return None

    @db_retry()
    async def _get_user_metadata(self) -> UserMetadata | None:
        """
        Get the user metadata for the chat.

        Returns:
            The user metadata, or None if no metadata exists
        """
        async with async_database() as db_conn:
            chat_obj = await UserMetadata.get_by_user_id(db_conn, user_id=self.chat_id)

            if not chat_obj:
                return None

            return chat_obj

    @db_retry()
    async def _get_chat_encryption_key(self) -> str:
        """
        Get the chat encryption key for the chat.

        Returns:
            The chat's encryption key

        Raises:
            UserNotFoundForChatError: If no chat is found (will be renamed to ChatNotFoundError later)
        """
        async with async_database() as db_conn:
            chat_obj = await Chats.get_by_id(db_conn, chat_id=self.chat_id)

            if not chat_obj:
                raise UserNotFoundForChatError(self.chat_id)

            return chat_obj.retrieve_key()

    @db_retry()
    async def _log_bot_activity(self) -> None:
        async with async_database() as db_conn:
            await self.active_session.new_activity(
                db_conn,
                timestamp=self._run_timestamp,
                is_user=False,  # This is a bot response
            )

    @db_retry()
    async def _save_session_context(self, *, ctype: ContextType, data: Any):
        """
        Create a session context for the given chat ID.
        If no session exists, create a new one.
        """
        async with async_database() as db_conn:
            await Context.new_or_update(
                db_conn,
                chat_encryption_key=self.chat_encryption_key,
                chat_id=self.chat_id,
                session_id=self.active_session.session_id,
                ctype=ctype.value,
                content=data,
            )

    @db_retry()
    async def _get_session_context(self) -> Context | None:
        async with async_database() as db_conn:
            context = await Context.get_by_session_id(
                db_conn,
                session_id=self.active_session.session_id,
                ctype="session",
            )
        return context

    @db_retry()
    async def _get_chat_context(self) -> list[Context]:
        chat_context = []

        async with async_database() as db_conn:
            chat_context_items = await Context.retrieve_context_by_chat(
                db_conn,
                chat_id=self.chat_id,
            )

            if chat_context_items:
                chat_context_items.sort(key=lambda c: c.created_at, reverse=True)

                # Historical conversation context - only include those created within the last 24 hours
                chat_context = [
                    c
                    for c in chat_context_items
                    if c.type == ContextType.SESSION.value and c.created_at >= (self._run_timestamp - timedelta(days=1))
                ]
                # Include all other context items for the session
                chat_context.extend([c for c in chat_context_items if c.session_id == self.active_session.session_id])

                # Decrypt all context items
                [c.decrypt_content(chat_encryption_key=self.chat_encryption_key) for c in chat_context]

        return chat_context

    @db_retry()
    async def _get_chat_history(self) -> list[ChatEvent]:
        message_history = []

        async with async_database() as db_conn:
            raw_messages = await self.active_session.get_messages(db_conn)

            # Filter messages to only those created before the run timestamp
            raw_messages = [msg for msg in raw_messages if msg.created_at <= self._run_timestamp]
            for msg in raw_messages:
                msg.decrypt(self.chat_encryption_key)

            for msg in raw_messages:
                if msg.message_type == "Message":
                    media = await MediaFiles.get_by_message_id(
                        db_conn,
                        chat_id=self.chat_id,
                        message_id=msg.message_id,
                    )
                elif msg.message_type == "MessageReactionUpdated":
                    media = []
                else:
                    continue  # Skip unknown message types

                if media:
                    [m.decrypt_content(chat_encryption_key=self.chat_encryption_key) for m in media]

                message_history.append(ChatEvent.from_message(msg, media))

        return message_history

    @db_retry()
    async def _get_next_notification(self) -> Notifications | None:
        """
        Get the next pending notification for a chat.

        Args:
            chat_id: The chat ID to get the next notification for

        Returns:
            The next pending notification, or None if no pending notifications exist
        """
        async with async_database() as db_conn:
            return await Notifications.get_next_pending(db_conn, chat_id=self.chat_id)

    @db_retry()
    async def _mark_notification_completed(self, notification: Notifications):
        async with async_database() as db_conn:
            await notification.mark_as_completed(db_conn)

    def _check_restricted_responses(
        self,
        message_history: list[ChatEvent],
        dependencies: ChatAgentDependencies | OnboardingAgentDependencies,
    ) -> set[str]:
        response_restrictions = dependencies.restricted_responses

        if isinstance(dependencies, ChatAgentDependencies):
            if "switch_personality" not in dependencies.restricted_responses:
                # Check if there's already a switch_personality event in the most recent 10 messages
                # If so, disable personality switching for this run
                recent_messages = message_history[-10:] if len(message_history) > 10 else message_history
                if any(event.event_type == "switch_personality" for event in recent_messages):
                    response_restrictions.add("switch_personality")

        # Restrict text responses if the bot has recently replied
        if (
            message_history
            and message_history[-1].event_type == "message"
            and message_history[-1].user_id == str(self._bot_id)
        ):
            response_restrictions.add("text")

        if "text" in response_restrictions and dependencies.notification:
            response_restrictions.remove("text")

        return set(response_restrictions)
