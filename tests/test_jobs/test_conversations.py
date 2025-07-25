"""Tests for the ConversationJob class and related functions."""

import hashlib
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from areyouok_telegram.jobs.conversations import JOB_LOCK
from areyouok_telegram.jobs.conversations import ConversationJob
from areyouok_telegram.jobs.conversations import schedule_conversation_job


class TestConversationJob:
    """Test the ConversationJob class."""

    def test_init(self):
        """Test initialization of ConversationJob."""
        job = ConversationJob("123456")

        assert job.chat_id == "123456"
        assert job._reply_lock is True
        assert job._run_count == 0

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
        """Test run when there's no active session."""
        job = ConversationJob("123456")
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # No active session
            mock_conn.__aenter__.return_value = mock_conn
            with patch.object(job, "_get_active_session", return_value=None):
                with patch("asyncio.sleep") as mock_sleep:
                    await job.run(context)

                    # Should increment run count
                    assert job._run_count == 1

                    # Should sleep with exponential backoff
                    mock_sleep.assert_called_once_with(2)  # 2^1 = 2

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
                with patch("asyncio.sleep") as mock_sleep:
                    await job.run(context)

                    # Should increment run count
                    assert job._run_count == 1

                    # Should sleep
                    mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 10:30:35", tz_offset=0)
    async def test_run_release_reply_lock_after_30_seconds(self):
        """Test that reply lock is released after 30 seconds."""
        job = ConversationJob("123456")
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # Mock active session with last message > 30 seconds ago
            mock_session = MagicMock()
            mock_session.has_bot_responded = False
            mock_session.last_user_message = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
            mock_session.get_messages = AsyncMock(return_value=[])

            with patch.object(job, "_get_active_session", return_value=mock_session):
                with patch("asyncio.sleep"):
                    await job.run(context)

                    # Reply lock should be released
                    assert job._reply_lock is False

    @pytest.mark.asyncio
    @freeze_time("2025-01-15 10:30:25", tz_offset=0)
    async def test_run_keep_reply_lock_before_30_seconds(self):
        """Test that reply lock is kept before 30 seconds."""
        job = ConversationJob("123456")
        context = MagicMock()

        with patch("areyouok_telegram.jobs.conversations.async_database_session") as mock_db:
            mock_conn = AsyncMock()
            mock_db.return_value.__aenter__.return_value = mock_conn

            # Mock active session with last message < 30 seconds ago
            mock_session = MagicMock()
            mock_session.has_bot_responded = False
            mock_session.last_user_message = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
            mock_session.get_messages = AsyncMock(return_value=[])

            with patch.object(job, "_get_active_session", return_value=mock_session):
                with patch("asyncio.sleep"):
                    await job.run(context)

                    # Reply lock should still be locked
                    assert job._reply_lock is True

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
            mock_session.last_user_message = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
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
                        mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_response_with_reply_lock(self):
        """Test _generate_response when reply lock is active."""
        job = ConversationJob("123456")
        job._reply_lock = True

        messages = [MagicMock()]
        result = await job._generate_response(MagicMock(), MagicMock(), messages)

        assert result is False

    @pytest.mark.asyncio
    async def test_generate_response_success(self):
        """Test successful message generation and sending."""
        job = ConversationJob("123456")
        job._reply_lock = False

        # Mock messages
        msg1 = MagicMock()
        msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        msg1.message_id = 100

        msg2 = MagicMock()
        msg2.date = datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC)
        msg2.message_id = 101

        messages = [msg2, msg1]  # Out of order

        # Mock context
        context = MagicMock()
        bot_response = MagicMock()
        bot_response.date = datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC)
        context.bot.send_message = AsyncMock(return_value=bot_response)
        context.bot.id = 999999

        # Mock connection
        conn = AsyncMock()

        # Mock active session
        mock_session = MagicMock()
        mock_session.new_message = AsyncMock()

        with patch.object(job, "_get_active_session", return_value=mock_session):
            with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
                result = await job._generate_response(conn, context, messages)

                assert result is True

                # Should send message to latest message
                context.bot.send_message.assert_called_once_with(
                    chat_id=123456, text="Are you ok? 🤔", reply_to_message_id=101
                )

                # Should save message to database
                mock_new_or_update.assert_called_once_with(
                    session=conn, user_id="999999", chat_id="123456", message=bot_response
                )

                # Should record bot message in session
                mock_session.new_message.assert_called_once_with(timestamp=bot_response.date, message_type="bot")

    @pytest.mark.asyncio
    async def test_generate_response_success_no_active_session_after_send(self):
        """Test successful message generation when active session disappears after sending."""
        job = ConversationJob("123456")
        job._reply_lock = False

        # Mock messages
        message = MagicMock()
        message.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        message.message_id = 100
        messages = [message]

        # Mock context
        context = MagicMock()
        bot_response = MagicMock()
        bot_response.date = datetime(2025, 1, 15, 10, 2, 0, tzinfo=UTC)
        context.bot.send_message = AsyncMock(return_value=bot_response)
        context.bot.id = 999999

        # Mock connection
        conn = AsyncMock()

        # Mock that active session is None after sending
        with patch.object(job, "_get_active_session", return_value=None):
            with patch("areyouok_telegram.data.Messages.new_or_update") as mock_new_or_update:
                result = await job._generate_response(conn, context, messages)

                assert result is True

                # Should still send message
                context.bot.send_message.assert_called_once()

                # Should save message to database
                mock_new_or_update.assert_called_once()

                # Should not try to record message in session (since none exists)
                # This is the branch that wasn't covered

    @pytest.mark.asyncio
    async def test_generate_response_send_failure(self):
        """Test _generate_response when sending fails."""
        job = ConversationJob("123456")
        job._reply_lock = False

        messages = [MagicMock(date=datetime.now(UTC), message_id=1)]

        # Mock context with failing bot
        context = MagicMock()
        context.bot.send_message = AsyncMock(side_effect=Exception("Network error"))

        result = await job._generate_response(MagicMock(), context, messages)

        assert result is False


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
