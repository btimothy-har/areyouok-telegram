"""Tests for handlers/settings.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import telegram
from telegram.ext import ContextTypes

from areyouok_telegram.handlers.settings import _construct_user_settings_response
from areyouok_telegram.handlers.settings import _update_user_metadata_field
from areyouok_telegram.handlers.settings import on_settings_command


class TestOnSettingsCommand:
    """Test the on_settings_command handler."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings._construct_user_settings_response")
    async def test_on_settings_command_display_settings(
        self, mock_construct_response, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test settings command displays current settings when no arguments provided."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        mock_construct_response.return_value = "**Your Current Settings:**\n• Name: John Doe"

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify settings response was constructed
        mock_construct_response.assert_called_once_with(user_id=str(mock_telegram_user.id))

        # Verify message was sent
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="**Your Current Settings:**\n• Name: John Doe",
            parse_mode="MarkdownV2",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings._update_user_metadata_field")
    @patch("areyouok_telegram.handlers.settings.data_operations.get_or_create_active_session")
    async def test_on_settings_command_update_preferred_name(
        self,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command updates preferred name field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings name Alice Smith"
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your preferred name to Alice Smith."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify reaction was set
        mock_context.bot.set_message_reaction.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            message_id=12345,
            reaction="👌",
        )

        # Verify typing indicator
        mock_context.bot.send_chat_action.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            action=telegram.constants.ChatAction.TYPING,
        )

        # Verify session was created/retrieved
        mock_get_active_session.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            timestamp=mock_telegram_message.date,
        )

        # Verify field update was called
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="preferred_name",
            new_value="Alice Smith",
        )

        # Verify response message
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="Successfully updated your preferred name to Alice Smith.",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings._update_user_metadata_field")
    @patch("areyouok_telegram.handlers.settings.data_operations.get_or_create_active_session")
    async def test_on_settings_command_update_country(
        self,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command updates country field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings country USA"
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your country to USA."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify field update was called with correct parameters
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="country",
            new_value="USA",
        )

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings._update_user_metadata_field")
    @patch("areyouok_telegram.handlers.settings.data_operations.get_or_create_active_session")
    async def test_on_settings_command_update_timezone(
        self,
        mock_get_active_session,
        mock_update_field,
        mock_telegram_user,
        mock_telegram_chat,
        mock_telegram_message,
    ):
        """Test settings command updates timezone field."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings timezone America/New_York"
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Mock session
        mock_session = MagicMock()
        mock_session.session_id = 123
        mock_get_active_session.return_value = mock_session

        # Mock update response
        mock_response = MagicMock()
        mock_response.feedback = "Successfully updated your timezone to America/New_York."
        mock_update_field.return_value = mock_response

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify field update was called with correct parameters
        mock_update_field.assert_called_once_with(
            chat_id=str(mock_telegram_chat.id),
            session_id=str(mock_session.session_id),
            field_name="timezone",
            new_value="America/New_York",
        )

    @pytest.mark.asyncio
    async def test_on_settings_command_invalid_field(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test settings command with invalid field name."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings invalid_field some_value"

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        # Call handler
        await on_settings_command(mock_update, mock_context)

        # Verify error message was sent
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_telegram_chat.id,
            text="Invalid field. Please specify one of: name, country, timezone.",
        )

    @pytest.mark.asyncio
    async def test_on_settings_command_field_normalization(
        self, mock_telegram_user, mock_telegram_chat, mock_telegram_message
    ):
        """Test that 'name' field is normalized to 'preferred_name'."""
        # Setup mocks
        mock_update = MagicMock(spec=telegram.Update)
        mock_update.effective_user = mock_telegram_user
        mock_update.effective_chat = mock_telegram_chat
        mock_update.message = mock_telegram_message
        mock_update.message.text = "/settings name Alice"  # Use 'name' to test normalization
        mock_update.message.id = 12345

        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        mock_context.bot = AsyncMock()

        with (
            patch(
                "areyouok_telegram.handlers.settings.data_operations.get_or_create_active_session"
            ) as mock_get_active_session,
            patch("areyouok_telegram.handlers.settings._update_user_metadata_field") as mock_update_field,
        ):
            # Mock session
            mock_session = MagicMock()
            mock_session.session_id = 123
            mock_get_active_session.return_value = mock_session

            # Mock update response
            mock_response = MagicMock()
            mock_response.feedback = "Updated."
            mock_update_field.return_value = mock_response

            # Call handler
            await on_settings_command(mock_update, mock_context)

            # Verify the field name was normalized from 'name' to 'preferred_name'
            mock_update_field.assert_called_once_with(
                chat_id=str(mock_telegram_chat.id),
                session_id=str(mock_session.session_id),
                field_name="preferred_name",
                new_value="Alice",
            )


class TestUpdateUserMetadataField:
    """Test _update_user_metadata_field private function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings.run_agent_with_tracking")
    async def test_update_user_metadata_field_success(self, mock_run_agent):
        """Test successful metadata field update."""
        # Setup mock response
        mock_agent_response = MagicMock()
        mock_agent_response.output.feedback = "Successfully updated your preferred name to Alice."
        mock_run_agent.return_value = mock_agent_response

        # Test parameters
        chat_id = "123456789"
        session_id = "session_456"
        field_name = "preferred_name"
        new_value = "Alice"

        # Call function
        result = await _update_user_metadata_field(
            chat_id=chat_id,
            session_id=session_id,
            field_name=field_name,
            new_value=new_value,
        )

        # Verify agent was called with correct parameters
        mock_run_agent.assert_called_once()
        call_args = mock_run_agent.call_args

        # Check the agent used (first positional argument)
        agent_used = call_args[0][0]
        assert agent_used is not None

        # Check chat_id and session_id passed correctly
        assert call_args[1]["chat_id"] == chat_id
        assert call_args[1]["session_id"] == session_id

        # Check run_kwargs
        run_kwargs = call_args[1]["run_kwargs"]
        expected_instruction = f"Update {field_name} to {new_value}."
        assert run_kwargs["user_prompt"] == expected_instruction

        # Check dependencies
        deps = run_kwargs["deps"]
        assert deps.tg_chat_id == chat_id
        assert deps.tg_session_id == session_id

        # Verify return value
        assert result.feedback == "Successfully updated your preferred name to Alice."

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings.run_agent_with_tracking")
    async def test_update_user_metadata_field_different_fields(self, mock_run_agent):
        """Test updating different metadata fields."""
        # Setup mock response
        mock_agent_response = MagicMock()
        mock_agent_response.output.feedback = "Field updated successfully."
        mock_run_agent.return_value = mock_agent_response

        test_cases = [
            ("preferred_name", "John Doe"),
            ("country", "USA"),
            ("timezone", "America/New_York"),
        ]

        chat_id = "123456789"
        session_id = "session_456"

        for field_name, new_value in test_cases:
            mock_run_agent.reset_mock()

            # Call function
            await _update_user_metadata_field(
                chat_id=chat_id,
                session_id=session_id,
                field_name=field_name,
                new_value=new_value,
            )

            # Verify correct instruction was generated
            call_args = mock_run_agent.call_args
            run_kwargs = call_args[1]["run_kwargs"]
            expected_instruction = f"Update {field_name} to {new_value}."
            assert run_kwargs["user_prompt"] == expected_instruction


