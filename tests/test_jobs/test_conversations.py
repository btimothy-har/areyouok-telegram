"""Tests for jobs/conversations.py - minimal core functionality tests."""

from unittest.mock import AsyncMock, patch

import pytest

from areyouok_telegram.jobs.conversations import ConversationJob


class TestConversationJob:
    """Test the ConversationJob class core functionality."""

    def test_init(self):
        """Test ConversationJob initialization."""
        job = ConversationJob(chat_id=123)
        assert job.chat_id == 123
        assert job._bot_id is None

    def test_name_property(self):
        """Test name property generates correct format."""
        job = ConversationJob(chat_id=456)
        assert job.name == "conversation:456"

    @pytest.mark.asyncio
    async def test_run_job_no_chat_stops(self):
        """Test run_job stops when chat not found."""
        job = ConversationJob(chat_id=999)

        with (
            patch("areyouok_telegram.data.models.Chat.get_by_id", new=AsyncMock(return_value=None)),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
        ):
            await job.run_job()

            # Should stop when chat not found
        mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_job_no_active_session_stops(self, chat_factory, user_factory):
        """Test run_job stops when no active session."""
        job = ConversationJob(chat_id=123)
        mock_chat = chat_factory(id_value=123)
        mock_user = user_factory(id_value=1)

        with (
            patch("areyouok_telegram.data.models.Chat.get_by_id", new=AsyncMock(return_value=mock_chat)),
            patch("areyouok_telegram.data.models.User.get_by_id", new=AsyncMock(return_value=mock_user)),
            patch("areyouok_telegram.data.models.Session.get_sessions", new=AsyncMock(return_value=[])),
            patch.object(job, "stop", new=AsyncMock()) as mock_stop,
        ):
            await job.run_job()

            # Should stop when no active session
        mock_stop.assert_called_once()
