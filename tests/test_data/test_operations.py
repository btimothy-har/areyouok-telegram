"""Tests for data/operations.py."""

from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram

from areyouok_telegram.data import operations as data_operations
from areyouok_telegram.data.models.guided_sessions import GuidedSessionType


class TestGetOrCreateActiveSession:
    """Test the get_or_create_active_session function."""

    @pytest.mark.asyncio
    async def test_get_existing_active_session(self):
        """Test retrieving an existing active session."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.data.operations.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_session)
            ) as mock_get_active:
                result = await data_operations.get_or_create_active_session(chat_id="chat123")

        assert result == mock_session
        mock_get_active.assert_called_once_with(mock_db_conn, chat_id="chat123")

    @pytest.mark.asyncio
    async def test_create_new_session_when_none_exists(self, frozen_time):
        """Test creating a new session when none exists."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.Sessions.get_active_session",
                    new=AsyncMock(return_value=None)
                ) as mock_get_active,
                patch(
                    "areyouok_telegram.data.operations.Sessions.create_session",
                    new=AsyncMock(return_value=mock_session)
                ) as mock_create,
            ):
                result = await data_operations.get_or_create_active_session(
                    chat_id="chat123",
                    timestamp=frozen_time
                )

        assert result == mock_session
        mock_get_active.assert_called_once_with(mock_db_conn, chat_id="chat123")
        mock_create.assert_called_once_with(mock_db_conn, chat_id="chat123", timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_no_create_when_flag_false(self):
        """Test not creating session when create_if_not_exists is False."""
        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.Sessions.get_active_session",
                    new=AsyncMock(return_value=None)
                ) as mock_get_active,
                patch(
                    "areyouok_telegram.data.operations.Sessions.create_session",
                    new=AsyncMock()
                ) as mock_create,
            ):
                result = await data_operations.get_or_create_active_session(
                    chat_id="chat123",
                    create_if_not_exists=False
                )

        assert result is None
        mock_get_active.assert_called_once_with(mock_db_conn, chat_id="chat123")
        mock_create.assert_not_called()


