from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.handlers import on_edit_message
from areyouok_telegram.handlers import on_message_react
from areyouok_telegram.handlers import on_new_message
from areyouok_telegram.handlers.exceptions import NoEditedMessageError
from areyouok_telegram.handlers.exceptions import NoMessageError
from areyouok_telegram.handlers.exceptions import NoMessageReactionError


class TestNewMessageHandler:
    """Test suite for message handlers functionality."""

    @pytest.mark.asyncio
    async def test_on_new_message_with_existing_session(
        self, mock_async_database_session, mock_update_private_chat_new_message
    ):
        """Test on_new_message with existing active session."""
        mock_context = AsyncMock()

        # Mock an existing active session
        mock_session = MagicMock()
        mock_session.new_message = AsyncMock()

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=mock_session) as mock_get_active,
        ):
            # Act
            await on_new_message(mock_update_private_chat_new_message, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_new_message.effective_user.id,
                chat_id=mock_update_private_chat_new_message.effective_chat.id,
                message=mock_update_private_chat_new_message.message,
            )

            # Verify session management
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_private_chat_new_message.effective_chat.id)
            )
            mock_session.new_message.assert_called_once_with(mock_update_private_chat_new_message.message.date, "user")

    @pytest.mark.asyncio
    async def test_on_new_message_without_existing_session(
        self, mock_async_database_session, mock_update_private_chat_new_message
    ):
        """Test on_new_message without existing active session."""
        mock_context = AsyncMock()

        # Mock the created session
        mock_new_session = MagicMock()
        mock_new_session.new_message = AsyncMock()

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=None) as mock_get_active,
            patch(
                "areyouok_telegram.data.Sessions.create_session", return_value=mock_new_session
            ) as mock_create_session,
        ):
            # Act
            await on_new_message(mock_update_private_chat_new_message, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_new_message.effective_user.id,
                chat_id=mock_update_private_chat_new_message.effective_chat.id,
                message=mock_update_private_chat_new_message.message,
            )

            # Verify session management
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_private_chat_new_message.effective_chat.id)
            )
            mock_create_session.assert_called_once_with(
                mock_async_database_session,
                str(mock_update_private_chat_new_message.effective_chat.id),
                mock_update_private_chat_new_message.message.date,
            )
            mock_new_session.new_message.assert_called_once_with(
                mock_update_private_chat_new_message.message.date, "user"
            )

    @pytest.mark.asyncio
    async def test_no_message_received(self, mock_async_database_session, mock_update_empty):
        """Test on_new_message raises NoMessageError when no message is received."""
        mock_context = AsyncMock()

        with pytest.raises(NoMessageError) as exc_info:
            await on_new_message(mock_update_empty, mock_context)

        assert str(exc_info.value) == f"Expected to receive a new message in update: {mock_update_empty.update_id}"

        # Ensure no database operations were attempted
        mock_async_database_session.assert_not_called()


class TestEditMessageHandler:
    """Test suite for message edit handlers functionality."""

    @pytest.mark.asyncio
    async def test_on_edit_message_with_active_session_recent_message(
        self, mock_async_database_session, mock_update_private_chat_edited_message, mock_session
    ):
        """Test on_edit_message with active session and recent message (after session start)."""
        mock_context = AsyncMock()

        # Set session start to the message date (message is current, so should extend)
        mock_session.session_start = mock_update_private_chat_edited_message.edited_message.date

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=mock_session) as mock_get_active,
        ):
            # Act
            await on_edit_message(mock_update_private_chat_edited_message, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_edited_message.effective_user.id,
                chat_id=mock_update_private_chat_edited_message.effective_chat.id,
                message=mock_update_private_chat_edited_message.edited_message,
            )

            # Verify session was extended with edit_date
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_private_chat_edited_message.effective_chat.id)
            )
            mock_session.new_user_activity.assert_called_once_with(
                mock_update_private_chat_edited_message.edited_message.edit_date
            )

    @pytest.mark.asyncio
    async def test_on_edit_message_with_active_session_old_message(
        self, mock_async_database_session, mock_update_private_chat_edited_message, mock_session
    ):
        """Test on_edit_message with active session but old message (before session start)."""
        mock_context = AsyncMock()

        # Set session start after the message date (old message, should NOT extend)
        mock_session.session_start = mock_update_private_chat_edited_message.edited_message.date + timedelta(minutes=30)

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=mock_session) as mock_get_active,
        ):
            # Act
            await on_edit_message(mock_update_private_chat_edited_message, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_edited_message.effective_user.id,
                chat_id=mock_update_private_chat_edited_message.effective_chat.id,
                message=mock_update_private_chat_edited_message.edited_message,
            )

            # Verify session was NOT extended (old message)
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_private_chat_edited_message.effective_chat.id)
            )
            mock_session.new_user_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_edit_message_without_active_session(
        self, mock_async_database_session, mock_update_private_chat_edited_message
    ):
        """Test on_edit_message without active session (no session created for edits)."""
        mock_context = AsyncMock()

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=None) as mock_get_active,
            patch("areyouok_telegram.data.Sessions.create_session") as mock_create_session,
        ):
            # Act
            await on_edit_message(mock_update_private_chat_edited_message, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_private_chat_edited_message.effective_user.id,
                chat_id=mock_update_private_chat_edited_message.effective_chat.id,
                message=mock_update_private_chat_edited_message.edited_message,
            )

            # Verify no session was created for edits
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_private_chat_edited_message.effective_chat.id)
            )
            mock_create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_message_received(self, mock_async_database_session, mock_update_empty):
        """Test on_edit_message with the expected payload for an edited private message."""
        mock_context = AsyncMock()

        with pytest.raises(NoEditedMessageError) as exc_info:
            await on_edit_message(mock_update_empty, mock_context)

        assert str(exc_info.value) == f"Expected to receive an edited message in update: {mock_update_empty.update_id}"

        # Ensure no database operations were attempted
        mock_async_database_session.assert_not_called()


