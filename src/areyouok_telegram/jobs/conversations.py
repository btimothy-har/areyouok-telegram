import asyncio
import random
from datetime import UTC, datetime, timedelta

import logfire
import telegram

from areyouok_telegram.config import CHAT_SESSION_TIMEOUT_MINS
from areyouok_telegram.data.models import (
    Chat,
    ChatEvent,
    Context,
    ContextType,
    GuidedSession,
    GuidedSessionType,
    MediaFile,
    Message,
    MessageTypes,
    Notification,
    Session,
    User,
    UserMetadata,
)
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.jobs.evaluations import EvaluationsJob
from areyouok_telegram.jobs.scheduler import run_job_once
from areyouok_telegram.llms import run_agent_with_tracking
from areyouok_telegram.llms.chat import (
    AgentResponse,
    ChatAgentDependencies,
    OnboardingAgentDependencies,
    ReactionResponse,
    TextResponse,
    TextWithButtonsResponse,
    chat_agent,
    onboarding_agent,
)
from areyouok_telegram.llms.chat.agents.journaling import JournalingAgentDependencies, journaling_agent
from areyouok_telegram.llms.context_compression import ContextTemplate, context_compression_agent
from areyouok_telegram.logging import traced
from areyouok_telegram.utils.retry import telegram_call


class UserNotFoundError(ValueError):
    """Raised when a user is not found for a chat."""

    def __init__(self, telegram_chat_id: int):
        super().__init__(f"User not found for chat {telegram_chat_id}")
        self.telegram_chat_id = telegram_chat_id


