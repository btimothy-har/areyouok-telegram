"""Tests for the ConversationJob class and related functions."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.constants import ReactionEmoji

from areyouok_telegram.agent import AgentDependencies
from areyouok_telegram.agent.responses import DoNothingResponse
from areyouok_telegram.agent.responses import ReactionResponse
from areyouok_telegram.agent.responses import TextResponse
from areyouok_telegram.jobs.conversations import JOB_LOCK
from areyouok_telegram.jobs.conversations import ConversationJob
from areyouok_telegram.jobs.conversations import schedule_conversation_job
from areyouok_telegram.jobs.exceptions import NoActiveSessionError


class TestConversationJob:
    """Test the ConversationJob class."""

    def test_init(self):
        """Test initialization of ConversationJob."""
        job = ConversationJob("123456")

        assert job.chat_id == "123456"
        assert job._last_response is None
        assert job._run_count == 0
        assert isinstance(job._run_timestamp, datetime)

    def test_name_property(self):
        """Test the name property."""
        job = ConversationJob("123456")

        assert job.name == "conversation_processor:123456"

    def test_id_property(self):
        """Test the _id property."""
        job = ConversationJob("123456")

        # Should be MD5 hash of the name
        expected_id = hashlib.md5(job.name.encode()).hexdigest()
        assert job._id == expected_id

    def test_sleep_time_property(self):
        """Test the sleep_time property with exponential backoff."""
        job = ConversationJob("123456")

        # Initial run count is 0
        assert job.sleep_time == 1  # 2^0 = 1

        job._run_count = 1
        assert job.sleep_time == 2  # 2^1 = 2

        job._run_count = 2
        assert job.sleep_time == 4  # 2^2 = 4

        job._run_count = 3
        assert job.sleep_time == 8  # 2^3 = 8

        job._run_count = 4
        assert job.sleep_time == 15  # min(2^4=16, 15) = 15

        job._run_count = 5
        assert job.sleep_time == 15  # min(2^5=32, 15) = 15

    @pytest.mark.asyncio
    async def test_get_active_session(self):
        """Test the _get_active_session method."""
        job = ConversationJob("123456")
        mock_conn = MagicMock()
        mock_session = MagicMock()

        with patch("areyouok_telegram.data.Sessions.get_active_session", return_value=mock_session) as mock_get:
            result = await job._get_active_session(mock_conn)

            assert result == mock_session
            mock_get.assert_called_once_with(mock_conn, "123456")

    @pytest.mark.asyncio
    async def test_run_no_active_session(self):
        """Test run when there's no active session raises exception."""
        job = ConversationJob("123456")
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # No active session
            with patch.object(job, "_get_active_session", return_value=None):
                with pytest.raises(NoActiveSessionError) as exc_info:
                    await job.run(context)

                assert exc_info.value.chat_id == "123456"
                assert job._run_count == 1

    @pytest.mark.asyncio
    async def test_run_bot_has_responded(self):
        """Test run when bot has already responded."""
        job = ConversationJob("123456")
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # Mock active session where bot has responded
            mock_session = MagicMock()
            mock_session.has_bot_responded = True

            with patch.object(job, "_get_active_session", return_value=mock_session):
                await job.run(context)

                # Should increment run count
                assert job._run_count == 1

                # _generate_response should not be called since bot has responded

    @pytest.mark.asyncio
    async def test_run_with_action_taken(self):
        """Test run when action is taken (message sent)."""
        job = ConversationJob("123456")
        job._run_count = 5  # Set high run count
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # Mock active session with messages
            mock_session = MagicMock()
            mock_session.has_bot_responded = False
            mock_session.get_messages = AsyncMock(return_value=[MagicMock()])

            with patch.object(job, "_get_active_session", return_value=mock_session):
                with patch.object(job, "_generate_response", return_value=True) as mock_generate:
                    with patch("asyncio.sleep") as mock_sleep:
                        await job.run(context)

                        # Should reset run count when action taken
                        assert job._run_count == 0

                        # Should not sleep
                        mock_sleep.assert_not_called()

                        # Should call generate_response
                        mock_generate.assert_called_once_with(mock_conn, context, mock_session)

    @pytest.mark.asyncio
    async def test_run_with_no_action_taken(self):
        """Test run when no action is taken."""
        job = ConversationJob("123456")
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # Mock active session with messages
            mock_session = MagicMock()
            mock_session.has_bot_responded = False
            mock_session.get_messages = AsyncMock(return_value=[MagicMock()])

            with patch.object(job, "_get_active_session", return_value=mock_session):
                with patch.object(job, "_generate_response", return_value=False) as mock_generate:
                    with patch("asyncio.sleep") as mock_sleep:
                        await job.run(context)

                        # Should increment run count
                        assert job._run_count == 1

                        # Should sleep with exponential backoff
                        mock_sleep.assert_called_once_with(2)  # 2^1 = 2

                        # Should call generate_response
                        mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_response_with_text_response(self, mock_private_message, mock_session):
        """Test _generate_response when agent returns a TextResponse."""
        job = ConversationJob("123456")

        # Use mock messages from fixtures
        msg1 = mock_private_message
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100

        msg2 = MagicMock()
        msg2.date = datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC)
        msg2.message_id = 101

        messages = [msg2, msg1]  # Out of order

        # Mock context
        context = MagicMock()
        bot_response = mock_private_message  # Use fixture for bot response
        bot_response.date = datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC)
        context.bot.id = 999999

        # Mock connection
        conn = AsyncMock()

        # Use mock session from fixture
        mock_session.get_messages = AsyncMock(return_value=messages)

        # Mock agent response
        text_response = TextResponse(
            reasoning="User seems worried",
            message_text="Are you ok? 🤔",
            reply_to_message_id="101"
        )

        mock_agent_result = MagicMock()
        mock_agent_result.data = text_response

        with patch("areyouok_telegram.agent.areyouok_agent.run", return_value=mock_agent_result) as mock_agent_run:
            with patch("areyouok_telegram.agent.convert_telegram_message_to_model_message"):
                with patch.object(TextResponse, "execute", AsyncMock(return_value=bot_response)) as mock_execute:
                    with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
                        result = await job._generate_response(conn, context, mock_session)

                        assert result is True
                        assert job._last_response == "TextResponse"

                        # Verify agent was called correctly
                        mock_agent_run.assert_called_once()
                        call_args = mock_agent_run.call_args
                        assert len(call_args.kwargs["message_history"]) == 2
                        assert isinstance(call_args.kwargs["deps"], AgentDependencies)
                        assert call_args.kwargs["deps"].tg_chat_id == "123456"

                        # Verify response was executed
                        mock_execute.assert_called_once()
                        execute_args = mock_execute.call_args
                        assert execute_args.kwargs["db_connection"] == conn
                        assert execute_args.kwargs["context"] == context
                        assert execute_args.kwargs["chat_id"] == "123456"

                        # Verify message was saved
                        mock_new_or_update.assert_called_once_with(
                            session=conn,
                            user_id="999999",
                            chat_id="123456",
                            message=bot_response
                        )

                        # Verify session activities were updated
                        mock_session.new_activity.assert_called_once_with(
                            timestamp=bot_response.date,
                            activity_type="bot"
                        )
                        mock_session.new_message.assert_called_once_with(
                            timestamp=bot_response.date,
                            message_type="bot"
                        )

    @pytest.mark.asyncio
    async def test_generate_response_with_reaction_response(self):
        """Test _generate_response when agent returns a ReactionResponse."""
        job = ConversationJob("123456")

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        message.message_id = 100

        # Mock context
        context = MagicMock()
        context.bot.id = 999999

        # Mock connection
        conn = AsyncMock()

        # Mock active session
        mock_session = MagicMock()
        mock_session.get_messages = AsyncMock(return_value=[message])
        mock_session.new_activity = AsyncMock()

        # Mock agent response
        reaction_response = ReactionResponse(
            reasoning="User message is positive",
            react_to_message_id="100",
            emoji=ReactionEmoji.THUMBS_UP
        )

        # Mock reaction result
        reaction_result = telegram.MessageReactionUpdated(
            chat=MagicMock(),
            message_id=100,
            date=datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC),
            old_reaction=(),
            new_reaction=(telegram.ReactionTypeEmoji(emoji=ReactionEmoji.THUMBS_UP),),
            user=MagicMock()
        )

        mock_agent_result = MagicMock()
        mock_agent_result.data = reaction_response

        with patch("areyouok_telegram.agent.areyouok_agent.run", return_value=mock_agent_result):
            with patch("areyouok_telegram.agent.convert_telegram_message_to_model_message"):
                with patch.object(ReactionResponse, "execute", AsyncMock(return_value=reaction_result)) as mock_execute:
                    with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
                        result = await job._generate_response(conn, context, mock_session)

                        assert result is True
                        assert job._last_response == "ReactionResponse"

                        # Verify response was executed
                        mock_execute.assert_called_once()
                        execute_args = mock_execute.call_args
                        assert execute_args.kwargs["db_connection"] == conn
                        assert execute_args.kwargs["context"] == context
                        assert execute_args.kwargs["chat_id"] == "123456"

                        # Verify reaction was saved
                        mock_new_or_update.assert_called_once_with(
                            session=conn,
                            user_id="999999",
                            chat_id="123456",
                            message=reaction_result
                        )

                        # Verify session activity was updated
                        mock_session.new_activity.assert_called_once_with(
                            timestamp=reaction_result.date,
                            activity_type="bot"
                        )

    @pytest.mark.asyncio
    async def test_generate_response_with_do_nothing_response(self):
        """Test _generate_response when agent returns a DoNothingResponse."""
        job = ConversationJob("123456")

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Mock context
        context = MagicMock()

        # Mock connection
        conn = AsyncMock()

        # Mock active session
        mock_session = MagicMock()
        mock_session.get_messages = AsyncMock(return_value=[message])
        mock_session.new_activity = AsyncMock()

        # Mock agent response
        do_nothing_response = DoNothingResponse(
            reasoning="No response needed at this time"
        )

        mock_agent_result = MagicMock()
        mock_agent_result.data = do_nothing_response

        with patch("areyouok_telegram.agent.areyouok_agent.run", return_value=mock_agent_result):
            with patch("areyouok_telegram.agent.convert_telegram_message_to_model_message"):
                with patch.object(DoNothingResponse, "execute", AsyncMock(return_value=None)) as mock_execute:
                    with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
                        result = await job._generate_response(conn, context, mock_session)

                        assert result is False
                        assert job._last_response == "DoNothingResponse"

                        # Verify response was executed
                        mock_execute.assert_called_once()

                        # Verify no message was saved
                        mock_new_or_update.assert_not_called()

                        # Verify no session activity was updated
                        mock_session.new_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_response_agent_failure(self):
        """Test _generate_response when agent fails."""
        job = ConversationJob("123456")

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Mock context
        context = MagicMock()

        # Mock connection
        conn = AsyncMock()

        # Mock active session
        mock_session = MagicMock()
        mock_session.get_messages = AsyncMock(return_value=[message])

        with patch("areyouok_telegram.agent.areyouok_agent.run", side_effect=Exception("Agent error")):
            with patch("areyouok_telegram.agent.convert_telegram_message_to_model_message"):
                result = await job._generate_response(conn, context, mock_session)

                assert result is False
                # Last response should not be updated on failure
                assert job._last_response is None

    @pytest.mark.asyncio
    async def test_generate_response_execution_failure(self):
        """Test _generate_response when response execution fails."""
        job = ConversationJob("123456")

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Mock context
        context = MagicMock()

        # Mock connection
        conn = AsyncMock()

        # Mock active session
        mock_session = MagicMock()
        mock_session.get_messages = AsyncMock(return_value=[message])

        # Mock agent response
        text_response = TextResponse(
            reasoning="Test",
            message_text="Test message"
        )

        mock_agent_result = MagicMock()
        mock_agent_result.data = text_response

        with patch("areyouok_telegram.agent.areyouok_agent.run", return_value=mock_agent_result):
            with patch("areyouok_telegram.agent.convert_telegram_message_to_model_message"):
                with patch.object(TextResponse, "execute", AsyncMock(side_effect=Exception("Network error"))):
                    result = await job._generate_response(conn, context, mock_session)

                    assert result is False
                    # Last response should be updated even if execution fails
                    assert job._last_response == "TextResponse"

    @pytest.mark.asyncio
    async def test_last_response_property(self):
        """Test the _last_response property."""
        job = ConversationJob("123456")

        # Should be None initially
        assert job._last_response is None

        # Should track the last response type when set
        job._last_response = "TextResponse"
        assert job._last_response == "TextResponse"

        job._last_response = "ReactionResponse"
        assert job._last_response == "ReactionResponse"