class TestMessageReactHandler:
    """Test suite for message reaction handlers functionality."""

    @pytest.mark.asyncio
    async def test_on_message_react_with_active_session_recent_message(
        self, mock_async_database_session, mock_update_message_reaction, mock_session
    ):
        """Test on_message_react with active session and recent message (after session start)."""
        mock_context = AsyncMock()

        # Set session start to the message date (message is current, so should record activity)
        mock_session.session_start = mock_update_message_reaction.message_reaction.date

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=mock_session) as mock_get_active,
        ):
            # Act
            await on_message_react(mock_update_message_reaction, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_message_reaction.effective_user.id,
                chat_id=mock_update_message_reaction.effective_chat.id,
                message=mock_update_message_reaction.message_reaction,
            )

            # Verify session was extended with reaction date
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_message_reaction.effective_chat.id)
            )
            mock_session.new_user_activity.assert_called_once_with(
                mock_update_message_reaction.message_reaction.date
            )

    @pytest.mark.asyncio
    async def test_on_message_react_with_active_session_old_message(
        self, mock_async_database_session, mock_update_message_reaction, mock_session
    ):
        """Test on_message_react with active session but old message (before session start)."""
        mock_context = AsyncMock()

        # Set session start after the message date (old message, should NOT record activity)
        mock_session.session_start = mock_update_message_reaction.message_reaction.date + timedelta(minutes=30)

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=mock_session) as mock_get_active,
        ):
            # Act
            await on_message_react(mock_update_message_reaction, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_message_reaction.effective_user.id,
                chat_id=mock_update_message_reaction.effective_chat.id,
                message=mock_update_message_reaction.message_reaction,
            )

            # Verify session was NOT extended (old message)
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_message_reaction.effective_chat.id)
            )
            mock_session.new_user_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_react_without_active_session(
        self, mock_async_database_session, mock_update_message_reaction
    ):
        """Test on_message_react without active session (no session created for reactions)."""
        mock_context = AsyncMock()

        with (
            patch("areyouok_telegram.data.Messages.new_or_update") as mock_messages_new_or_update,
            patch("areyouok_telegram.data.Sessions.get_active_session", return_value=None) as mock_get_active,
            patch("areyouok_telegram.data.Sessions.create_session") as mock_create_session,
        ):
            # Act
            await on_message_react(mock_update_message_reaction, mock_context)

            # Verify message was saved
            mock_messages_new_or_update.assert_called_once_with(
                mock_async_database_session,
                user_id=mock_update_message_reaction.effective_user.id,
                chat_id=mock_update_message_reaction.effective_chat.id,
                message=mock_update_message_reaction.message_reaction,
            )

            # Verify no session was created for reactions
            mock_get_active.assert_called_once_with(
                mock_async_database_session, str(mock_update_message_reaction.effective_chat.id)
            )
            mock_create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_message_reaction_received(self, mock_async_database_session, mock_update_empty):
        """Test on_message_react raises NoMessageReactionError when no message reaction is received."""
        mock_context = AsyncMock()

        with pytest.raises(NoMessageReactionError) as exc_info:
            await on_message_react(mock_update_empty, mock_context)

        assert str(exc_info.value) == f"Expected to receive a message reaction in update: {mock_update_empty.update_id}"

        # Ensure no database operations were attempted
        mock_async_database_session.assert_not_called()