class ConversationJob(BaseJob):
    """
    A class-based job for handling conversations in a specific chat.

    This job:
    1. Fetches recent messages for a specific chat
    2. Processes messages and determines if a reply is needed
    3. Sends replies and saves them to the database
    """

    def __init__(self, chat_id: int):
        """
        Initialize the conversation job for a specific chat.

        Args:
            chat_id: Internal chat ID
        """
        super().__init__()
        self.chat_id = chat_id

    @property
    def name(self) -> str:
        """Generate a consistent job name for this chat."""
        return f"conversation:{self.chat_id}"

    async def run_job(self) -> None:
        """Process conversation for this chat."""

        # Get chat and encryption key
        chat = await Chat.get_by_id(chat_id=self.chat_id)
        if not chat:
            with logfire.span(
                f"Stopping conversation job for chat {self.chat_id} - chat not found.",
                _span_name="ConversationJob._run.no_chat",
                _level="warning",
                chat_id=self.chat_id,
            ):
                await self.stop()
                return

        # Get active session (don't create if it doesn't exist)
        active_sessions = await Session.get_sessions(chat=chat, active=True)
        active_session = active_sessions[0] if active_sessions else None

        if not active_session:
            # If no active session is found, log a warning and stop the job
            # This can happen if the user submits a command without chatting
            with logfire.span(
                "Conversation job started without an active session.",
                _span_name="ConversationJob._run.active_session",
                _level="warning",
                chat_id=self.chat_id,
            ):
                await self.stop()

        elif active_session.has_bot_responded:
            # If the last user activity was more than an hour ago, stop the job
            reference_ts = active_session.last_user_activity or active_session.session_start
            inactivity_duration = self._run_timestamp - reference_ts

            if inactivity_duration > timedelta(minutes=CHAT_SESSION_TIMEOUT_MINS):
                context = await Context.get_by_chat(
                    chat=chat,
                    session=active_session,
                    ctype=ContextType.SESSION.value,
                )
                message_history = []  # Initialize message_history before conditional logic
                if context:
                    logfire.warning(
                        "Context already exists for session, skipping compression.",
                        session_id=active_session.id,
                    )
                else:
                    with logfire.span(
                        f"Compressing conversation history for session {active_session.id}.",
                        _span_name="ConversationJob._run.compress_context",
                        chat_id=self.chat_id,
                        session_id=active_session.id,
                    ):
                        message_history = await self._get_chat_history(chat=chat, active_session=active_session)

                        if len(message_history) > 0:
                            compressed_context = await self.compress_session_context(
                                chat=chat,
                                active_session=active_session,
                                message_history=message_history,
                            )
                            context = Context(
                                chat=chat,
                                session_id=active_session.id,
                                type=ContextType.SESSION.value,
                                content=compressed_context.content,
                            )
                            await context.save()

                        else:
                            logfire.warning(
                                f"No messages found in chat session {active_session.id}, nothing to compress."
                            )

                # Check if we should run evaluations (only if we actually got message history)
                if len(message_history) > 5:
                    await run_job_once(
                        context=self._run_context,
                        job=EvaluationsJob(
                            chat_id=self.chat_id,
                            session_id=active_session.id,
                        ),
                        when=datetime.now(UTC) + timedelta(seconds=10),
                    )

                # Always close session and stop job when inactive, regardless of context existence
                # Check for any active guided sessions and inactivate them
                guided_sessions = await GuidedSession.get_by_chat(chat=chat, session=active_session)
                if guided_sessions:
                    for s in [gs for gs in guided_sessions if gs.is_active]:
                        await s.inactivate()

                await active_session.close_session(timestamp=self._run_timestamp)
                logfire.info(f"Session {active_session.id} closed due to inactivity.")

                await self.stop()

        else:
            with logfire.span(
                f"Generating response in {active_session.id}.",
                _span_name="ConversationJob._run.respond",
                chat_id=self.chat_id,
            ):
                run_count = 0
                persistent_restrictions: set[str] = set()  # Track restrictions across loop iterations

                while True:
                    run_count += 1

                    await telegram_call(
                        self._run_context.bot.send_chat_action,
                        chat_id=chat.telegram_chat_id,
                        action=telegram.constants.ChatAction.TYPING,
                    )

                    message_history, dependencies = await self.prepare_conversation_input(
                        chat=chat,
                        active_session=active_session,
                        include_context=True,
                    )

                    # Apply persistent restrictions from previous iterations
                    dependencies.restricted_responses.update(persistent_restrictions)

                    # Generate response - select appropriate agent based on dependency type
                    agent_run_time = datetime.now(UTC)
                    if isinstance(dependencies, JournalingAgentDependencies):
                        agent = journaling_agent
                    elif isinstance(dependencies, OnboardingAgentDependencies):
                        agent = onboarding_agent
                    else:
                        agent = chat_agent

                    agent_run_payload = await run_agent_with_tracking(
                        agent,
                        chat=chat,
                        session=active_session,
                        run_kwargs={
                            "message_history": [
                                c.to_model_message(self._bot_id, agent_run_time) for c in message_history
                            ],
                            "deps": dependencies,
                        },
                    )

                    agent_response: AgentResponse = agent_run_payload.output

                    if agent_response.response_type == "SwitchPersonalityResponse":
                        response_message = await self.execute_response(
                            chat=chat,
                            active_session=active_session,
                            response=agent_response,
                        )
                        # Disable personality switching for subsequent iterations
                        persistent_restrictions.add("switch_personality")
                        run_count = 0
                        continue

                    elif run_count <= 3:
                        # Re-fetch active session to check for new messages
                        active_session = await Session.get_by_id(session_id=active_session.id)
                        if (
                            active_session
                            and active_session.last_user_message
                            and active_session.last_user_message > self._run_timestamp
                        ):
                            self._run_timestamp = active_session.last_user_message
                            await self.apply_response_delay(chat=chat)
                            continue

                    response_message = await self.execute_response(
                        chat=chat,
                        active_session=active_session,
                        response=agent_response,
                    )
                    break

                if response_message:
                    if agent_response.response_type in ["TextWithButtonsResponse"]:
                        reasoning = agent_response.reasoning + agent_response.context
                    else:
                        reasoning = agent_response.reasoning

                    # Get bot user (for bot-generated messages)
                    bot_user = await User.get_by_id(telegram_user_id=self._bot_id)

                    # Log the bot's response message
                    message_obj = Message.from_telegram(
                        user_id=bot_user.id,
                        chat=chat,
                        message=response_message,
                        session_id=active_session.id,
                        reasoning=reasoning,
                    )
                    await message_obj.save()

                    # Update session activity
                    if isinstance(response_message, telegram.Message):
                        if response_message.date >= active_session.session_start:
                            await active_session.new_message(timestamp=response_message.date, is_user=False)
                    elif isinstance(response_message, telegram.MessageReactionUpdated):
                        if response_message.date >= active_session.session_start:
                            await active_session.new_activity(timestamp=response_message.date, is_user=False)

                    if dependencies.notification and isinstance(response_message, telegram.Message):
                        await dependencies.notification.mark_as_completed()

                # Always log bot activity
                await active_session.new_activity(
                    timestamp=self._run_timestamp,
                    is_user=False,  # This is a bot response
                )

            await self.apply_response_delay(chat=chat)

    @traced(extract_args=["include_context"])
    async def prepare_conversation_input(
        self,
        *,
        chat: Chat,
        active_session: Session,
        include_context: bool = True,
    ) -> tuple[list[ChatEvent], ChatAgentDependencies | OnboardingAgentDependencies | JournalingAgentDependencies]:
        """Prepare the conversation input for the chat session.
        This method gathers the message history and checks for unsupported media types.
        Returns:
            tuple: A tuple containing the message history and any special instructions to the user.
        """
        message_history = []
        latest_personality_context = None

        # Check for active guided sessions linked to this chat session (priority over onboarding/chat)
        all_guided_sessions = await GuidedSession.get_by_chat(chat=chat, session=active_session)
        active_guided_sessions = [s for s in all_guided_sessions if s.is_active]

        if active_guided_sessions:
            if any(s.session_type == GuidedSessionType.JOURNALING.value for s in active_guided_sessions):
                guided_session = next(
                    s for s in active_guided_sessions if s.session_type == GuidedSessionType.JOURNALING.value
                )

            elif any(s.session_type == GuidedSessionType.ONBOARDING.value for s in active_guided_sessions):
                guided_session = next(
                    s for s in active_guided_sessions if s.session_type == GuidedSessionType.ONBOARDING.value
                )
            else:
                guided_session = None
        else:
            guided_session = None

        if include_context and not guided_session:
            # Gather chat context - fetch all context for this chat
            all_context_items = await Context.get_by_chat(chat=chat)

            if all_context_items:
                all_context_items.sort(key=lambda c: c.created_at, reverse=True)

                # Historical conversation context - only include those created within the last 24 hours
                chat_context_items = [
                    c
                    for c in all_context_items
                    if c.type == ContextType.SESSION.value and c.created_at >= (self._run_timestamp - timedelta(days=1))
                ]
                # Include all other context items for the session
                chat_context_items.extend([c for c in all_context_items if c.session_id == active_session.id])

                message_history.extend([ChatEvent.from_context(c) for c in chat_context_items])
                latest_personality_context = next(
                    (c for c in chat_context_items if c.type == ContextType.PERSONALITY.value), None
                )
            else:
                latest_personality_context = None

        chat_history = await self._get_chat_history(chat=chat, active_session=active_session)
        message_history.extend(chat_history)

        # Get next notification for this chat
        notification = await Notification.get_next_pending(chat=chat)

        # Get user for the chat
        user = await User.get_by_id(telegram_user_id=chat.telegram_chat_id)
        if not user:
            raise UserNotFoundError(chat.telegram_chat_id)

        deps_data = {
            "bot_id": self._bot_id,
            "user": user,
            "chat": chat,
            "session": active_session,
            "notification": notification,
        }

        if guided_session and guided_session.session_type == GuidedSessionType.JOURNALING.value:
            # Journaling session takes priority
            deps_data["journaling_session"] = guided_session
            deps = JournalingAgentDependencies(**deps_data)

        elif guided_session and guided_session.session_type == GuidedSessionType.ONBOARDING.value:
            deps_data["onboarding_session"] = guided_session
            deps = OnboardingAgentDependencies(**deps_data)

        else:
            if latest_personality_context:
                chat_personality = (
                    latest_personality_context.content.get("personality", "companionship")
                    if isinstance(latest_personality_context.content, dict)
                    else "companionship"
                )
            else:
                chat_personality = random.choices(["companionship", "exploration"], weights=[0.4, 0.6], k=1)[0]

            deps_data["personality"] = chat_personality
            deps = ChatAgentDependencies(**deps_data)

        message_history.sort(key=lambda x: x.timestamp)

        # Check restricted responses
        response_restrictions = deps.restricted_responses

        if isinstance(deps, ChatAgentDependencies):
            if "switch_personality" not in deps.restricted_responses:
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

        if "text" in response_restrictions and deps.notification:
            response_restrictions.remove("text")

        deps.restricted_responses = set(response_restrictions)

        return message_history, deps

    @traced(extract_args=False)
    async def compress_session_context(
        self,
        *,
        chat: Chat,
        active_session: Session,
        message_history: list[ChatEvent],
    ) -> ContextTemplate:
        """
        Compress the session context for this chat.
        """

        message_history.sort(key=lambda x: x.timestamp)
        agent_run_time = datetime.now(UTC)

        context_run_payload = await run_agent_with_tracking(
            context_compression_agent,
            chat=chat,
            session=active_session,
            run_kwargs={
                "message_history": [c.to_model_message(self._bot_id, agent_run_time) for c in message_history],
            },
        )

        context_report: ContextTemplate = context_run_payload.output
        return context_report

    async def apply_response_delay(self, *, chat: Chat):
        # For private chats, telegram_chat_id == telegram_user_id
        user = await User.get_by_id(telegram_user_id=chat.telegram_chat_id)
        if user:
            user_metadata = await UserMetadata.get_by_user_id(user_id=user.id)
            response_delay = user_metadata.response_wait_time if user_metadata else 2
        else:
            response_delay = 2

        if response_delay > 0:
            await asyncio.sleep(response_delay)

    @traced(extract_args=["response"], record_return=True)
    async def execute_response(
        self,
        *,
        chat: Chat,
        active_session: Session,
        response: AgentResponse,
    ) -> MessageTypes | None:
        """Execute the response action in the given context."""

        response_message = None

        if response.response_type in ["TextResponse", "TextWithButtonsResponse", "KeyboardResponse"]:
            response_message = await self._execute_text_response(chat=chat, response=response)

        elif response.response_type == "ReactionResponse":
            # Get the message to react to
            message = await Message.get_by_id(
                chat=chat,
                telegram_message_id=response.react_to_message_id,
            )

            if not message:
                logfire.warning(
                    f"Message {response.react_to_message_id} not found in chat {self.chat_id}, skipping reaction."
                )
                return

            telegram_message = message.telegram_object

            response_message = await self._execute_reaction_response(
                chat=chat, response=response, message=telegram_message
            )

        elif response.response_type == "SwitchPersonalityResponse":
            context = Context(
                chat=chat,
                session_id=active_session.id,
                type=ContextType.PERSONALITY.value,
                content={
                    "personality": response.personality,
                    "reasoning": response.reasoning,
                },
            )
            await context.save()

        elif response.response_type == "DoNothingResponse":
            context = Context(
                chat=chat,
                session_id=active_session.id,
                type=ContextType.RESPONSE.value,
                content={
                    "reasoning": response.reasoning,
                },
            )
            await context.save()

        logfire.info(f"Response executed in chat {self.chat_id}: {response.response_type}.")
        return response_message

    async def _execute_text_response(
        self, *, chat: Chat, response: TextResponse | TextWithButtonsResponse
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
            # If 5 or fewer buttons, arrange in single column (separate rows)
            if len(response.buttons) <= 5:
                for btn in response.buttons:
                    button_rows.append([telegram.KeyboardButton(text=btn.text)])
            else:
                # For more than 5 buttons, use 3-per-row layout
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
            chat_id=chat.telegram_chat_id,
            text=response.message_text,
            reply_parameters=reply_parameters,
            reply_markup=reply_markup,
        )

        return reply_message

    async def _execute_reaction_response(self, *, chat: Chat, response: ReactionResponse, message: telegram.Message):
        react_sent = await telegram_call(
            self._run_context.bot.set_message_reaction,
            chat_id=chat.telegram_chat_id,
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

    async def _get_chat_history(self, *, chat: Chat, active_session: Session) -> list[ChatEvent]:
        message_history = []

        # Get messages for this session (auto-decrypted)
        raw_messages = await Message.get_by_session(chat=chat, session_id=active_session.id)

        # Filter messages to only those created before the run timestamp
        raw_messages = [msg for msg in raw_messages if msg.created_at <= self._run_timestamp]

        for msg in raw_messages:
            if msg.message_type == "Message":
                media = await MediaFile.get_by_message(chat=chat, message_id=msg.id)
            elif msg.message_type == "MessageReactionUpdated":
                media = []
            else:
                continue  # Skip unknown message types

            message_history.append(ChatEvent.from_message(msg, media))

        return message_history
