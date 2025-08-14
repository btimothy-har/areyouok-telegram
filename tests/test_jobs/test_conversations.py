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

from areyouok_telegram.jobs.conversations import ConversationJob
from areyouok_telegram.llms.chat import ReactionResponse
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

        mock_response = TextResponse(reasoning="Test reasoning", message_text="Hello!", reply_to_message_id=None)

        mock_message = MagicMock(spec=telegram.Message)

        with (
            patch(
                "areyouok_telegram.jobs.conversations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_encryption_key"),
            ),
            patch("areyouok_telegram.jobs.conversations.get_chat_session", new=AsyncMock(return_value=mock_session)),
            patch.object(job, "_prepare_conversation_input", new=AsyncMock(return_value=([], MagicMock()))),
            patch.object(job, "generate_response", new=AsyncMock(return_value=(mock_response, mock_message))) as mock_generate,
            patch("areyouok_telegram.jobs.conversations.log_bot_activity", new=AsyncMock()) as mock_log_activity,
            patch("areyouok_telegram.jobs.conversations.logfire.span"),
        ):
            await job._run(mock_context)

        # Verify response was generated and executed
        mock_generate.assert_called_once()

        # Verify bot activity was logged with reasoning
        mock_log_activity.assert_called_once_with(
            bot_id="bot123",
            chat_encryption_key="test_encryption_key",
            chat_id="123",
            chat_session=mock_session,
            timestamp=frozen_time,
            response_message=mock_message,
            reasoning="Test reasoning",
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
        
        from areyouok_telegram.llms.chat import ChatAgentDependencies
        mock_deps = MagicMock(spec=ChatAgentDependencies)

        with (
            patch("areyouok_telegram.jobs.conversations.run_agent_with_tracking", new=AsyncMock(return_value=mock_payload)),
            patch.object(job, "_execute_response", new=AsyncMock(return_value=mock_message))
        ):
            result = await job.generate_response(
                context=mock_context,
                chat_encryption_key="test_encryption_key",
                chat_session=mock_session,
                conversation_history=[],
                dependencies=mock_deps,
            )

        assert result == (mock_response, mock_message)

    @pytest.mark.asyncio
    async def test_generate_response_exception(self):
        """Test generate_response raises exceptions (no internal error handling)."""
        job = ConversationJob("123")

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        from areyouok_telegram.llms.chat import ChatAgentDependencies
        mock_deps = MagicMock(spec=ChatAgentDependencies)

        with patch(
            "areyouok_telegram.jobs.conversations.run_agent_with_tracking",
            new=AsyncMock(side_effect=Exception("Test error")),
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
            result = await job._execute_response(chat_encryption_key="test_encryption_key", context=mock_context, chat_session=MagicMock(), response=mock_response)

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

            result = await job._execute_response(chat_encryption_key="test_encryption_key", context=mock_context, chat_session=MagicMock(), response=mock_response)

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

            result = await job._execute_response(chat_encryption_key="test_encryption_key", context=mock_context, chat_session=MagicMock(), response=mock_response)

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

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch("areyouok_telegram.jobs.conversations.Context.get_by_session_id", new=AsyncMock(return_value=None)),
            patch.object(job, "_prepare_conversation_input", new=AsyncMock(return_value=([], MagicMock()))),
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

        mock_messages = [MagicMock()]
        mock_compressed = MagicMock()

        with (
            patch("areyouok_telegram.jobs.conversations.async_database") as mock_async_db,
            patch("areyouok_telegram.jobs.conversations.Context.get_by_session_id", new=AsyncMock(return_value=None)),
            patch.object(job, "_prepare_conversation_input", new=AsyncMock(return_value=(mock_messages, MagicMock()))),
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
        from unittest.mock import ANY
        from areyouok_telegram.data.models.context import ContextType
        mock_save.assert_called_once_with(
            chat_encryption_key="test_encryption_key",
            chat_id="123", 
            chat_session=mock_session,
            ctype=ContextType.SESSION,
            data=ANY
        )
        mock_close.assert_called_once_with(mock_session)
        mock_log_info.assert_called_once_with("Session session123 closed due to inactivity.")