class TestGetOrCreateGuidedSession:
    """Test the get_or_create_guided_session function."""

    @pytest.mark.asyncio
    async def test_get_existing_guided_session(self):
        """Test retrieving an existing guided session."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_guided_session = MagicMock()

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.data.operations.GuidedSessions.get_by_chat_id",
                new=AsyncMock(return_value=[mock_guided_session])
            ) as mock_get_by_chat:
                result = await data_operations.get_or_create_guided_session(
                    chat_id="chat123",
                    session=mock_session,
                    stype=GuidedSessionType.ONBOARDING
                )

        assert result == mock_guided_session
        mock_get_by_chat.assert_called_once_with(
            mock_db_conn,
            chat_id="chat123",
            session_type=GuidedSessionType.ONBOARDING.value
        )

    @pytest.mark.asyncio
    async def test_create_new_guided_session(self):
        """Test creating a new guided session when none exists."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_guided_session = MagicMock()

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.GuidedSessions.get_by_chat_id",
                    new=AsyncMock(return_value=[])
                ) as mock_get_by_chat,
                patch(
                    "areyouok_telegram.data.operations.GuidedSessions.start_new_session",
                    new=AsyncMock()
                ) as mock_start_new,
                patch(
                    "areyouok_telegram.data.operations.GuidedSessions.get_by_chat_session",
                    new=AsyncMock(return_value=[mock_guided_session])
                ) as mock_get_by_session,
            ):
                result = await data_operations.get_or_create_guided_session(
                    chat_id="chat123",
                    session=mock_session,
                    stype=GuidedSessionType.ONBOARDING
                )

        assert result == mock_guided_session
        mock_get_by_chat.assert_called_once()
        mock_start_new.assert_called_once_with(
            mock_db_conn,
            chat_id="chat123",
            chat_session="session123",
            session_type=GuidedSessionType.ONBOARDING.value
        )
        mock_get_by_session.assert_called_once_with(
            mock_db_conn,
            chat_session="session123",
            session_type=GuidedSessionType.ONBOARDING.value
        )

    @pytest.mark.asyncio
    async def test_no_create_when_flag_false(self):
        """Test not creating guided session when create_if_not_exists is False."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.GuidedSessions.get_by_chat_id",
                    new=AsyncMock(return_value=[])
                ) as mock_get_by_chat,
                patch(
                    "areyouok_telegram.data.operations.GuidedSessions.start_new_session",
                    new=AsyncMock()
                ) as mock_start_new,
            ):
                result = await data_operations.get_or_create_guided_session(
                    chat_id="chat123",
                    session=mock_session,
                    stype=GuidedSessionType.ONBOARDING,
                    create_if_not_exists=False
                )

        assert result is None
        mock_get_by_chat.assert_called_once()
        mock_start_new.assert_not_called()


class TestNewSessionEvent:
    """Test the new_session_event function."""

    @pytest.mark.asyncio
    async def test_new_message_event(self, frozen_time):
        """Test logging a new message event."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_session.chat_id = "chat456"
        mock_session.session_start = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.new_message = AsyncMock()
        mock_session.new_activity = AsyncMock()

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "encryption_key"

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.date = frozen_time
        mock_message.edit_date = None
        mock_message.message_id = 123

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.Chats.get_by_id",
                    new=AsyncMock(return_value=mock_chat)
                ) as mock_get_chat,
                patch(
                    "areyouok_telegram.data.operations.Messages.new_or_update",
                    new=AsyncMock()
                ) as mock_new_or_update,
                patch(
                    "areyouok_telegram.data.operations.extract_media_from_telegram_message",
                    new=AsyncMock(return_value=0)
                ) as mock_extract_media,
            ):
                await data_operations.new_session_event(
                    session=mock_session,
                    message=mock_message,
                    user_id="user789",
                    is_user=True,
                    reasoning="Test reasoning"
                )

        mock_get_chat.assert_called_once_with(mock_db_conn, chat_id="chat456")
        mock_new_or_update.assert_called_once_with(
            mock_db_conn,
            user_encryption_key="encryption_key",
            user_id="user789",
            chat_id="chat456",
            message=mock_message,
            session_key="session123",
            reasoning="Test reasoning"
        )
        mock_session.new_message.assert_called_once_with(mock_db_conn, timestamp=frozen_time, is_user=True)
        mock_extract_media.assert_called_once_with(
            mock_db_conn,
            "encryption_key",
            message=mock_message,
            session_id="session123"
        )

    @pytest.mark.asyncio
    async def test_new_reaction_event(self, frozen_time):
        """Test logging a new reaction event."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_session.chat_id = "chat456"
        mock_session.session_start = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.new_activity = AsyncMock()

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "encryption_key"

        mock_reaction = MagicMock(spec=telegram.MessageReactionUpdated)
        mock_reaction.date = frozen_time

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.Chats.get_by_id",
                    new=AsyncMock(return_value=mock_chat)
                ) as mock_get_chat,
                patch(
                    "areyouok_telegram.data.operations.Messages.new_or_update",
                    new=AsyncMock()
                ) as mock_new_or_update,
            ):
                await data_operations.new_session_event(
                    session=mock_session,
                    message=mock_reaction,
                    user_id="user789",
                    is_user=False
                )

        mock_get_chat.assert_called_once_with(mock_db_conn, chat_id="chat456")
        mock_new_or_update.assert_called_once_with(
            mock_db_conn,
            user_encryption_key="encryption_key",
            user_id="user789",
            chat_id="chat456",
            message=mock_reaction,
            session_key="session123",
            reasoning=None
        )
        mock_session.new_activity.assert_called_once_with(mock_db_conn, timestamp=frozen_time, is_user=False)

    @pytest.mark.asyncio
    async def test_system_user_no_activity_log(self, frozen_time):
        """Test that system user messages don't log session activity."""
        from areyouok_telegram.data.models.chat_event import SYSTEM_USER_ID

        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_session.chat_id = "chat456"
        mock_session.session_start = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.new_message = AsyncMock()
        mock_session.new_activity = AsyncMock()

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "encryption_key"

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.date = frozen_time
        mock_message.edit_date = None

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.Chats.get_by_id",
                    new=AsyncMock(return_value=mock_chat)
                ),
                patch(
                    "areyouok_telegram.data.operations.Messages.new_or_update",
                    new=AsyncMock()
                ),
                patch(
                    "areyouok_telegram.data.operations.extract_media_from_telegram_message",
                    new=AsyncMock(return_value=0)
                ),
            ):
                await data_operations.new_session_event(
                    session=mock_session,
                    message=mock_message,
                    user_id=SYSTEM_USER_ID,
                    is_user=False
                )

        # Verify no session activity was logged for system user
        mock_session.new_message.assert_not_called()
        mock_session.new_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_media_handling(self, frozen_time):
        """Test handling of media messages."""
        mock_session = MagicMock()
        mock_session.session_id = "session123"
        mock_session.chat_id = "chat456"
        mock_session.session_start = datetime(2024, 1, 1, tzinfo=UTC)
        mock_session.new_message = AsyncMock()

        mock_chat = MagicMock()
        mock_chat.retrieve_key.return_value = "encryption_key"

        mock_message = MagicMock(spec=telegram.Message)
        mock_message.date = frozen_time
        mock_message.edit_date = None
        mock_message.message_id = 123

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with (
                patch(
                    "areyouok_telegram.data.operations.Chats.get_by_id",
                    new=AsyncMock(return_value=mock_chat)
                ),
                patch(
                    "areyouok_telegram.data.operations.Messages.new_or_update",
                    new=AsyncMock()
                ),
                patch(
                    "areyouok_telegram.data.operations.extract_media_from_telegram_message",
                    new=AsyncMock(return_value=2)
                ) as mock_extract_media,
                patch(
                    "areyouok_telegram.data.operations.handle_unsupported_media",
                    new=AsyncMock()
                ) as mock_handle_unsupported,
            ):
                await data_operations.new_session_event(
                    session=mock_session,
                    message=mock_message,
                    user_id="user789",
                    is_user=True
                )

        mock_extract_media.assert_called_once()
        mock_handle_unsupported.assert_called_once_with(
            mock_db_conn,
            chat_id="chat456",
            message_id=123
        )


