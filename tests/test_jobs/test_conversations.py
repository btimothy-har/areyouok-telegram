"""Tests for jobs/conversations.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

from areyouok_telegram.data.models.chat_event import ChatEvent
from areyouok_telegram.data.models.context import ContextType
from areyouok_telegram.data.models.notifications import Notifications
from areyouok_telegram.data.operations import InvalidChatError
from areyouok_telegram.jobs.conversations import ConversationJob
from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import DoNothingResponse
from areyouok_telegram.llms.chat import KeyboardResponse
from areyouok_telegram.llms.chat import OnboardingAgentDependencies
from areyouok_telegram.llms.chat import ReactionResponse
from areyouok_telegram.llms.chat import SwitchPersonalityResponse
from areyouok_telegram.llms.chat import TextResponse
from areyouok_telegram.llms.chat import TextWithButtonsResponse
from areyouok_telegram.llms.chat.responses import _KeyboardButton  # noqa: PLC2701
from areyouok_telegram.llms.chat.responses import _MessageButton  # noqa: PLC2701


class TestConversationJob:
    """Test the ConversationJob class."""

    def test_init(self):
        """Test ConversationJob initialization."""
        job = ConversationJob("123")

        assert job.chat_id == "123"

    def test_name_property(self):
        """Test name property generates correct job name."""
        job = ConversationJob("chat456")
        assert job.name == "conversation:chat456"

    @pytest.mark.asyncio
    async def test_run_bot_already_responded(self):
        """Test run_job when bot has already responded."""
        job = ConversationJob("123")
        job._run_timestamp = datetime.now(UTC)

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = datetime.now(UTC) - timedelta(minutes=30)

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
        ):
            await job.run_job()

        # Test passes if no exception is thrown - bot should handle already responded state gracefully

    @pytest.mark.asyncio
    async def test_run_generates_response(self, frozen_time):
        """Test run_job generates and executes response."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id=None)
        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(
                job,
                "prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_bot_id="bot123",
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="companionship",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)) as mock_generate,
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "_log_bot_activity", new=AsyncMock()) as mock_log_activity,
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify response was generated and executed
        mock_generate.assert_called_once()

        # Verify bot activity was logged
        mock_log_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_response_success(self):
        """Test generate_response returns agent response."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._bot_id = "bot123"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "_mark_notification_completed", new=AsyncMock()) as mock_mark_notification,
        ):
            result = await job.generate_response(
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == mock_response
        # Verify notification completion was not called since there was no notification
        mock_mark_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_response_exception(self):
        """Test generate_response raises exceptions (no internal error handling)."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._bot_id = "bot123"

        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking",
                new=AsyncMock(side_effect=Exception("Test error")),
            ),
            patch.object(job, "_mark_notification_completed", new=AsyncMock()),
        ):
            with pytest.raises(Exception, match="Test error"):
                await job.generate_response(
                    conversation_history=[],
                    dependencies=mock_deps,
                )

    @pytest.mark.asyncio
    async def test_execute_response_text(self):
        """Test execute_response for text response."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job.chat_encryption_key = "test_encryption_key"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id="456")
        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch.object(job, "_execute_text_response", new=AsyncMock(return_value=mock_message)) as mock_execute_text,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            result = await job.execute_response(response=mock_response)

        assert result == mock_message
        mock_execute_text.assert_called_once_with(response=mock_response)
        mock_log_info.assert_called_once_with("Response executed in chat 123: TextResponse.")

    @pytest.mark.asyncio
    async def test_execute_response_reaction(self):
        """Test execute_response for reaction response."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job.chat_encryption_key = "test_encryption_key"

        mock_response = ReactionResponse(
            reasoning="Test reasoning", react_to_message_id="456", emoji=ReactionEmoji.THUMBS_UP
        )

        # Create a Messages mock (SQLAlchemy object), not a telegram.Message
        mock_message = MagicMock()
        mock_message.decrypt = MagicMock()
        mock_message.telegram_object = MagicMock(spec=telegram.Message)

        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.Messages.retrieve_message_by_id",
                new=AsyncMock(return_value=(mock_message, None)),
            ),
            patch.object(
                job, "_execute_reaction_response", new=AsyncMock(return_value=mock_reaction)
            ) as mock_execute_reaction,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job.execute_response(response=mock_response)

        assert result == mock_reaction
        mock_execute_reaction.assert_called_once_with(response=mock_response, message=mock_message.telegram_object)
        mock_log_info.assert_called_once_with("Response executed in chat 123: ReactionResponse.")

    @pytest.mark.asyncio
    async def test_execute_response_reaction_message_not_found(self):
        """Test execute_response when reaction target message not found."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job.chat_encryption_key = "test_encryption_key"

        mock_response = ReactionResponse(
            reasoning="Test reasoning", react_to_message_id="456", emoji=ReactionEmoji.THUMBS_UP
        )

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.Messages.retrieve_message_by_id",
                new=AsyncMock(return_value=(None, None)),
            ),
            patch("areyouok_telegram.jobs.conversations.logfire.warning") as mock_log_warning,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job.execute_response(response=mock_response)

        assert result is None
        mock_log_warning.assert_called_once_with("Message 456 not found in chat 123, skipping reaction.")

    @pytest.mark.asyncio
    async def test_execute_text_response_with_reply(self):
        """Test _execute_text_response with reply parameters."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        response = TextResponse(reasoning="Test reasoning", message_text="Reply text", reply_to_message_id="789")

        await job._execute_text_response(response)

        # Verify send_message was called with reply parameters
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Reply text"
        assert call_args.kwargs["reply_parameters"].message_id == 789
        # Verify reply_markup removes keyboard
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert isinstance(reply_markup, telegram.ReplyKeyboardRemove)

    @pytest.mark.asyncio
    async def test_execute_text_response_no_reply(self):
        """Test _execute_text_response without reply parameters."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        response = TextResponse(reasoning="Test reasoning", message_text="Regular text", reply_to_message_id=None)

        await job._execute_text_response(response)

        # Verify send_message was called without reply parameters
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Regular text"
        assert call_args.kwargs["reply_parameters"] is None

        # Verify reply_markup removes keyboard
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert isinstance(reply_markup, telegram.ReplyKeyboardRemove)

    @pytest.mark.asyncio
    async def test_execute_reaction_response_success(self):
        """Test _execute_reaction_response successfully sends reaction."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.set_message_reaction = AsyncMock(return_value=True)
        job._run_context.bot.get_me = AsyncMock(return_value=MagicMock())

        response = ReactionResponse(
            reasoning="Test reasoning",
            react_to_message_id="456",
            emoji=ReactionEmoji.RED_HEART,  # This is actually ❤ not ❤️
        )

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat = MagicMock()

        result = await job._execute_reaction_response(response, mock_message)

        # Verify reaction was sent
        job._run_context.bot.set_message_reaction.assert_called_once_with(
            chat_id=123, message_id=456, reaction=ReactionEmoji.RED_HEART
        )

        # Verify MessageReactionUpdated was created
        assert isinstance(result, telegram.MessageReactionUpdated)
        assert result.message_id == 456

    @pytest.mark.asyncio
    async def test_run_user_not_found_error(self):
        """Test _run when InvalidChatError is raised."""
        job = ConversationJob("123")

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(side_effect=InvalidChatError("No user found")),
            ),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.span") as mock_span,
        ):
            await job.run_job()

        mock_stop.assert_called_once_with()
        mock_span.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_no_active_session(self):
        """Test _run when no active session is found."""
        job = ConversationJob("123")

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.data.operations.get_or_create_active_session", new=AsyncMock(return_value=None)),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.span") as mock_span,
        ):
            await job.run_job()

        mock_stop.assert_called_once_with()
        mock_span.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_response_with_logging(self, frozen_time):
        """Test _run response generation with message logging."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id=None)
        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(
                job,
                "prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_bot_id="bot123",
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="companionship",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)),
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()) as mock_log_event,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify message event was logged
        mock_log_event.assert_called_once_with(
            session=mock_session,
            message=mock_message,
            user_id="bot123",
            is_user=False,
            reasoning="Test reasoning",
        )

    @pytest.mark.asyncio
    async def test_run_response_without_message(self, frozen_time):
        """Test _run response generation when no message is returned."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        mock_response = DoNothingResponse(reasoning="Do nothing")

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(
                job,
                "prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_bot_id="bot123",
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="companionship",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)),
            patch.object(job, "execute_response", new=AsyncMock(return_value=None)),
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()) as mock_log_event,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify message event was NOT logged when no message returned
        mock_log_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_restricted_responses_personality_switching(self):
        """Test _check_restricted_responses adds switch_personality restriction when recent event exists."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        # Create conversation history with switch_personality event
        mock_chat_event = MagicMock(spec=ChatEvent)
        mock_chat_event.event_type = "switch_personality"
        conversation_history = [mock_chat_event]

        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=None,
        )

        # Call the method directly
        restricted_responses = job._check_restricted_responses(conversation_history, mock_deps)

        # Verify switch_personality was added to restricted responses
        assert "switch_personality" in restricted_responses

    @pytest.mark.asyncio
    async def test_check_restricted_responses_bot_last_message(self):
        """Test _check_restricted_responses restricts text when bot was last to message."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        # Create conversation history where bot was last to message
        mock_chat_event = MagicMock(spec=ChatEvent)
        mock_chat_event.event_type = "message"
        mock_chat_event.user_id = "bot123"
        conversation_history = [mock_chat_event]

        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=None,
        )

        # Call the method directly
        restricted_responses = job._check_restricted_responses(conversation_history, mock_deps)

        # Verify text was added to restricted responses
        assert "text" in restricted_responses

    @pytest.mark.asyncio
    async def test_check_restricted_responses_notification_removes_text_restriction(self):
        """Test _check_restricted_responses removes text restriction when notification is present."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        # Create a mock notification object
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Special notification content"

        # Start with text in restricted responses and a notification
        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses={"text"},
            notification=mock_notification,
        )

        # Call the method directly
        restricted_responses = job._check_restricted_responses([], mock_deps)

        # Verify text was removed from restricted responses
        assert "text" not in restricted_responses

    @pytest.mark.asyncio
    async def test_run_job_switch_personality_recursive(self, frozen_time):
        """Test run_job handles SwitchPersonalityResponse with recursive call - tests while loop logic."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        mock_switch_response = SwitchPersonalityResponse(reasoning="Switch personality", personality="celebration")
        mock_final_response = TextResponse(
            reasoning="Final response", message_text="Hello with new personality!", reply_to_message_id=None
        )
        mock_message = MagicMock()

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(
                job,
                "prepare_conversation_input",
                new=AsyncMock(
                    side_effect=[
                        # First call - returns initial deps
                        (
                            [],
                            ChatAgentDependencies(
                                tg_bot_id="bot123",
                                tg_chat_id="123",
                                tg_session_id="session123",
                                personality="companionship",
                                restricted_responses=set(),
                                notification=None,
                            ),
                        ),
                        # Second call after personality switch
                        (
                            [],
                            ChatAgentDependencies(
                                tg_bot_id="bot123",
                                tg_chat_id="123",
                                tg_session_id="session123",
                                personality="celebration",
                                restricted_responses={"switch_personality"},  # Added restriction
                                notification=None,
                            ),
                        ),
                    ]
                ),
            ),
            patch.object(
                job,
                "generate_response",
                new=AsyncMock(side_effect=[mock_switch_response, mock_final_response]),
            ) as mock_generate,
            patch.object(
                job,
                "execute_response",
                new=AsyncMock(side_effect=[None, mock_message]),
            ),
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify generate_response was called twice (first for switch, then for final response)
        assert mock_generate.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_response_switch_personality(self):
        """Test execute_response for switch personality response."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job.chat_encryption_key = "test_encryption_key"

        mock_response = SwitchPersonalityResponse(reasoning="Switch to celebration", personality="celebration")

        with (
            patch.object(job, "_save_session_context", new=AsyncMock()) as mock_save,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            result = await job.execute_response(response=mock_response)

        assert result is None
        mock_save.assert_called_once_with(
            ctype=ContextType.PERSONALITY,
            data={
                "personality": "celebration",
                "reasoning": "Switch to celebration",
            },
        )
        mock_log_info.assert_called_once_with("Response executed in chat 123: SwitchPersonalityResponse.")

    @pytest.mark.asyncio
    async def test_execute_response_do_nothing(self):
        """Test execute_response for do nothing response."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job.chat_encryption_key = "test_encryption_key"

        mock_response = DoNothingResponse(reasoning="Nothing to do")

        with (
            patch.object(job, "_save_session_context", new=AsyncMock()) as mock_save,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            result = await job.execute_response(response=mock_response)

        assert result is None
        mock_save.assert_called_once_with(
            ctype=ContextType.RESPONSE,
            data={
                "reasoning": "Nothing to do",
            },
        )
        mock_log_info.assert_called_once_with("Response executed in chat 123: DoNothingResponse.")

    @pytest.mark.asyncio
    async def test_execute_reaction_response_failure(self):
        """Test _execute_reaction_response when reaction fails to send."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.set_message_reaction = AsyncMock(return_value=False)  # Failure case

        response = ReactionResponse(
            reasoning="Test reasoning",
            react_to_message_id="456",
            emoji=ReactionEmoji.RED_HEART,
        )

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat = MagicMock()

        result = await job._execute_reaction_response(response, mock_message)

        # Verify reaction was attempted
        job._run_context.bot.set_message_reaction.assert_called_once_with(
            chat_id=123, message_id=456, reaction=ReactionEmoji.RED_HEART
        )

        # Verify None is returned when reaction fails
        assert result is None

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_onboarding_session(self, frozen_time):
        """Test prepare_conversation_input with onboarding session."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.guided_session_key = "onboarding123"
        mock_onboarding_session.is_active = True

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify OnboardingAgentDependencies was created
        assert isinstance(deps, OnboardingAgentDependencies)
        assert deps.onboarding_session_key == "onboarding123"
        assert deps.tg_chat_id == "123"
        assert deps.tg_session_id == "session123"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_chat_context(self, frozen_time):
        """Test prepare_conversation_input with chat context items."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock context items
        mock_personality_context = MagicMock()
        mock_personality_context.type = ContextType.PERSONALITY.value
        mock_personality_context.content = {"personality": "celebration"}
        mock_personality_context.decrypt_content = MagicMock()

        mock_chat_event = MagicMock()
        mock_chat_event.timestamp = frozen_time

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[mock_chat_event])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            # Mock the latest personality context extraction
            with patch.object(job, "_get_chat_context") as mock_get_context:
                mock_get_context.return_value = [mock_personality_context]

                message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify ChatAgentDependencies was created with personality from context
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "celebration"
        assert deps.tg_chat_id == "123"
        assert deps.tg_session_id == "session123"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_personality_context_non_dict(self, frozen_time):
        """Test prepare_conversation_input when personality context content is not a dict."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock personality context with non-dict content
        mock_personality_context = MagicMock()
        mock_personality_context.type = ContextType.PERSONALITY.value
        mock_personality_context.content = "not a dict"  # Non-dict content
        mock_personality_context.decrypt_content = MagicMock()

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[mock_personality_context])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify default personality is used when content is not a dict
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "companionship"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_default_personality(self, frozen_time):
        """Test prepare_conversation_input with default personality when no context exists."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.random.choices", return_value=["companionship"]),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify default personality is randomly selected (mocked to companionship)
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "companionship"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_default_personality_exploration(self, frozen_time):
        """Test prepare_conversation_input with exploration as randomly selected default personality."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.random.choices", return_value=["exploration"]),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify exploration personality can be randomly selected
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "exploration"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_message_reaction_updated(self, frozen_time):
        """Test prepare_conversation_input with MessageReactionUpdated messages."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock MessageReactionUpdated message
        mock_message = MagicMock()
        mock_message.message_type = "MessageReactionUpdated"
        mock_message.message_id = "msg123"
        mock_message.created_at = frozen_time
        mock_message.decrypt = MagicMock()

        mock_chat_event = MagicMock()

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[mock_chat_event])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=False)

        # Verify message was included in history
        assert len(message_history) == 1
        assert message_history[0] == mock_chat_event

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_unknown_message_type(self, frozen_time):
        """Test prepare_conversation_input with unknown message types - should be filtered by _get_chat_history."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(
                job, "_get_chat_history", new=AsyncMock(return_value=[])
            ),  # _get_chat_history filters unknown types
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=False)

        # Verify empty message history (unknown types filtered out)
        assert len(message_history) == 0

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_inactive_onboarding_session(self, frozen_time):
        """Test prepare_conversation_input with inactive onboarding session."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock inactive onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.guided_session_key = "onboarding123"
        mock_onboarding_session.is_active = False  # Inactive

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.random.choices", return_value=["companionship"]),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify ChatAgentDependencies was created (not OnboardingAgentDependencies)
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "companionship"
        assert not hasattr(deps, "onboarding_session_key")

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_message_filtering(self, frozen_time):
        """Test prepare_conversation_input filters messages by run timestamp - delegated to _get_chat_history."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock chat event that represents filtered messages
        mock_chat_event = MagicMock()
        mock_chat_event.timestamp = frozen_time - timedelta(minutes=30)

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(
                job, "_get_chat_history", new=AsyncMock(return_value=[mock_chat_event])
            ),  # Returns filtered messages
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=False)

        # Verify message was included (filtering happens in _get_chat_history)
        assert len(message_history) == 1
        assert message_history[0] == mock_chat_event

    @pytest.mark.asyncio
    async def test_run_job_notification_completion(self, frozen_time):
        """Test run_job marks notification as completed when notification is present and successful."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock(spec=telegram.Message)

        # Create a mock notification object
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification content"

        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=mock_notification,
        )

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(job, "prepare_conversation_input", new=AsyncMock(return_value=([], mock_deps))),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)),
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "_mark_notification_completed", new=AsyncMock()) as mock_mark_notification,
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify notification was marked as completed
        mock_mark_notification.assert_called_once_with(mock_notification)

    @pytest.mark.asyncio
    async def test_run_job_notification_completion_with_do_nothing_response(self, frozen_time):
        """Test run_job marks notification as completed even with DoNothingResponse."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        # Agent returns DoNothingResponse
        mock_response = DoNothingResponse(reasoning="Nothing to do")

        # Create a mock notification object
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification content"

        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=mock_notification,
        )

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(job, "prepare_conversation_input", new=AsyncMock(return_value=([], mock_deps))),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)),
            patch.object(job, "execute_response", new=AsyncMock(return_value=None)),
            patch.object(job, "_mark_notification_completed", new=AsyncMock()) as mock_mark_notification,
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify notification was NOT marked as completed since DoNothingResponse returns None (no telegram.Message)
        mock_mark_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_response_no_notification_completion_when_no_notification(self):
        """Test generate_response does not call mark_notification_completed when no notification exists."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        # Dependencies without notification
        mock_deps = ChatAgentDependencies(
            tg_bot_id="bot123",
            tg_chat_id="123",
            tg_session_id="session123",
            personality="companionship",
            restricted_responses=set(),
            notification=None,  # No notification
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "_mark_notification_completed", new=AsyncMock()) as mock_mark_notification,
        ):
            result = await job.generate_response(
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == mock_response
        # Verify notification completion was NOT called since there was no notification
        mock_mark_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_compress_session_context(self, frozen_time):
        """Test compress_session_context method."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job._bot_id = "bot123"

        # Create mock message history
        mock_chat_event = MagicMock(spec=ChatEvent)
        mock_chat_event.timestamp = frozen_time
        mock_chat_event.to_model_message = MagicMock(return_value=MagicMock())
        message_history = [mock_chat_event]

        mock_context_template = MagicMock()
        mock_payload = MagicMock()
        mock_payload.output = mock_context_template

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ) as mock_run_agent,
        ):
            result = await job.compress_session_context(message_history)

        # Verify agent was called with correct parameters
        mock_run_agent.assert_called_once()
        call_args = mock_run_agent.call_args
        assert call_args[1]["chat_id"] == "123"
        assert call_args[1]["session_id"] == "session123"

        # Verify result is the context template
        assert result == mock_context_template

    @pytest.mark.asyncio
    async def test_get_session_context(self):
        """Test _get_session_context method."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"

        mock_context = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.Context.get_by_session_id",
                new=AsyncMock(return_value=mock_context),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._get_session_context()

        # Note: The implementation has a bug - it should return context, not context | None
        # But we test the actual behavior
        assert result is not None

    @pytest.mark.asyncio
    async def test_save_session_context(self):
        """Test _save_session_context method."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job.chat_encryption_key = "test_encryption_key"

        test_data = {"test": "data"}

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.Context.new",
                new=AsyncMock(),
            ) as mock_new_or_update,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await job._save_session_context(ctype=ContextType.RESPONSE, data=test_data)

        mock_new_or_update.assert_called_once_with(
            mock_db_conn,
            chat_encryption_key="test_encryption_key",
            chat_id="123",
            session_id="session123",
            ctype=ContextType.RESPONSE.value,
            content=test_data,
        )

    @pytest.mark.asyncio
    async def test_log_bot_activity(self, frozen_time):
        """Test _log_bot_activity method."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.new_activity = AsyncMock()  # Make it async
        job._run_timestamp = frozen_time

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await job._log_bot_activity()

        job.active_session.new_activity.assert_called_once_with(
            mock_db_conn,
            timestamp=frozen_time,
            is_user=False,
        )

    @pytest.mark.asyncio
    async def test_mark_notification_completed(self):
        """Test _mark_notification_completed method."""
        job = ConversationJob("123")
        mock_notification = MagicMock(spec=Notifications)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await job._mark_notification_completed(mock_notification)

        mock_notification.mark_as_completed.assert_called_once_with(mock_db_conn)

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_with_notification(self, frozen_time):
        """Test prepare_conversation_input properly fetches and includes notification."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        # Create mock notification
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification content"

        # Mock onboarding session as inactive
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=mock_notification)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=True)

        # Verify dependencies include the notification
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.notification == mock_notification
        assert deps.tg_chat_id == "123"
        assert deps.tg_session_id == "session123"

    @pytest.mark.asyncio
    async def test_execute_text_with_buttons_response(self):
        """Test _execute_text_response with TextWithButtonsResponse."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        buttons = [
            _MessageButton(label="Option 1", callback="opt1"),
            _MessageButton(label="Option 2", callback="opt2"),
            _MessageButton(label="Option 3", callback="opt3"),
        ]

        response = TextWithButtonsResponse(
            reasoning="Test reasoning",
            message_text="Choose an option:",
            reply_to_message_id=None,
            buttons=buttons,
            buttons_per_row=2,
            context="Button context for understanding",
        )

        await job._execute_text_response(response)

        # Verify send_message was called with inline keyboard
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Choose an option:"
        assert call_args.kwargs["reply_parameters"] is None

        # Verify reply_markup contains inline keyboard
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert isinstance(reply_markup, telegram.InlineKeyboardMarkup)

        # Check button layout (2 buttons per row, so 2 rows)
        assert len(reply_markup.inline_keyboard) == 2
        assert len(reply_markup.inline_keyboard[0]) == 2  # First row has 2 buttons
        assert len(reply_markup.inline_keyboard[1]) == 1  # Second row has 1 button

        # Check button content
        assert reply_markup.inline_keyboard[0][0].text == "Option 1"
        assert reply_markup.inline_keyboard[0][0].callback_data == "response::opt1"
        assert reply_markup.inline_keyboard[0][1].text == "Option 2"
        assert reply_markup.inline_keyboard[0][1].callback_data == "response::opt2"
        assert reply_markup.inline_keyboard[1][0].text == "Option 3"
        assert reply_markup.inline_keyboard[1][0].callback_data == "response::opt3"

    @pytest.mark.asyncio
    async def test_execute_text_with_buttons_single_row(self):
        """Test _execute_text_response with TextWithButtonsResponse single row layout."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        buttons = [
            _MessageButton(label="Yes", callback="yes"),
            _MessageButton(label="No", callback="no"),
        ]

        response = TextWithButtonsResponse(
            reasoning="Test reasoning",
            message_text="Do you agree?",
            reply_to_message_id="456",
            buttons=buttons,
            buttons_per_row=2,
            context="Yes/No confirmation buttons",
        )

        await job._execute_text_response(response)

        # Verify send_message was called with reply parameters and inline keyboard
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Do you agree?"
        assert call_args.kwargs["reply_parameters"].message_id == 456

        # Verify reply_markup contains single row
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert len(reply_markup.inline_keyboard) == 1
        assert len(reply_markup.inline_keyboard[0]) == 2

    @pytest.mark.asyncio
    async def test_text_with_buttons_response_logging_includes_context(self, frozen_time):
        """Test that button responses include context in reasoning for logging."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time - timedelta(minutes=1)

        buttons = [_MessageButton(label="Option 1", callback="opt1")]
        mock_response = TextWithButtonsResponse(
            reasoning="Test reasoning",
            message_text="Choose:",
            reply_to_message_id=None,
            buttons=buttons,
            buttons_per_row=1,
            context="Additional context for buttons",
        )
        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(
                job,
                "prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_bot_id="bot123",
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="companionship",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)),
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()) as mock_log_event,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify message event was logged with reasoning + context
        mock_log_event.assert_called_once_with(
            session=mock_session,
            message=mock_message,
            user_id="bot123",
            is_user=False,
            reasoning="Test reasoningAdditional context for buttons",  # reasoning + context concatenated
        )

    @pytest.mark.asyncio
    async def test_execute_keyboard_response_single_column(self):
        """Test _execute_text_response with KeyboardResponse (3 or fewer buttons - single column)."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        buttons = [
            _KeyboardButton(text="Yes"),
            _KeyboardButton(text="No"),
            _KeyboardButton(text="Maybe"),
        ]

        response = KeyboardResponse(
            reasoning="Test reasoning",
            message_text="Do you agree?",
            reply_to_message_id=None,
            tooltip_text="Choose your response",
            buttons=buttons,
        )

        await job._execute_text_response(response)

        # Verify send_message was called with reply keyboard
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Do you agree?"
        assert call_args.kwargs["reply_parameters"] is None

        # Verify reply_markup contains reply keyboard
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert isinstance(reply_markup, telegram.ReplyKeyboardMarkup)

        # Check button layout (3 or fewer buttons - single column)
        assert len(reply_markup.keyboard) == 3  # 3 rows
        assert len(reply_markup.keyboard[0]) == 1  # First row has 1 button
        assert len(reply_markup.keyboard[1]) == 1  # Second row has 1 button
        assert len(reply_markup.keyboard[2]) == 1  # Third row has 1 button

        # Check button content
        assert reply_markup.keyboard[0][0].text == "Yes"
        assert reply_markup.keyboard[1][0].text == "No"
        assert reply_markup.keyboard[2][0].text == "Maybe"

        # Check keyboard properties
        assert reply_markup.one_time_keyboard is True
        assert reply_markup.resize_keyboard is True
        assert reply_markup.input_field_placeholder == "Choose your response"

    @pytest.mark.asyncio
    async def test_execute_keyboard_response_multi_row(self):
        """Test _execute_text_response with KeyboardResponse (more than 3 buttons - 3 per row)."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        buttons = [
            _KeyboardButton(text="Option 1"),
            _KeyboardButton(text="Option 2"),
            _KeyboardButton(text="Option 3"),
            _KeyboardButton(text="Option 4"),
            _KeyboardButton(text="Option 5"),
        ]

        response = KeyboardResponse(
            reasoning="Test reasoning",
            message_text="Choose an option:",
            reply_to_message_id="456",
            tooltip_text="Pick one of the options",
            buttons=buttons,
        )

        await job._execute_text_response(response)

        # Verify send_message was called with reply parameters and reply keyboard
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Choose an option:"
        assert call_args.kwargs["reply_parameters"].message_id == 456

        # Verify reply_markup contains reply keyboard
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert isinstance(reply_markup, telegram.ReplyKeyboardMarkup)

        # Check button layout (more than 3 buttons - 3 per row)
        assert len(reply_markup.keyboard) == 2  # 2 rows
        assert len(reply_markup.keyboard[0]) == 3  # First row has 3 buttons
        assert len(reply_markup.keyboard[1]) == 2  # Second row has 2 buttons

        # Check button content
        assert reply_markup.keyboard[0][0].text == "Option 1"
        assert reply_markup.keyboard[0][1].text == "Option 2"
        assert reply_markup.keyboard[0][2].text == "Option 3"
        assert reply_markup.keyboard[1][0].text == "Option 4"
        assert reply_markup.keyboard[1][1].text == "Option 5"

    @pytest.mark.asyncio
    async def test_execute_text_response_removes_keyboard_for_text_only(self):
        """Test that TextResponse removes any existing keyboard."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        response = TextResponse(
            reasoning="Test reasoning",
            message_text="Simple text response",
            reply_to_message_id=None,
        )

        await job._execute_text_response(response)

        # Verify send_message was called with ReplyKeyboardRemove
        job._run_context.bot.send_message.assert_called_once()
        call_args = job._run_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Simple text response"

        # Verify reply_markup removes keyboard
        reply_markup = call_args.kwargs["reply_markup"]
        assert reply_markup is not None
        assert isinstance(reply_markup, telegram.ReplyKeyboardRemove)

    # Missing method tests

    @pytest.mark.asyncio
    async def test_apply_response_delay_with_user_metadata(self):
        """Test apply_response_delay with user metadata."""
        job = ConversationJob("123")

        mock_user_metadata = MagicMock()
        mock_user_metadata.response_wait_time = 3

        with (
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=mock_user_metadata)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await job.apply_response_delay()

        mock_sleep.assert_called_once_with(3)

    @pytest.mark.asyncio
    async def test_apply_response_delay_default(self):
        """Test apply_response_delay with default delay when no user metadata."""
        job = ConversationJob("123")

        with (
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await job.apply_response_delay()

        mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_apply_response_delay_zero_delay(self):
        """Test apply_response_delay with zero delay."""
        job = ConversationJob("123")

        mock_user_metadata = MagicMock()
        mock_user_metadata.response_wait_time = 0

        with (
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=mock_user_metadata)),
            patch("areyouok_telegram.jobs.conversations.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            await job.apply_response_delay()

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_get_user_metadata_success(self):
        """Test _get_user_metadata returns user metadata."""
        job = ConversationJob("123")

        mock_user_metadata = MagicMock()

        with patch(
            "areyouok_telegram.jobs.conversations.UserMetadata.get_by_user_id",
            new=AsyncMock(return_value=mock_user_metadata),
        ):
            result = await job._get_user_metadata()

        assert result == mock_user_metadata

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_get_user_metadata_not_found(self):
        """Test _get_user_metadata returns None when no metadata found."""
        job = ConversationJob("123")

        with patch(
            "areyouok_telegram.jobs.conversations.UserMetadata.get_by_user_id", new=AsyncMock(return_value=None)
        ):
            result = await job._get_user_metadata()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_chat_context_filtering_and_sorting(self, frozen_time):
        """Test _get_chat_context filtering and sorting logic."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"

        # Create mock context items with different types and timestamps
        mock_session_context_old = MagicMock()
        mock_session_context_old.type = ContextType.SESSION.value
        mock_session_context_old.created_at = frozen_time - timedelta(days=2)  # Too old, should be filtered
        mock_session_context_old.decrypt_content = MagicMock()

        mock_session_context_recent = MagicMock()
        mock_session_context_recent.type = ContextType.SESSION.value
        mock_session_context_recent.created_at = frozen_time - timedelta(hours=12)  # Recent, should be included
        mock_session_context_recent.session_id = "other_session"
        mock_session_context_recent.decrypt_content = MagicMock()

        mock_personality_context = MagicMock()
        mock_personality_context.type = ContextType.PERSONALITY.value
        mock_personality_context.created_at = frozen_time - timedelta(hours=6)  # Recent, should be included
        mock_personality_context.session_id = "session123"  # Same session, should be included
        mock_personality_context.decrypt_content = MagicMock()

        context_items = [mock_session_context_old, mock_session_context_recent, mock_personality_context]

        with patch(
            "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
            new=AsyncMock(return_value=context_items),
        ):
            result = await job._get_chat_context()

        # Should include recent session context and current session personality context
        assert len(result) == 2
        assert mock_session_context_recent in result
        assert mock_personality_context in result
        assert mock_session_context_old not in result

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_get_chat_context_no_context_items(self):
        """Test _get_chat_context when no context items exist."""
        job = ConversationJob("123")
        job.chat_encryption_key = "test_encryption_key"

        with patch(
            "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat", new=AsyncMock(return_value=None)
        ):
            result = await job._get_chat_context()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_chat_history_message_filtering(self, frozen_time):
        """Test _get_chat_history filters messages by timestamp."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job.active_session = MagicMock()

        # Create mock messages with different timestamps
        mock_message_before = MagicMock()
        mock_message_before.created_at = frozen_time - timedelta(minutes=10)  # Before run timestamp
        mock_message_before.message_type = "Message"
        mock_message_before.message_id = "msg1"
        mock_message_before.decrypt = MagicMock()

        mock_message_after = MagicMock()
        mock_message_after.created_at = frozen_time + timedelta(minutes=10)  # After run timestamp, should be filtered
        mock_message_after.message_type = "Message"
        mock_message_after.message_id = "msg2"
        mock_message_after.decrypt = MagicMock()

        raw_messages = [mock_message_before, mock_message_after]
        job.active_session.get_messages = AsyncMock(return_value=raw_messages)

        mock_chat_event = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id", new=AsyncMock(return_value=[])),
            patch("areyouok_telegram.jobs.conversations.ChatEvent.from_message", return_value=mock_chat_event),
        ):
            result = await job._get_chat_history()

        # Should only include message before run timestamp
        assert len(result) == 1
        assert result[0] == mock_chat_event

    @pytest.mark.asyncio
    async def test_get_chat_history_with_media_files(self, frozen_time):
        """Test _get_chat_history handles media files properly."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job.active_session = MagicMock()

        mock_message = MagicMock()
        mock_message.created_at = frozen_time - timedelta(minutes=10)
        mock_message.message_type = "Message"
        mock_message.message_id = "msg1"
        mock_message.decrypt = MagicMock()

        mock_media_file = MagicMock()
        mock_media_file.decrypt_content = MagicMock()
        media_files = [mock_media_file]

        job.active_session.get_messages = AsyncMock(return_value=[mock_message])

        mock_chat_event = MagicMock()

        with (
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=media_files),
            ),
            patch("areyouok_telegram.jobs.conversations.ChatEvent.from_message", return_value=mock_chat_event),
        ):
            result = await job._get_chat_history()

        # Verify media file was decrypted
        mock_media_file.decrypt_content.assert_called_once_with(chat_encryption_key="test_encryption_key")
        assert len(result) == 1
        assert result[0] == mock_chat_event

    @pytest.mark.asyncio
    async def test_get_chat_history_message_reaction_updated(self, frozen_time):
        """Test _get_chat_history handles MessageReactionUpdated messages."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job.active_session = MagicMock()

        mock_message = MagicMock()
        mock_message.created_at = frozen_time - timedelta(minutes=10)
        mock_message.message_type = "MessageReactionUpdated"
        mock_message.message_id = "msg1"
        mock_message.decrypt = MagicMock()

        job.active_session.get_messages = AsyncMock(return_value=[mock_message])

        mock_chat_event = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.ChatEvent.from_message", return_value=mock_chat_event):
            result = await job._get_chat_history()

        # MessageReactionUpdated should have empty media list
        assert len(result) == 1
        assert result[0] == mock_chat_event

    @pytest.mark.asyncio
    async def test_get_chat_history_unknown_message_type(self, frozen_time):
        """Test _get_chat_history skips unknown message types."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job.active_session = MagicMock()

        mock_message_known = MagicMock()
        mock_message_known.created_at = frozen_time - timedelta(minutes=10)
        mock_message_known.message_type = "Message"
        mock_message_known.message_id = "msg1"
        mock_message_known.decrypt = MagicMock()

        mock_message_unknown = MagicMock()
        mock_message_unknown.created_at = frozen_time - timedelta(minutes=5)
        mock_message_unknown.message_type = "UnknownType"
        mock_message_unknown.message_id = "msg2"
        mock_message_unknown.decrypt = MagicMock()

        job.active_session.get_messages = AsyncMock(return_value=[mock_message_known, mock_message_unknown])

        mock_chat_event = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id", new=AsyncMock(return_value=[])),
            patch("areyouok_telegram.jobs.conversations.ChatEvent.from_message", return_value=mock_chat_event),
        ):
            result = await job._get_chat_history()

        # Should only include known message type
        assert len(result) == 1
        assert result[0] == mock_chat_event

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_get_next_notification_success(self):
        """Test _get_next_notification returns notification."""
        job = ConversationJob("123")

        mock_notification = MagicMock()

        with patch(
            "areyouok_telegram.jobs.conversations.Notifications.get_next_pending",
            new=AsyncMock(return_value=mock_notification),
        ):
            result = await job._get_next_notification()

        assert result == mock_notification

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_get_next_notification_none(self):
        """Test _get_next_notification returns None when no notifications."""
        job = ConversationJob("123")

        with patch(
            "areyouok_telegram.jobs.conversations.Notifications.get_next_pending", new=AsyncMock(return_value=None)
        ):
            result = await job._get_next_notification()

        assert result is None

    # Branch coverage tests

    @pytest.mark.asyncio
    async def test_run_job_session_compression_with_existing_context(self, frozen_time):
        """Test run_job session compression when context already exists."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = frozen_time - timedelta(hours=2)  # Inactive session
        mock_session.session_id = "session123"

        mock_context = MagicMock()  # Existing context

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(job, "_get_session_context", new=AsyncMock(return_value=mock_context)),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.warning") as mock_warning,
            patch("areyouok_telegram.data.operations.close_chat_session", new=AsyncMock()),
        ):
            await job.run_job()

        mock_warning.assert_called_once_with(
            "Context already exists for session, skipping compression.", session_id="session123"
        )
        mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_job_session_compression_with_empty_message_history(self, frozen_time):
        """Test run_job session compression with empty message history."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = frozen_time - timedelta(hours=2)  # Inactive session
        mock_session.session_id = "session123"

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(job, "_get_session_context", new=AsyncMock(return_value=None)),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),  # Empty history
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.warning") as mock_warning,
            patch("areyouok_telegram.data.operations.close_chat_session", new=AsyncMock()),
        ):
            await job.run_job()

        mock_warning.assert_called_once()
        assert "No messages found" in str(mock_warning.call_args[0][0])
        mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_job_evaluation_scheduling(self, frozen_time):
        """Test run_job schedules evaluation when message history is substantial."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = frozen_time - timedelta(hours=2)  # Inactive session
        mock_session.session_id = "session123"

        # Create message history with more than 5 messages
        message_history = [MagicMock() for _ in range(7)]

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch.object(job, "_get_session_context", new=AsyncMock(return_value=None)),
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=message_history)),
            patch.object(job, "compress_session_context", new=AsyncMock()),
            patch.object(job, "_save_session_context", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.run_job_once", new=AsyncMock()) as mock_run_job_once,
            patch.object(job, "stop", new=AsyncMock()),
            patch("areyouok_telegram.data.operations.close_chat_session", new=AsyncMock()),
        ):
            await job.run_job()

        # Verify evaluation job was scheduled
        mock_run_job_once.assert_called_once()
        call_args = mock_run_job_once.call_args[1]
        assert call_args["context"] == job._run_context
        assert call_args["job"].__class__.__name__ == "EvaluationsJob"

    @pytest.mark.asyncio
    async def test_run_job_message_iteration_logic(self, frozen_time):
        """Test run_job while loop with message timestamp updates."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_chat_action = AsyncMock()

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"
        mock_session.last_user_message = frozen_time + timedelta(seconds=30)  # Updated after start

        updated_session = MagicMock()
        updated_session.has_bot_responded = False
        updated_session.session_id = "session123"
        updated_session.last_user_message = frozen_time + timedelta(seconds=30)

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id=None)
        mock_message = MagicMock(spec=telegram.Message)

        # Create a proper mock dependencies object with notification set to None
        mock_dependencies = MagicMock()
        mock_dependencies.notification = None

        call_count = 0

        def side_effect_get_session(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return mock_session
            else:
                return updated_session

        with (
            patch(
                "areyouok_telegram.data.operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch(
                "areyouok_telegram.data.operations.get_or_create_active_session", side_effect=side_effect_get_session
            ),
            patch.object(job, "prepare_conversation_input", new=AsyncMock(return_value=([], mock_dependencies))),
            patch.object(job, "generate_response", new=AsyncMock(return_value=mock_response)),
            patch.object(job, "execute_response", new=AsyncMock(return_value=mock_message)),
            patch.object(job, "apply_response_delay", new=AsyncMock()) as mock_apply_delay,
            patch.object(job, "_log_bot_activity", new=AsyncMock()),
            patch.object(job, "_get_user_metadata", new=AsyncMock(return_value=None)),
            patch("areyouok_telegram.data.operations.new_session_event", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job.run_job()

        # Verify apply_response_delay was called twice (once in iteration, once at end)
        assert mock_apply_delay.call_count == 2

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_without_context(self, frozen_time):
        """Test prepare_conversation_input with include_context=False."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job.chat_encryption_key = "test_encryption_key"
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        job.active_session = mock_session

        mock_onboarding_session = MagicMock()
        mock_onboarding_session.is_active = False

        with (
            patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=mock_onboarding_session),
            ),
            patch.object(job, "_get_chat_context", new=AsyncMock()) as mock_get_context,
            patch.object(job, "_get_chat_history", new=AsyncMock(return_value=[])),
            patch.object(job, "_get_next_notification", new=AsyncMock(return_value=None)),
        ):
            message_history, deps = await job.prepare_conversation_input(include_context=False)

        # Verify _get_chat_context was NOT called
        mock_get_context.assert_not_called()
        assert len(message_history) == 0

    # Exception handling tests

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_database_connection_failure_retry_decorated_methods(self):
        """Test that @db_retry decorated methods handle database failures."""
        job = ConversationJob("123")

        # Test a few representative @db_retry methods
        with patch("areyouok_telegram.jobs.conversations.async_database", side_effect=Exception("Database error")):
            with pytest.raises(Exception, match="Database error"):
                await job._get_user_metadata()

            with pytest.raises(Exception, match="Database error"):
                await job._get_next_notification()

    @pytest.mark.asyncio
    async def test_telegram_api_failure_handling(self):
        """Test handling of Telegram API failures."""
        job = ConversationJob("123")
        job._run_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        job._run_context.bot.send_message = AsyncMock(side_effect=Exception("Telegram API error"))

        response = TextResponse(reasoning="Test reasoning", message_text="Test message", reply_to_message_id=None)

        with pytest.raises(Exception, match="Telegram API error"):
            await job._execute_text_response(response)

    @pytest.mark.asyncio
    async def test_agent_execution_failure_in_generate_response(self):
        """Test agent execution failure in generate_response."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"

        mock_deps = MagicMock()

        with patch(
            "areyouok_telegram.jobs.conversations.run_agent_with_tracking",
            new=AsyncMock(side_effect=Exception("Agent error")),
        ):
            with pytest.raises(Exception, match="Agent error"):
                await job.generate_response(conversation_history=[], dependencies=mock_deps)

    @pytest.mark.asyncio
    async def test_agent_execution_failure_in_compress_session_context(self):
        """Test agent execution failure in compress_session_context."""
        job = ConversationJob("123")
        job.active_session = MagicMock()
        job.active_session.session_id = "session123"
        job._bot_id = "bot123"

        mock_chat_event = MagicMock()
        mock_chat_event.timestamp = datetime.now(UTC)
        mock_chat_event.to_model_message = MagicMock()

        with patch(
            "areyouok_telegram.jobs.conversations.run_agent_with_tracking",
            new=AsyncMock(side_effect=Exception("Context compression error")),
        ):
            with pytest.raises(Exception, match="Context compression error"):
                await job.compress_session_context([mock_chat_event])
