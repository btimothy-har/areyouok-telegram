"""Tests for the ConversationJob class and related functions."""

import hashlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pydantic_ai
import pytest
from freezegun import freeze_time
from telegram.constants import ReactionEmoji

from areyouok_telegram.agent import ChatAgentDependencies
from areyouok_telegram.agent.responses import DoNothingResponse
from areyouok_telegram.agent.responses import ReactionResponse
from areyouok_telegram.agent.responses import TextResponse
from areyouok_telegram.jobs.conversations import JOB_LOCK
from areyouok_telegram.jobs.conversations import ConversationJob
from areyouok_telegram.jobs.conversations import schedule_conversation_job
from areyouok_telegram.jobs.exceptions import NoActiveSessionError


@pytest.fixture
def mock_job(mock_session):
    """Create a mock ConversationJob with pre-patched _get_active_session."""
    job = ConversationJob("123456")

    # Pre-patch _get_active_session to return the mock_session
    with patch.object(job, "_get_active_session", return_value=mock_session):
        yield job


@pytest.fixture
def mock_input_message():
    """Create a mock message conversion that returns proper ModelMessage objects."""
    with patch("areyouok_telegram.agent.convert_telegram_message_to_model_message") as mock_convert:
        # Create a proper ModelRequest message
        model_request = pydantic_ai.messages.ModelRequest(
            parts=[
                pydantic_ai.messages.UserPromptPart(
                    content='{"text": "Hello", "message_id": "123", "timestamp": "0 seconds ago"}',
                    timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
        mock_convert.return_value = model_request
        yield mock_convert


@pytest.fixture
def mock_agent_run():
    """Create a mock for chat_agent.run with configurable response."""
    with patch("areyouok_telegram.agent.chat_agent.run") as mock_run:
        # Default to TextResponse, but can be overridden in tests
        mock_result = MagicMock()
        mock_result.data = TextResponse(reasoning="Default test reasoning", message_text="Default test response")
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_text_response(mock_private_message):
    """Create a mock TextResponse object."""
    # Create a mock TextResponse with proper execute method
    mock_response = MagicMock(spec=TextResponse)
    mock_response.reasoning = "Default test reasoning"
    mock_response.message_text = "Default test response"
    mock_response.reply_to_message_id = None
    mock_response.response_type = "TextResponse"

    # Configure execute method to return proper telegram message
    bot_message = mock_private_message
    bot_message.date = datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC)
    mock_response.execute = AsyncMock(return_value=bot_message)

    return mock_response


@pytest.fixture
def mock_reaction_response(mock_message_reaction):
    """Create a mock ReactionResponse object."""
    # Create a mock ReactionResponse with proper execute method
    mock_response = MagicMock(spec=ReactionResponse)
    mock_response.reasoning = "Default test reasoning"
    mock_response.react_to_message_id = "123"
    mock_response.emoji = ReactionEmoji.THUMBS_UP
    mock_response.response_type = "ReactionResponse"

    # Configure execute method to return proper telegram reaction
    bot_reaction = mock_message_reaction
    bot_reaction.date = datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC)
    mock_response.execute = AsyncMock(return_value=bot_reaction)

    return mock_response


@pytest.fixture
def mock_do_nothing_response():
    """Create a mock DoNothingResponse object."""
    # Create a mock DoNothingResponse with proper execute method
    mock_response = MagicMock(spec=DoNothingResponse)
    mock_response.reasoning = "Default test reasoning"
    mock_response.response_type = "DoNothingResponse"

    # Configure execute method to return None
    mock_response.execute = AsyncMock(return_value=None)

    return mock_response


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

        # No active session
        with patch.object(job, "_get_active_session", return_value=None):
            with pytest.raises(NoActiveSessionError) as exc_info:
                await job.run(context)

            assert exc_info.value.chat_id == "123456"
            assert job._run_count == 1

    @pytest.mark.asyncio
    async def test_run_bot_has_responded(self, mock_job, mock_session):
        """Test run when bot has already responded."""
        context = MagicMock()

        # Configure mock session where bot has responded
        mock_session.has_bot_responded = True

        with patch.object(mock_job, "_generate_response") as mock_generate:
            await mock_job.run(context)

            # Should increment run count
            assert mock_job._run_count == 1

            # _generate_response should not be called since bot has responded
            mock_generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_calls_generate_response(self, mock_job, mock_session, mock_async_database_session):
        """Test run calls _generate_response when bot has not responded."""
        context = MagicMock()

        # Configure mock session with messages
        mock_session.has_bot_responded = False
        mock_session.get_messages = AsyncMock(return_value=[MagicMock()])

        with patch.object(mock_job, "_generate_response") as mock_generate:
            await mock_job.run(context)

            # Should increment run count
            assert mock_job._run_count == 1

            # Should call generate_response
            mock_generate.assert_called_once_with(mock_async_database_session, context, mock_session)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_input_message")
    async def test_generate_response_with_text_response(
        self, mock_job, mock_session, mock_agent_run, mock_text_response
    ):
        """Test _generate_response when agent returns a TextResponse."""

        # Mock agent run to return a TextResponse
        mock_agent_run.return_value.data = mock_text_response

        # Use mock messages from fixtures
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100

        msg2 = MagicMock()
        msg2.date = datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC)
        msg2.message_id = 101

        messages = [msg2, msg1]  # Out of order

        # Mock context
        context = MagicMock()
        context.bot.id = 999999

        # Mock connection
        conn = AsyncMock()

        # Use mock session from fixture
        mock_session.get_messages = AsyncMock(return_value=messages)

        # Configure agent to return the mock TextResponse
        mock_agent_run.return_value.data = mock_text_response

        # The mock_text_response fixture already provides the bot response
        bot_response = mock_text_response.execute.return_value

        with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
            result = await mock_job._generate_response(conn, context, mock_session)

            assert result is True
            assert mock_job._last_response == "TextResponse"

            # Verify agent was called correctly
            mock_agent_run.assert_called_once()
            call_args = mock_agent_run.call_args
            assert len(call_args.kwargs["message_history"]) == 2
            assert isinstance(call_args.kwargs["deps"], ChatAgentDependencies)
            assert call_args.kwargs["deps"].tg_chat_id == "123456"

            # Verify response was executed
            mock_text_response.execute.assert_called_once()
            execute_args = mock_text_response.execute.call_args
            assert execute_args.kwargs["db_connection"] == conn
            assert execute_args.kwargs["context"] == context
            assert execute_args.kwargs["chat_id"] == "123456"

            # Verify message was saved
            mock_new_or_update.assert_called_once_with(
                session=conn, user_id="999999", chat_id="123456", message=bot_response
            )

            # Verify session activities were updated
            mock_session.new_activity.assert_called_once_with(timestamp=mock_job._run_timestamp, is_user=False)
            mock_session.new_message.assert_called_once_with(timestamp=bot_response.date, is_user=False)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_input_message")
    async def test_generate_response_with_reaction_response(
        self, mock_job, mock_session, mock_agent_run, mock_reaction_response
    ):
        """Test _generate_response when agent returns a ReactionResponse."""

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        message.message_id = 100

        messages = [message]

        # Mock context
        context = MagicMock()
        context.bot.id = 999999

        # Mock connection
        conn = AsyncMock()

        # Use mock session from fixture
        mock_session.get_messages = AsyncMock(return_value=messages)

        # Configure agent to return the mock ReactionResponse
        mock_agent_run.return_value.data = mock_reaction_response

        # The mock_reaction_response fixture already provides the bot response
        bot_response = mock_reaction_response.execute.return_value

        with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
            result = await mock_job._generate_response(conn, context, mock_session)

            assert result is True
            assert mock_job._last_response == "ReactionResponse"

            # Verify agent was called correctly
            mock_agent_run.assert_called_once()
            call_args = mock_agent_run.call_args
            assert len(call_args.kwargs["message_history"]) == 1
            assert isinstance(call_args.kwargs["deps"], ChatAgentDependencies)
            assert call_args.kwargs["deps"].tg_chat_id == "123456"

            # Verify response was executed
            mock_reaction_response.execute.assert_called_once()
            execute_args = mock_reaction_response.execute.call_args
            assert execute_args.kwargs["db_connection"] == conn
            assert execute_args.kwargs["context"] == context
            assert execute_args.kwargs["chat_id"] == "123456"

            # Verify reaction was saved
            mock_new_or_update.assert_called_once_with(
                session=conn, user_id="999999", chat_id="123456", message=bot_response
            )

            # Verify session activity was updated
            mock_session.new_activity.assert_called_once_with(timestamp=mock_job._run_timestamp, is_user=False)
            # new_message should NOT be called for reactions
            mock_session.new_message.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_input_message")
    async def test_generate_response_with_do_nothing_response(
        self, mock_job, mock_session, mock_agent_run, mock_do_nothing_response
    ):
        """Test _generate_response when agent returns a DoNothingResponse."""

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        messages = [message]

        # Mock context
        context = MagicMock()

        # Mock connection
        conn = AsyncMock()

        # Use mock session from fixture
        mock_session.get_messages = AsyncMock(return_value=messages)

        # Configure agent to return the mock DoNothingResponse
        mock_agent_run.return_value.data = mock_do_nothing_response

        with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
            result = await mock_job._generate_response(conn, context, mock_session)

            assert result is False
            assert mock_job._last_response == "DoNothingResponse"

            # Verify agent was called correctly
            mock_agent_run.assert_called_once()
            call_args = mock_agent_run.call_args
            assert len(call_args.kwargs["message_history"]) == 1
            assert isinstance(call_args.kwargs["deps"], ChatAgentDependencies)
            assert call_args.kwargs["deps"].tg_chat_id == "123456"

            # Verify response was executed
            mock_do_nothing_response.execute.assert_called_once()
            execute_args = mock_do_nothing_response.execute.call_args
            assert execute_args.kwargs["db_connection"] == conn
            assert execute_args.kwargs["context"] == context
            assert execute_args.kwargs["chat_id"] == "123456"

            # Verify no message was saved
            mock_new_or_update.assert_not_called()

            # Verify session activity was still updated
            mock_session.new_activity.assert_called_once_with(timestamp=mock_job._run_timestamp, is_user=False)
            # new_message should NOT be called when no response
            mock_session.new_message.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_input_message")
    async def test_generate_response_agent_failure(self, mock_job, mock_session, mock_agent_run):
        """Test _generate_response when agent fails."""

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        messages = [message]

        # Mock context
        context = MagicMock()

        # Mock connection
        conn = AsyncMock()

        # Use mock session from fixture
        mock_session.get_messages = AsyncMock(return_value=messages)

        # Configure agent to fail
        mock_agent_run.side_effect = Exception("Agent error")

        result = await mock_job._generate_response(conn, context, mock_session)

        assert result is False
        # Last response should not be updated on failure
        assert mock_job._last_response is None

        # Verify agent was called
        mock_agent_run.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_input_message")
    async def test_generate_response_execution_failure(
        self, mock_job, mock_session, mock_agent_run, mock_text_response
    ):
        """Test _generate_response when response execution fails."""

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        messages = [message]

        # Mock context
        context = MagicMock()

        # Mock connection
        conn = AsyncMock()

        # Use mock session from fixture
        mock_session.get_messages = AsyncMock(return_value=messages)

        # Configure agent to return the mock TextResponse
        mock_agent_run.return_value.data = mock_text_response

        # Configure text response execution to fail
        mock_text_response.execute.side_effect = Exception("Network error")

        result = await mock_job._generate_response(conn, context, mock_session)

        assert result is False
        # Last response should be updated even if execution fails
        assert mock_job._last_response == "TextResponse"

        # Verify agent was called
        mock_agent_run.assert_called_once()
        # Verify execute was called
        mock_text_response.execute.assert_called_once()

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

    @pytest.mark.asyncio
    async def test_run_session_expires_no_user_activity(self, mock_job, mock_session):
        """Test run when session expires due to no user activity."""
        context = MagicMock()

        # Configure mock session with no user activity
        mock_session.has_bot_responded = False
        mock_session.last_user_activity = None

        with (
            patch.object(mock_job, "_generate_response") as mock_generate,
            patch.object(mock_job, "_stop") as mock_stop,
        ):
            await mock_job.run(context)

            # Should process messages normally when no last_user_activity
            mock_generate.assert_called_once()
            mock_stop.assert_not_called()
            mock_session.close_session.assert_not_called()

    @pytest.mark.asyncio
    @freeze_time("2025-07-31 12:00:00", tz_offset=0)
    async def test_run_session_expires_after_one_hour(self, mock_job, mock_session):
        """Test run when session expires after 1 hour of inactivity."""
        context = MagicMock()

        # Current time is frozen at 2025-07-31 12:00:00 UTC
        current_time = datetime(2025, 7, 31, 12, 0, 0, tzinfo=UTC)

        # Configure mock session with old user activity (more than 1 hour ago)
        mock_session.has_bot_responded = False
        mock_session.last_user_activity = current_time - timedelta(seconds=3601)  # 1 hour and 1 second ago

        with (
            patch.object(mock_job, "_generate_response") as mock_generate,
            patch.object(mock_job, "_stop") as mock_stop,
            patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db_session,
        ):
            mock_db_session.return_value.__aenter__.return_value = AsyncMock()

            await mock_job.run(context)

            # Should process messages first
            mock_generate.assert_called_once()

            # Should then stop the job and close the session
            mock_stop.assert_called_once_with(context)
            mock_session.close_session.assert_called_once_with(
                session=mock_db_session.return_value.__aenter__.return_value,
                timestamp=current_time,
            )

    @pytest.mark.asyncio
    @freeze_time("2025-07-31 12:00:00", tz_offset=0)
    async def test_run_session_not_expired_within_hour(self, mock_job, mock_session):
        """Test run when session is still active within the 1-hour window."""
        context = MagicMock()

        # Current time is frozen at 2025-07-31 12:00:00 UTC
        current_time = datetime(2025, 7, 31, 12, 0, 0, tzinfo=UTC)

        # Configure mock session with recent user activity (within 1 hour)
        mock_session.has_bot_responded = False
        mock_session.last_user_activity = current_time - timedelta(seconds=3599)  # 59 minutes and 59 seconds ago

        with (
            patch.object(mock_job, "_generate_response") as mock_generate,
            patch.object(mock_job, "_stop") as mock_stop,
        ):
            await mock_job.run(context)

            # Should process messages normally
            mock_generate.assert_called_once()

            # Should NOT stop the job or close the session
            mock_stop.assert_not_called()
            mock_session.close_session.assert_not_called()

    @pytest.mark.asyncio
    @freeze_time("2025-07-31 12:00:00", tz_offset=0)
    async def test_run_session_expires_exactly_one_hour(self, mock_job, mock_session):
        """Test run when session expires exactly after 1 hour."""
        context = MagicMock()

        # Current time is frozen at 2025-07-31 12:00:00 UTC
        current_time = datetime(2025, 7, 31, 12, 0, 0, tzinfo=UTC)

        # Configure mock session with user activity exactly 1 hour ago
        mock_session.has_bot_responded = False
        mock_session.last_user_activity = current_time - timedelta(seconds=3600)  # Exactly 1 hour ago

        with (
            patch.object(mock_job, "_generate_response") as mock_generate,
            patch.object(mock_job, "_stop") as mock_stop,
        ):
            await mock_job.run(context)

            # Should process messages normally (boundary condition: not > 1 hour)
            mock_generate.assert_called_once()

            # Should NOT stop the job (3600 seconds is not > 3600)
            mock_stop.assert_not_called()
            mock_session.close_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_job_success(self):
        """Test _stop method successfully removes jobs."""
        job = ConversationJob("123456")
        context = MagicMock()

        # Mock existing jobs
        mock_job1 = MagicMock()
        mock_job1.schedule_removal = MagicMock()
        mock_job2 = MagicMock()
        mock_job2.schedule_removal = MagicMock()
        existing_jobs = [mock_job1, mock_job2]

        context.job_queue.get_jobs_by_name.return_value = existing_jobs

        # Clear any existing locks
        if str(job.chat_id) in JOB_LOCK:
            del JOB_LOCK[str(job.chat_id)]

        await job._stop(context)

        # Should check for existing jobs with correct name
        context.job_queue.get_jobs_by_name.assert_called_once_with("conversation_processor:123456")

        # Should schedule removal for all existing jobs
        mock_job1.schedule_removal.assert_called_once()
        mock_job2.schedule_removal.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_job_no_existing_jobs(self):
        """Test _stop method when no jobs exist."""
        job = ConversationJob("123456")
        context = MagicMock()

        # No existing jobs
        context.job_queue.get_jobs_by_name.return_value = []

        # Clear any existing locks
        if str(job.chat_id) in JOB_LOCK:
            del JOB_LOCK[str(job.chat_id)]

        await job._stop(context)

        # Should check for existing jobs
        context.job_queue.get_jobs_by_name.assert_called_once_with("conversation_processor:123456")

        # No schedule_removal calls should be made (no jobs to remove)

    @pytest.mark.asyncio
    async def test_stop_job_with_job_lock(self):
        """Test _stop method properly uses job lock for thread safety."""
        job = ConversationJob("123456")
        context = MagicMock()

        mock_job = MagicMock()
        mock_job.schedule_removal = MagicMock()
        context.job_queue.get_jobs_by_name.return_value = [mock_job]

        # Verify lock is used
        lock_acquired = False
        original_acquire = JOB_LOCK[str(job.chat_id)].acquire

        async def mock_acquire():
            nonlocal lock_acquired
            lock_acquired = True
            return await original_acquire()

        with patch.object(JOB_LOCK[str(job.chat_id)], "acquire", side_effect=mock_acquire):
            await job._stop(context)

        # Lock should have been acquired
        assert lock_acquired
        mock_job.schedule_removal.assert_called_once()


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

        await schedule_conversation_job(context, chat_id, interval=10)

        # Should check for existing jobs
        context.job_queue.get_jobs_by_name.assert_called_once_with("conversation_processor:123456")

        # Should schedule the job
        context.job_queue.run_repeating.assert_called_once()
        call_args = context.job_queue.run_repeating.call_args

        assert call_args.kwargs["interval"] == 10
        assert call_args.kwargs["first"] == 5
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

        await schedule_conversation_job(context, chat_id, interval=60)

        # Should schedule with custom interval
        call_args = context.job_queue.run_repeating.call_args
        assert call_args.kwargs["interval"] == 60
        assert call_args.kwargs["first"] == 30