class TestScheduleConversationJob:
    """Test the schedule_conversation_job function."""

    @pytest.mark.asyncio
    async def test_schedule_new_job(self):
        """Test scheduling a new conversation job."""
        context = MagicMock()
        context.job_queue.get_jobs_by_name.return_value = []
        context.job_queue.run_repeating = MagicMock()

        chat_id = 123456

        # Clear any existing locks
        if str(chat_id) in JOB_LOCK:
            del JOB_LOCK[str(chat_id)]

        await schedule_conversation_job(context, chat_id, delay_seconds=10)

        # Should check for existing jobs
        context.job_queue.get_jobs_by_name.assert_called_once_with("conversation_processor:123456")

        # Should schedule the job
        context.job_queue.run_repeating.assert_called_once()
        call_args = context.job_queue.run_repeating.call_args

        assert call_args.kwargs["interval"] == 1
        assert call_args.kwargs["first"] == 10
        assert call_args.kwargs["name"] == "conversation_processor:123456"
        assert call_args.kwargs["chat_id"] == 123456
        assert call_args.kwargs["job_kwargs"]["id"] == "conversation_processor:123456"
        assert call_args.kwargs["job_kwargs"]["coalesce"] is True
        assert call_args.kwargs["job_kwargs"]["max_instances"] == 1

    @pytest.mark.asyncio
    async def test_schedule_existing_job(self):
        """Test attempting to schedule when job already exists."""
        context = MagicMock()
        context.job_queue.get_jobs_by_name.return_value = [MagicMock()]  # Existing job
        context.job_queue.run_repeating = MagicMock()

        chat_id = 123456

        await schedule_conversation_job(context, chat_id)

        # Should check for existing jobs
        context.job_queue.get_jobs_by_name.assert_called_once()

        # Should not schedule a new job
        context.job_queue.run_repeating.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_with_custom_delay(self):
        """Test scheduling with custom delay."""
        context = MagicMock()
        context.job_queue.get_jobs_by_name.return_value = []
        context.job_queue.run_repeating = MagicMock()

        chat_id = 789012

        # Clear any existing locks
        if str(chat_id) in JOB_LOCK:
            del JOB_LOCK[str(chat_id)]

        await schedule_conversation_job(context, chat_id, delay_seconds=60)

        # Should schedule with custom delay
        call_args = context.job_queue.run_repeating.call_args
        assert call_args.kwargs["first"] == 60
