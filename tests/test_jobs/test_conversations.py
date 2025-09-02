"""Tests for jobs/conversations.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import ANY
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

from areyouok_telegram.data.models.chat_event import ChatEvent
from areyouok_telegram.data.models.context import ContextType
from areyouok_telegram.jobs.conversations import ConversationJob
from areyouok_telegram.jobs.exceptions import UserNotFoundForChatError
from areyouok_telegram.data.models.notifications import Notifications
from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import DoNothingResponse
from areyouok_telegram.llms.chat import OnboardingAgentDependencies
from areyouok_telegram.llms.chat import ReactionResponse
from areyouok_telegram.llms.chat import SwitchPersonalityResponse
from areyouok_telegram.llms.chat import TextResponse


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
        """Test _run when bot has already responded."""
        job = ConversationJob("123")
        job._run_timestamp = datetime.now(UTC)

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = datetime.now(UTC) - timedelta(minutes=30)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch("areyouok_telegram.jobs.conversations.logfire.debug") as mock_log_debug,
        ):
            await job._run(mock_context)

        mock_log_debug.assert_called_once_with("No new updates, nothing to do.")

    @pytest.mark.asyncio
    async def test_run_inactive_session_closes(self, frozen_time):
        """Test _run closes inactive session after 1 hour."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = frozen_time - timedelta(hours=2)  # 2 hours ago
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch.object(job, "close_session", new=AsyncMock()) as mock_close,
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify session was closed and job was stopped
        mock_close.assert_called_once_with("test_encryption_key", context=mock_context, chat_session=mock_session)
        mock_stop.assert_called_once_with(mock_context)

    @pytest.mark.asyncio
    async def test_run_generates_response(self, frozen_time):
        """Test _run generates and executes response."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"
        mock_context.bot.send_chat_action = AsyncMock()

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id=None)

        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch(
                "areyouok_telegram.jobs.conversations.get_next_notification",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ),
            patch.object(
                job,
                "_prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_context=mock_context,
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="exploration",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(
                job, "generate_response", new=AsyncMock(return_value=(mock_response, mock_message))
            ) as mock_generate,
            patch("areyouok_telegram.jobs.conversations.log_bot_activity", new=AsyncMock()) as mock_log_activity,
            patch("areyouok_telegram.jobs.conversations.log_bot_message", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify response was generated and executed
        mock_generate.assert_called_once()

        # Verify bot activity was logged
        mock_log_activity.assert_called_once_with(
            chat_session=mock_session,
            timestamp=frozen_time,
        )

    @pytest.mark.asyncio
    async def test_generate_response_success(self):
        """Test generate_response returns agent response."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ) as mock_mark_notification,
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == (mock_response, mock_message)
        # Verify notification completion was not called since there was no notification
        mock_mark_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_response_exception(self):
        """Test generate_response raises exceptions (no internal error handling)."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking",
                new=AsyncMock(side_effect=Exception("Test error")),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ),
        ):
            with pytest.raises(Exception, match="Test error"):
                await job.generate_response(
                    context=mock_context,
                    chat_encryption_key="test_encryption_key",
                    chat_session=mock_session,
                    conversation_history=[],
                    dependencies=mock_deps,
                )

    @pytest.mark.asyncio
    async def test_execute_response_text(self):
        """Test execute_response for text response."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id="456")

        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch.object(job, "_execute_text_response", new=AsyncMock(return_value=mock_message)) as mock_execute_text,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            result = await job._execute_response(
                chat_encryption_key="test_encryption_key",
                context=mock_context,
                chat_session=MagicMock(),
                response=mock_response,
            )

        assert result == mock_message
        mock_execute_text.assert_called_once_with(context=mock_context, response=mock_response)
        mock_log_info.assert_called_once_with("Response executed in chat 123: TextResponse.")

    @pytest.mark.asyncio
    async def test_execute_response_reaction(self):
        """Test execute_response for reaction response."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_response = ReactionResponse(
            reasoning="Test reasoning", react_to_message_id="456", emoji=ReactionEmoji.THUMBS_UP
        )

        # Create a Messages mock (SQLAlchemy object), not a telegram.Message
        mock_message = MagicMock()
        mock_message.decrypt_payload = MagicMock(return_value='{"message_id": 456}')
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

            result = await job._execute_response(
                chat_encryption_key="test_encryption_key",
                context=mock_context,
                chat_session=MagicMock(),
                response=mock_response,
            )

        assert result == mock_reaction
        mock_execute_reaction.assert_called_once_with(
            context=mock_context, response=mock_response, message=mock_message.telegram_object
        )
        mock_log_info.assert_called_once_with("Response executed in chat 123: ReactionResponse.")

    @pytest.mark.asyncio
    async def test_execute_response_reaction_message_not_found(self):
        """Test execute_response when reaction target message not found."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
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

            result = await job._execute_response(
                chat_encryption_key="test_encryption_key",
                context=mock_context,
                chat_session=MagicMock(),
                response=mock_response,
            )

        assert result is None
        mock_log_warning.assert_called_once_with("Message 456 not found in chat 123, skipping reaction.")

    @pytest.mark.asyncio
    async def test_execute_text_response_with_reply(self):
        """Test _execute_text_response with reply parameters."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        response = TextResponse(reasoning="Test reasoning", message_text="Reply text", reply_to_message_id="789")

        await job._execute_text_response(mock_context, response)

        # Verify send_message was called with reply parameters
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == 123
        assert call_args.kwargs["text"] == "Reply text"
        assert call_args.kwargs["reply_parameters"].message_id == 789

    @pytest.mark.asyncio
    async def test_execute_text_response_no_reply(self):
        """Test _execute_text_response without reply parameters."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.send_message = AsyncMock(return_value=MagicMock(spec=telegram.Message))

        response = TextResponse(reasoning="Test reasoning", message_text="Regular text", reply_to_message_id=None)

        await job._execute_text_response(mock_context, response)

        # Verify send_message was called without reply parameters
        mock_context.bot.send_message.assert_called_once_with(chat_id=123, text="Regular text", reply_parameters=None)

    @pytest.mark.asyncio
    async def test_execute_reaction_response_success(self):
        """Test _execute_reaction_response successfully sends reaction."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.set_message_reaction = AsyncMock(return_value=True)
        mock_context.bot.get_me = AsyncMock(return_value=MagicMock())

        response = ReactionResponse(
            reasoning="Test reasoning",
            react_to_message_id="456",
            emoji=ReactionEmoji.RED_HEART,  # This is actually ❤ not ❤️
        )

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat = MagicMock()

        result = await job._execute_reaction_response(mock_context, response, mock_message)

        # Verify reaction was sent
        mock_context.bot.set_message_reaction.assert_called_once_with(
            chat_id=123, message_id=456, reaction=ReactionEmoji.RED_HEART
        )

        # Verify MessageReactionUpdated was created
        assert isinstance(result, telegram.MessageReactionUpdated)
        assert result.message_id == 456

    @pytest.mark.asyncio
    async def test_close_session_with_existing_context(self):
        """Test close_session when context already exists."""
        job = ConversationJob("123")

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"

        mock_context = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.Context.get_by_session_id",
                new=AsyncMock(return_value=mock_context),
            ),
            patch("areyouok_telegram.jobs.conversations.logfire.warning") as mock_log_warning,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await job.close_session("test_encryption_key", context=MagicMock(), chat_session=mock_session)

        mock_log_warning.assert_called_once_with(
            "Context already exists for session, skipping compression.", session_id="session123"
        )

    @pytest.mark.asyncio
    async def test_close_session_no_messages(self):
        """Test close_session when no messages in session."""
        job = ConversationJob("123")

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch("areyouok_telegram.jobs.conversations.Context.get_by_session_id", new=AsyncMock(return_value=None)),
            patch.object(
                job,
                "_prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_context=mock_context,
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="exploration",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch("areyouok_telegram.jobs.conversations.close_chat_session", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.logfire.warning") as mock_log_warning,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await job.close_session("test_encryption_key", context=MagicMock(), chat_session=mock_session)

        mock_log_warning.assert_called_once_with("No messages found in chat session session123, nothing to compress.")

    @pytest.mark.asyncio
    async def test_close_session_success(self):
        """Test close_session successfully compresses and closes session."""
        job = ConversationJob("123")

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_messages = [MagicMock()]
        mock_compressed = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch("areyouok_telegram.jobs.conversations.Context.get_by_session_id", new=AsyncMock(return_value=None)),
            patch.object(
                job,
                "_prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        mock_messages,
                        ChatAgentDependencies(
                            tg_context=mock_context,
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="exploration",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "_compress_session_context", new=AsyncMock(return_value=mock_compressed)),
            patch("areyouok_telegram.jobs.conversations.save_session_context", new=AsyncMock()) as mock_save,
            patch("areyouok_telegram.jobs.conversations.close_chat_session", new=AsyncMock()) as mock_close,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            await job.close_session("test_encryption_key", context=MagicMock(), chat_session=mock_session)

        # Verify compression and closing
        # Note: Can't directly assert on job._compress_session_context since it's the original method
        # The mock_save and mock_close assertions below verify the flow worked

        mock_save.assert_called_once_with(
            chat_encryption_key="test_encryption_key",
            chat_id="123",
            chat_session=mock_session,
            ctype=ContextType.SESSION,
            data=ANY,
        )
        mock_close.assert_called_once_with(mock_session)
        mock_log_info.assert_called_once_with("Session session123 closed due to inactivity.")

    @pytest.mark.asyncio
    async def test_run_user_not_found_error(self):
        """Test _run when UserNotFoundForChatError is raised."""
        job = ConversationJob("123")
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(side_effect=UserNotFoundForChatError("No user found")),
            ),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.span") as mock_span,
        ):
            await job._run(mock_context)

        mock_stop.assert_called_once_with(mock_context)
        mock_span.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_no_active_session(self):
        """Test _run when no active session is found."""
        job = ConversationJob("123")
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=None)),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.logfire.span") as mock_span,
        ):
            await job._run(mock_context)

        mock_stop.assert_called_once_with(mock_context)
        mock_span.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_response_with_logging(self, frozen_time):
        """Test _run response generation with message logging."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time
        job._bot_id = "bot123"

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"
        mock_context.bot.send_chat_action = AsyncMock()

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id=None)
        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch.object(
                job,
                "_prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_context=mock_context,
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="exploration",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "generate_response", new=AsyncMock(return_value=(mock_response, mock_message))),
            patch("areyouok_telegram.jobs.conversations.log_bot_activity", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.log_bot_message", new=AsyncMock()) as mock_log_message,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify message was logged
        mock_log_message.assert_called_once_with(
            bot_id="bot123",
            chat_encryption_key="test_encryption_key",
            chat_id="123",
            chat_session=mock_session,
            message=mock_message,
            reasoning="Test reasoning",
        )

    @pytest.mark.asyncio
    async def test_run_response_without_message(self, frozen_time):
        """Test _run response generation when no message is returned."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.has_bot_responded = False
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.id = "bot123"
        mock_context.bot.send_chat_action = AsyncMock()

        mock_response = DoNothingResponse(reasoning="Do nothing")

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch.object(
                job,
                "_prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_context=mock_context,
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="exploration",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
            patch.object(job, "generate_response", new=AsyncMock(return_value=(mock_response, None))),
            patch("areyouok_telegram.jobs.conversations.log_bot_activity", new=AsyncMock()),
            patch("areyouok_telegram.jobs.conversations.log_bot_message", new=AsyncMock()) as mock_log_message,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify message was NOT logged when no message returned
        mock_log_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_response_personality_switching_restriction(self):
        """Test generate_response with personality switching restrictions."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        # Create conversation history with switch_personality event
        mock_chat_event = MagicMock(spec=ChatEvent)
        mock_chat_event.event_type = "switch_personality"
        conversation_history = [mock_chat_event]

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ),
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=conversation_history,
                dependencies=mock_deps,
            )

        # Verify switch_personality was added to restricted responses
        assert "switch_personality" in mock_deps.restricted_responses
        assert result == (mock_response, mock_message)

    @pytest.mark.asyncio
    async def test_generate_response_bot_last_message_restricts_text(self):
        """Test generate_response restricts text when bot was last to message."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        # Create conversation history where bot was last to message
        mock_chat_event = MagicMock(spec=ChatEvent)
        mock_chat_event.event_type = "message"
        mock_chat_event.user_id = "bot123"
        conversation_history = [mock_chat_event]

        mock_response = ReactionResponse(
            reasoning="Test reasoning", react_to_message_id="456", emoji=ReactionEmoji.THUMBS_UP
        )
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ),
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=conversation_history,
                dependencies=mock_deps,
            )

        # Verify text was added to restricted responses
        assert "text" in mock_deps.restricted_responses
        assert result == (mock_response, mock_message)

    @pytest.mark.asyncio
    async def test_generate_response_notification_removes_text_restriction(self):
        """Test generate_response removes text restriction when notification is present."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        # Create a mock notification object
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Special notification content"

        # Start with text in restricted responses and a notification
        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses={"text"},
            notification=mock_notification,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ) as mock_mark_notification,
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        # Verify text was removed from restricted responses
        assert "text" not in mock_deps.restricted_responses
        # Verify notification was marked as completed
        mock_mark_notification.assert_called_once_with(mock_notification)
        assert result == (mock_response, mock_message)

    @pytest.mark.asyncio
    async def test_generate_response_switch_personality_recursive(self):
        """Test generate_response handles SwitchPersonalityResponse with recursive call."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_switch_response = SwitchPersonalityResponse(reasoning="Switch personality", personality="celebration")
        mock_final_response = TextResponse(
            reasoning="Final response", message_text="Hello with new personality!", reply_to_message_id=None
        )
        mock_message = MagicMock()

        # Two separate payloads - first returns switch, second returns text
        mock_payload_switch = MagicMock()
        mock_payload_switch.output = mock_switch_response

        mock_payload_final = MagicMock()
        mock_payload_final.output = mock_final_response

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=None,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking",
                new=AsyncMock(side_effect=[mock_payload_switch, mock_payload_final]),
            ) as mock_run_agent,
            patch.object(job, "_execute_response", new=AsyncMock(side_effect=[None, mock_message])),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ),
            patch.object(
                job,
                "_prepare_conversation_input",
                new=AsyncMock(
                    return_value=(
                        [],
                        ChatAgentDependencies(
                            tg_context=mock_context,
                            tg_chat_id="123",
                            tg_session_id="session123",
                            personality="celebration",
                            restricted_responses=set(),
                            notification=None,
                        ),
                    )
                ),
            ),
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        # Verify both agent calls were made (first for switch, then for final response)
        assert mock_run_agent.call_count == 2
        assert result == (mock_final_response, mock_message)

    @pytest.mark.asyncio
    async def test_execute_response_switch_personality(self):
        """Test execute_response for switch personality response."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_response = SwitchPersonalityResponse(reasoning="Switch to celebration", personality="celebration")

        with (
            patch("areyouok_telegram.jobs.conversations.save_session_context", new=AsyncMock()) as mock_save,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            result = await job._execute_response(
                chat_encryption_key="test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                response=mock_response,
            )

        assert result is None
        mock_save.assert_called_once_with(
            chat_encryption_key="test_encryption_key",
            chat_id="123",
            chat_session=mock_session,
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

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_response = DoNothingResponse(reasoning="Nothing to do")

        with (
            patch("areyouok_telegram.jobs.conversations.save_session_context", new=AsyncMock()) as mock_save,
            patch("areyouok_telegram.jobs.conversations.logfire.info") as mock_log_info,
        ):
            result = await job._execute_response(
                chat_encryption_key="test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                response=mock_response,
            )

        assert result is None
        mock_save.assert_called_once_with(
            chat_encryption_key="test_encryption_key",
            chat_id="123",
            chat_session=mock_session,
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

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot.set_message_reaction = AsyncMock(return_value=False)  # Failure case

        response = ReactionResponse(
            reasoning="Test reasoning",
            react_to_message_id="456",
            emoji=ReactionEmoji.RED_HEART,
        )

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.chat = MagicMock()

        result = await job._execute_reaction_response(mock_context, response, mock_message)

        # Verify reaction was attempted
        mock_context.bot.set_message_reaction.assert_called_once_with(
            chat_id=123, message_id=456, reaction=ReactionEmoji.RED_HEART
        )

        # Verify None is returned when reaction fails
        assert result is None

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_onboarding_session(self, frozen_time):
        """Test _prepare_conversation_input with onboarding session."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.get_messages = AsyncMock(return_value=[])
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.guided_session_key = "onboarding123"
        mock_onboarding_session.is_active = True

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.get_next_notification",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=True,
            )

        # Verify OnboardingAgentDependencies was created
        assert isinstance(deps, OnboardingAgentDependencies)
        assert deps.onboarding_session_key == "onboarding123"
        assert deps.tg_chat_id == "123"
        assert deps.tg_session_id == "session123"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_chat_context(self, frozen_time):
        """Test _prepare_conversation_input with chat context items."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.get_messages = AsyncMock(return_value=[])
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock context items
        mock_session_context = MagicMock()
        mock_session_context.type = ContextType.SESSION.value
        mock_session_context.created_at = frozen_time - timedelta(hours=2)  # Within 24 hours
        mock_session_context.session_id = "other_session"
        mock_session_context.decrypt_content = MagicMock()

        mock_personality_context = MagicMock()
        mock_personality_context.type = ContextType.PERSONALITY.value
        mock_personality_context.created_at = frozen_time
        mock_personality_context.session_id = "session123"
        mock_personality_context.content = {"personality": "celebration"}
        mock_personality_context.decrypt_content = MagicMock()

        mock_chat_event = MagicMock()
        mock_chat_event.timestamp = frozen_time

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.get_next_notification",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[mock_session_context, mock_personality_context]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.ChatEvent.from_context",
                return_value=mock_chat_event,
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=True,
            )

        # Verify ChatAgentDependencies was created with personality from context
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "celebration"
        assert deps.tg_chat_id == "123"
        assert deps.tg_session_id == "session123"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_personality_context_non_dict(self, frozen_time):
        """Test _prepare_conversation_input when personality context content is not a dict."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.get_messages = AsyncMock(return_value=[])
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock personality context with non-dict content
        mock_personality_context = MagicMock()
        mock_personality_context.type = ContextType.PERSONALITY.value
        mock_personality_context.created_at = frozen_time
        mock_personality_context.session_id = "session123"
        mock_personality_context.content = "not a dict"  # Non-dict content
        mock_personality_context.decrypt_content = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[mock_personality_context]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.ChatEvent.from_context",
                return_value=MagicMock(),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=True,
            )

        # Verify default personality is used when content is not a dict
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "exploration"

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_default_personality(self, frozen_time):
        """Test _prepare_conversation_input with default personality when no context exists."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.get_messages = AsyncMock(return_value=[])
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=True,
            )

        # Verify default personality is used
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "exploration"


    @pytest.mark.asyncio
    async def test_prepare_conversation_input_message_reaction_updated(self, frozen_time):
        """Test _prepare_conversation_input with MessageReactionUpdated messages."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        # Create mock MessageReactionUpdated message
        mock_message = MagicMock()
        mock_message.message_type = "MessageReactionUpdated"
        mock_message.message_id = "msg123"
        mock_message.created_at = frozen_time
        mock_message.decrypt_payload = MagicMock()

        mock_session.get_messages = AsyncMock(return_value=[mock_message])

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.ChatEvent.from_message",
                return_value=MagicMock(),
            ) as mock_chat_event,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=False,
            )

        # Verify MessageReactionUpdated was processed (media should be empty list)
        mock_chat_event.assert_called_once_with(mock_message, [])

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_unknown_message_type(self, frozen_time):
        """Test _prepare_conversation_input with unknown message types."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        # Create mock message with unknown type
        mock_message = MagicMock()
        mock_message.message_type = "UnknownType"
        mock_message.message_id = "msg123"
        mock_message.created_at = frozen_time
        mock_message.decrypt_payload = MagicMock()

        mock_session.get_messages = AsyncMock(return_value=[mock_message])

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.ChatEvent.from_message",
                return_value=MagicMock(),
            ) as mock_chat_event,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=False,
            )

        # Verify unknown message type was skipped
        mock_chat_event.assert_not_called()


    @pytest.mark.asyncio
    async def test_prepare_conversation_input_inactive_onboarding_session(self, frozen_time):
        """Test _prepare_conversation_input with inactive onboarding session."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.get_messages = AsyncMock(return_value=[])
        mock_session.last_bot_activity = frozen_time - timedelta(hours=1)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock inactive onboarding session
        mock_onboarding_session = MagicMock()
        mock_onboarding_session.guided_session_key = "onboarding123"
        mock_onboarding_session.is_active = False  # Inactive

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[mock_onboarding_session]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=True,
            )

        # Verify ChatAgentDependencies was created (not OnboardingAgentDependencies)
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.personality == "exploration"
        assert not hasattr(deps, "onboarding_session_key")

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_message_filtering(self, frozen_time):
        """Test _prepare_conversation_input filters messages by run timestamp."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.last_bot_activity = frozen_time - timedelta(hours=2)

        # Create messages - one before and one after run timestamp
        mock_message_before = MagicMock()
        mock_message_before.message_type = "Message"
        mock_message_before.message_id = "msg_before"
        mock_message_before.created_at = frozen_time - timedelta(minutes=30)  # Before run timestamp
        mock_message_before.decrypt_payload = MagicMock()

        mock_message_after = MagicMock()
        mock_message_after.message_type = "Message"
        mock_message_after.message_id = "msg_after"
        mock_message_after.created_at = frozen_time + timedelta(minutes=30)  # After run timestamp
        mock_message_after.decrypt_payload = MagicMock()

        mock_session.get_messages = AsyncMock(return_value=[mock_message_before, mock_message_after])

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.ChatEvent.from_message",
                return_value=MagicMock(),
            ) as mock_chat_event,
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=False,
            )

        # Verify only the message before run timestamp was processed
        mock_chat_event.assert_called_once_with(mock_message_before, [])

    @pytest.mark.asyncio
    async def test_compress_session_context(self, frozen_time):
        """Test _compress_session_context method."""
        job = ConversationJob("123")
        job._bot_id = "bot123"

        mock_session = MagicMock()
        mock_session.session_id = "session123"

        # Create mock message history
        mock_chat_event = MagicMock(spec=ChatEvent)
        mock_chat_event.timestamp = frozen_time
        mock_chat_event.to_model_message = MagicMock(return_value=MagicMock())
        message_history = [mock_chat_event]

        mock_context_template = MagicMock()
        mock_payload = MagicMock()
        mock_payload.output = mock_context_template

        # Mock the context compression agent
        mock_agent = MagicMock()
        mock_agent.__name__ = "context_compression_agent"

        with (
            patch("areyouok_telegram.jobs.conversations.context_compression_agent", mock_agent),
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ) as mock_run_agent,
        ):
            result = await job._compress_session_context(mock_session, message_history)

        # Verify agent was called with correct parameters
        mock_run_agent.assert_called_once()
        call_args = mock_run_agent.call_args
        assert call_args[0][0] == mock_agent
        assert call_args[1]["chat_id"] == "123"
        assert call_args[1]["session_id"] == "session123"

        # Verify result is the context template
        assert result == mock_context_template

    @pytest.mark.asyncio
    async def test_generate_response_with_notification_completion(self):
        """Test generate_response marks notification as completed when notification is present and response is successful."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        # Create a mock notification object
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification content"

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=mock_notification,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ) as mock_mark_notification,
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == (mock_response, mock_message)
        # Verify notification was marked as completed
        mock_mark_notification.assert_called_once_with(mock_notification)

    @pytest.mark.asyncio
    async def test_generate_response_notification_completion_with_do_nothing_response(self):
        """Test generate_response marks notification as completed even with DoNothingResponse."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        # Agent returns DoNothingResponse
        mock_response = DoNothingResponse(reasoning="Nothing to do")
        mock_payload = MagicMock()
        mock_payload.output = mock_response

        # Create a mock notification object
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification content"

        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=mock_notification,
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=None)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ) as mock_mark_notification,
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == (mock_response, None)
        # Verify notification was marked as completed since agent_response is valid
        mock_mark_notification.assert_called_once_with(mock_notification)

    @pytest.mark.asyncio
    async def test_generate_response_no_notification_completion_when_no_notification(self):
        """Test generate_response does not call mark_notification_completed when no notification exists."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Test response", reply_to_message_id=None)
        mock_message = MagicMock()

        mock_payload = MagicMock()
        mock_payload.output = mock_response

        # Dependencies without notification
        mock_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123",
            tg_session_id="session123",
            personality="exploration",
            restricted_responses=set(),
            notification=None,  # No notification
        )

        with (
            patch(
                "areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)
            ),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message)),
            patch(
                "areyouok_telegram.jobs.conversations.mark_notification_completed",
                new=AsyncMock(),
            ) as mock_mark_notification,
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == (mock_response, mock_message)
        # Verify notification completion was NOT called since there was no notification
        mock_mark_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_prepare_conversation_input_with_notification(self, frozen_time):
        """Test _prepare_conversation_input properly fetches and includes notification."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.session_key = "session_key_123"
        mock_session.session_id = "session123"
        mock_session.get_messages = AsyncMock(return_value=[])

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        # Create mock notification
        mock_notification = MagicMock(spec=Notifications)
        mock_notification.content = "Test notification content"

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.conversations.get_next_notification",
                new=AsyncMock(return_value=mock_notification),
            ) as mock_get_notification,
            patch(
                "areyouok_telegram.jobs.conversations.GuidedSessions.get_by_chat_session",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.Context.retrieve_context_by_chat",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "areyouok_telegram.jobs.conversations.MediaFiles.get_by_message_id",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            message_history, deps = await job._prepare_conversation_input(
                "test_encryption_key",
                context=mock_context,
                chat_session=mock_session,
                include_context=True,
            )

        # Verify get_next_notification was called with correct chat_id
        mock_get_notification.assert_called_once_with("123")
        
        # Verify dependencies include the notification
        assert isinstance(deps, ChatAgentDependencies)
        assert deps.notification == mock_notification
        assert deps.tg_chat_id == "123"
        assert deps.tg_session_id == "session123"

    @pytest.mark.asyncio
    async def test_run_inactive_session_uses_session_start_as_reference(self, frozen_time):
        """Test _run uses session_start as reference when last_user_activity is None."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = None  # None value
        mock_session.session_start = frozen_time - timedelta(hours=2)  # Should use this as reference
        mock_session.session_id = "session123"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch.object(job, "close_session", new=AsyncMock()) as mock_close,
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.post_cleanup_tasks", new=AsyncMock()) as mock_cleanup,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify session was closed because it used session_start as reference
        mock_close.assert_called_once_with("test_encryption_key", context=mock_context, chat_session=mock_session)
        mock_stop.assert_called_once_with(mock_context)
        mock_cleanup.assert_called_once_with(context=mock_context, chat_session=mock_session)

    @pytest.mark.asyncio
    async def test_run_inactive_session_closes_with_post_cleanup(self, frozen_time):
        """Test _run closes inactive session and runs post cleanup tasks."""
        job = ConversationJob("123")
        job._run_timestamp = frozen_time

        mock_session = MagicMock()
        mock_session.has_bot_responded = True
        mock_session.last_user_activity = frozen_time - timedelta(hours=2)  # 2 hours ago
        mock_session.session_id = "session123"
        mock_session.session_start = frozen_time - timedelta(hours=3)

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch.object(job, "close_session", new=AsyncMock()) as mock_close,
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
            patch("areyouok_telegram.jobs.conversations.post_cleanup_tasks", new=AsyncMock()) as mock_cleanup,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify session was closed, job was stopped, and cleanup was run
        mock_close.assert_called_once_with("test_encryption_key", context=mock_context, chat_session=mock_session)
        mock_stop.assert_called_once_with(mock_context)
        mock_cleanup.assert_called_once_with(context=mock_context, chat_session=mock_session)