class TestCloseChatSession:
    """Test the close_chat_session function."""

    @pytest.mark.asyncio
    async def test_close_session_success(self, frozen_time):
        """Test successfully closing a chat session."""
        mock_session = MagicMock()
        mock_session.chat_id = "chat123"
        mock_session.close_session = AsyncMock()

        mock_guided_session = MagicMock()
        mock_guided_session.is_active = True
        mock_guided_session.inactivate = AsyncMock()

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=[mock_guided_session])
            ) as mock_get_guided:
                await data_operations.close_chat_session(chat_session=mock_session)

        mock_get_guided.assert_called_once_with(
            chat_id="chat123",
            session=mock_session,
            create_if_not_exists=False
        )
        mock_guided_session.inactivate.assert_called_once_with(mock_db_conn, timestamp=frozen_time)
        mock_session.close_session.assert_called_once_with(mock_db_conn, timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_close_session_no_guided_sessions(self, frozen_time):
        """Test closing session when no guided sessions exist."""
        mock_session = MagicMock()
        mock_session.chat_id = "chat123"
        mock_session.close_session = AsyncMock()

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=None)
            ) as mock_get_guided:
                await data_operations.close_chat_session(chat_session=mock_session)

        mock_get_guided.assert_called_once_with(
            chat_id="chat123",
            session=mock_session,
            create_if_not_exists=False
        )
        mock_session.close_session.assert_called_once_with(mock_db_conn, timestamp=frozen_time)

    @pytest.mark.asyncio
    async def test_close_session_inactive_guided_sessions(self, frozen_time):
        """Test closing session when guided sessions are already inactive."""
        mock_session = MagicMock()
        mock_session.chat_id = "chat123"
        mock_session.close_session = AsyncMock()

        mock_guided_session = MagicMock()
        mock_guided_session.is_active = False
        mock_guided_session.inactivate = AsyncMock()

        with patch("areyouok_telegram.data.operations.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            with patch(
                "areyouok_telegram.data.operations.get_or_create_guided_session",
                new=AsyncMock(return_value=[mock_guided_session])
            ):
                await data_operations.close_chat_session(chat_session=mock_session)

        # Should not inactivate already inactive sessions
        mock_guided_session.inactivate.assert_not_called()
        mock_session.close_session.assert_called_once_with(mock_db_conn, timestamp=frozen_time)