class TestConstructUserSettingsResponse:
    """Test _construct_user_settings_response private function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings.async_database")
    @patch("areyouok_telegram.handlers.settings.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_with_metadata(self, mock_get_by_user_id, mock_async_database):
        """Test constructing response when user has metadata."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Setup user metadata mock
        mock_user_metadata = MagicMock()
        mock_user_metadata.preferred_name = "Alice Smith"
        mock_user_metadata.country = "USA"
        mock_user_metadata.country_display_name = "United States"
        mock_user_metadata.timezone = "America/New_York"
        mock_get_by_user_id.return_value = mock_user_metadata

        user_id = "123456789"

        with (
            patch("areyouok_telegram.handlers.settings.MD2_SETTINGS_DISPLAY_TEMPLATE") as mock_template,
            patch("areyouok_telegram.handlers.settings.escape_markdown_v2") as mock_escape,
        ):
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• Name: Alice Smith"

            # Mock markdown escaping
            mock_escape.side_effect = lambda x: f"escaped_{x}"

            # Call function
            result = await _construct_user_settings_response(user_id)

            # Verify database operations
            mock_get_by_user_id.assert_called_once_with(mock_db_conn, user_id=user_id)

            # Verify markdown escaping was called for each field
            expected_escape_calls = [
                ((mock_user_metadata.preferred_name,),),
                ((mock_user_metadata.country_display_name,),),
                ((mock_user_metadata.timezone,),),
            ]
            assert mock_escape.call_args_list == expected_escape_calls

            # Verify template formatting
            mock_template.format.assert_called_once_with(
                name="escaped_Alice Smith",
                country="escaped_United States",
                timezone="escaped_America/New_York",
            )

            assert result == "**Your Settings:**\n• Name: Alice Smith"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings.async_database")
    @patch("areyouok_telegram.handlers.settings.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_no_metadata(self, mock_get_by_user_id, mock_async_database):
        """Test constructing response when user has no metadata."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock no user metadata found
        mock_get_by_user_id.return_value = None

        user_id = "123456789"

        with (
            patch("areyouok_telegram.handlers.settings.MD2_SETTINGS_DISPLAY_TEMPLATE") as mock_template,
            patch("areyouok_telegram.handlers.settings.escape_markdown_v2") as mock_escape,
        ):
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• All fields: Not set"

            # Mock markdown escaping
            mock_escape.return_value = "escaped_Not set"

            # Call function
            result = await _construct_user_settings_response(user_id)

            # Verify all fields default to "Not set"
            mock_template.format.assert_called_once_with(
                name="escaped_Not set",
                country="escaped_Not set",
                timezone="escaped_Not set",
            )

            # Verify escaping was called for each "Not set" value
            assert mock_escape.call_count == 3
            for call in mock_escape.call_args_list:
                assert call[0][0] == "Not set"

            assert result == "**Your Settings:**\n• All fields: Not set"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings.async_database")
    @patch("areyouok_telegram.handlers.settings.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_rather_not_say(self, mock_get_by_user_id, mock_async_database):
        """Test constructing response with 'rather_not_say' values."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)

        # Setup user metadata with "rather_not_say" values
        mock_user_metadata = MagicMock()
        mock_user_metadata.preferred_name = "Alice"
        mock_user_metadata.country = "rather_not_say"
        mock_user_metadata.country_display_name = "Prefer not to say"
        mock_user_metadata.timezone = "rather_not_say"
        mock_get_by_user_id.return_value = mock_user_metadata

        user_id = "123456789"

        with (
            patch("areyouok_telegram.handlers.settings.MD2_SETTINGS_DISPLAY_TEMPLATE") as mock_template,
            patch("areyouok_telegram.handlers.settings.escape_markdown_v2") as mock_escape,
        ):
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• Mixed values"

            # Mock markdown escaping
            mock_escape.side_effect = lambda x: f"escaped_{x}"

            # Call function
            result = await _construct_user_settings_response(user_id)

            # Verify special handling of "rather_not_say" values
            mock_template.format.assert_called_once_with(
                name="escaped_Alice",
                country="escaped_Prefer not to say",
                timezone="escaped_Prefer not to say",
            )

            assert result == "**Your Settings:**\n• Mixed values"
