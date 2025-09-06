"""Tests for handlers/settings_utils.py."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.handlers.settings_utils import construct_user_settings_response
from areyouok_telegram.handlers.settings_utils import update_user_metadata_field


class TestUpdateUserMetadataField:
    """Test update_user_metadata_field function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.run_agent_with_tracking")
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
        result = await update_user_metadata_field(
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
    @patch("areyouok_telegram.handlers.settings_utils.run_agent_with_tracking")
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
            ("communication_style", "casual"),
        ]
        
        chat_id = "123456789"
        session_id = "session_456"
        
        for field_name, new_value in test_cases:
            mock_run_agent.reset_mock()
            
            # Call function
            await update_user_metadata_field(
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

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.run_agent_with_tracking")
    async def test_update_user_metadata_field_agent_error(self, mock_run_agent):
        """Test handling of agent errors during update."""
        # Setup mock to raise an exception
        agent_error = Exception("Agent processing failed")
        mock_run_agent.side_effect = agent_error
        
        # Should propagate the agent error
        with pytest.raises(Exception) as exc_info:
            await update_user_metadata_field(
                chat_id="123456789",
                session_id="session_456",
                field_name="preferred_name",
                new_value="Alice",
            )
        
        assert exc_info.value == agent_error


class TestConstructUserSettingsResponse:
    """Test construct_user_settings_response function."""

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.async_database")
    @patch("areyouok_telegram.handlers.settings_utils.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_with_metadata(
        self, mock_get_by_user_id, mock_async_database
    ):
        """Test constructing response when user has metadata."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Setup user metadata mock
        mock_user_metadata = MagicMock()
        mock_user_metadata.preferred_name = "Alice Smith"
        mock_user_metadata.country = "USA"
        mock_user_metadata.timezone = "America/New_York"
        mock_get_by_user_id.return_value = mock_user_metadata
        
        user_id = "123456789"
        
        with patch("areyouok_telegram.handlers.settings_utils.SETTINGS_DISPLAY_TEMPLATE") as mock_template, \
             patch("areyouok_telegram.handlers.settings_utils.escape_markdown_v2") as mock_escape:
            
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• Name: Alice Smith"
            
            # Mock markdown escaping
            mock_escape.side_effect = lambda x: f"escaped_{x}"
            
            # Call function
            result = await construct_user_settings_response(user_id)
            
            # Verify database operations
            mock_get_by_user_id.assert_called_once_with(mock_db_conn, user_id=user_id)
            
            # Verify markdown escaping was called for each field
            expected_escape_calls = [
                ((mock_user_metadata.preferred_name,),),
                ((mock_user_metadata.country,),),
                ((mock_user_metadata.timezone,),),
            ]
            assert mock_escape.call_args_list == expected_escape_calls
            
            # Verify template formatting
            mock_template.format.assert_called_once_with(
                name="escaped_Alice Smith",
                country="escaped_USA",
                timezone="escaped_America/New_York",
            )
            
            assert result == "**Your Settings:**\n• Name: Alice Smith"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.async_database")
    @patch("areyouok_telegram.handlers.settings_utils.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_no_metadata(
        self, mock_get_by_user_id, mock_async_database
    ):
        """Test constructing response when user has no metadata."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Mock no user metadata found
        mock_get_by_user_id.return_value = None
        
        user_id = "123456789"
        
        with patch("areyouok_telegram.handlers.settings_utils.SETTINGS_DISPLAY_TEMPLATE") as mock_template, \
             patch("areyouok_telegram.handlers.settings_utils.escape_markdown_v2") as mock_escape:
            
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• All fields: Not set"
            
            # Mock markdown escaping
            mock_escape.return_value = "escaped_Not set"
            
            # Call function
            result = await construct_user_settings_response(user_id)
            
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
    @patch("areyouok_telegram.handlers.settings_utils.async_database")
    @patch("areyouok_telegram.handlers.settings_utils.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_rather_not_say(
        self, mock_get_by_user_id, mock_async_database
    ):
        """Test constructing response with 'rather_not_say' values."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Setup user metadata with "rather_not_say" values
        mock_user_metadata = MagicMock()
        mock_user_metadata.preferred_name = "Alice"
        mock_user_metadata.country = "rather_not_say"
        mock_user_metadata.timezone = "rather_not_say"
        mock_get_by_user_id.return_value = mock_user_metadata
        
        user_id = "123456789"
        
        with patch("areyouok_telegram.handlers.settings_utils.SETTINGS_DISPLAY_TEMPLATE") as mock_template, \
             patch("areyouok_telegram.handlers.settings_utils.escape_markdown_v2") as mock_escape:
            
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• Mixed values"
            
            # Mock markdown escaping
            mock_escape.side_effect = lambda x: f"escaped_{x}"
            
            # Call function
            result = await construct_user_settings_response(user_id)
            
            # Verify special handling of "rather_not_say" values
            mock_template.format.assert_called_once_with(
                name="escaped_Alice",
                country="escaped_Prefer not to say",
                timezone="escaped_Prefer not to say",
            )
            
            assert result == "**Your Settings:**\n• Mixed values"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.async_database")
    @patch("areyouok_telegram.handlers.settings_utils.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_partial_metadata(
        self, mock_get_by_user_id, mock_async_database
    ):
        """Test constructing response when user has partial metadata."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Setup user metadata with some fields None
        mock_user_metadata = MagicMock()
        mock_user_metadata.preferred_name = "Bob"
        mock_user_metadata.country = None  # Not set
        mock_user_metadata.timezone = "UTC"
        mock_get_by_user_id.return_value = mock_user_metadata
        
        user_id = "123456789"
        
        with patch("areyouok_telegram.handlers.settings_utils.SETTINGS_DISPLAY_TEMPLATE") as mock_template, \
             patch("areyouok_telegram.handlers.settings_utils.escape_markdown_v2") as mock_escape:
            
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• Partial metadata"
            
            # Mock markdown escaping
            mock_escape.side_effect = lambda x: f"escaped_{x}"
            
            # Call function
            result = await construct_user_settings_response(user_id)
            
            # Verify mix of real values and "Not set"
            mock_template.format.assert_called_once_with(
                name="escaped_Bob",
                country="escaped_Not set",  # None becomes "Not set"
                timezone="escaped_UTC",
            )
            
            assert result == "**Your Settings:**\n• Partial metadata"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.async_database")
    @patch("areyouok_telegram.handlers.settings_utils.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_database_error(
        self, mock_get_by_user_id, mock_async_database
    ):
        """Test handling of database errors during response construction."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Mock database error
        database_error = Exception("Database connection failed")
        mock_get_by_user_id.side_effect = database_error
        
        user_id = "123456789"
        
        # Should propagate the database error
        with pytest.raises(Exception) as exc_info:
            await construct_user_settings_response(user_id)
        
        assert exc_info.value == database_error
        mock_get_by_user_id.assert_called_once_with(mock_db_conn, user_id=user_id)

    @pytest.mark.asyncio
    @patch("areyouok_telegram.handlers.settings_utils.async_database")
    @patch("areyouok_telegram.handlers.settings_utils.UserMetadata.get_by_user_id")
    async def test_construct_user_settings_response_empty_string_values(
        self, mock_get_by_user_id, mock_async_database
    ):
        """Test constructing response with empty string metadata values."""
        # Setup database mock
        mock_db_conn = AsyncMock()
        mock_async_database.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_database.return_value.__aexit__ = AsyncMock(return_value=None)
        
        # Setup user metadata with empty strings
        mock_user_metadata = MagicMock()
        mock_user_metadata.preferred_name = ""
        mock_user_metadata.country = ""
        mock_user_metadata.timezone = ""
        mock_get_by_user_id.return_value = mock_user_metadata
        
        user_id = "123456789"
        
        with patch("areyouok_telegram.handlers.settings_utils.SETTINGS_DISPLAY_TEMPLATE") as mock_template, \
             patch("areyouok_telegram.handlers.settings_utils.escape_markdown_v2") as mock_escape:
            
            # Mock template formatting
            mock_template.format.return_value = "**Your Settings:**\n• Empty values"
            
            # Mock markdown escaping
            mock_escape.side_effect = lambda x: f"escaped_{x}"
            
            # Call function
            result = await construct_user_settings_response(user_id)
            
            # Verify empty strings are treated as "Not set" (falsy values)
            mock_template.format.assert_called_once_with(
                name="escaped_Not set",
                country="escaped_Not set",
                timezone="escaped_Not set",
            )
            
            assert result == "**Your Settings:**\n• Empty values"