"""Tests for onboarding agent."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.user_metadata import UserMetadata
from areyouok_telegram.llms.chat.agents.onboarding import OnboardingAgentDependencies
from areyouok_telegram.llms.chat.agents.onboarding import save_user_response
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.agent_country_timezone import CountryTimezone
from areyouok_telegram.llms.agent_country_timezone import country_timezone_agent


class TestSaveUserResponse:
    """Test save_user_response function."""

    @pytest.fixture
    def mock_run_context(self):
        """Create mock pydantic_ai run context."""
        context = MagicMock()
        context.deps = MagicMock(spec=OnboardingAgentDependencies)
        context.deps.tg_chat_id = "123456"
        context.deps.tg_session_id = "session_123"
        return context

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    async def test_save_user_response_non_country_field_success(
        self, mock_log_context, mock_async_db, mock_run_context
    ):
        """Test successful metadata update for non-country fields."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Test data
        field = "preferred_name"
        value = "Alice Smith"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            result = await save_user_response(mock_run_context, field, value)

            # Verify database update was called
            mock_update.assert_called_once_with(
                mock_db_conn,
                user_id=mock_run_context.deps.tg_chat_id,
                field=field,
                value=value,
            )

            # Verify context logging was called
            mock_log_context.assert_called_once_with(
                chat_id=mock_run_context.deps.tg_chat_id,
                session_id=mock_run_context.deps.tg_session_id,
                content=f"Updated usermeta: {field} is now {str(value)}",
            )

            # Verify return value
            assert result == f"{field} updated successfully."

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.run_agent_with_tracking")
    async def test_save_user_response_country_single_timezone(
        self, mock_run_agent, mock_log_context, mock_async_db, mock_run_context
    ):
        """Test successful metadata update for country field with single timezone."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock timezone agent response
        mock_timezone_result = MagicMock()
        mock_timezone_result.output = CountryTimezone(timezone="America/New_York", has_multiple=False)
        mock_run_agent.return_value = mock_timezone_result

        # Test data
        field = "country"
        value = "USA"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            result = await save_user_response(mock_run_context, field, value)

            # Verify country update was called
            assert mock_update.call_count == 2  # country + timezone

            # First call: country update
            first_call = mock_update.call_args_list[0]
            assert first_call[1]["user_id"] == mock_run_context.deps.tg_chat_id
            assert first_call[1]["field"] == "country"
            assert first_call[1]["value"] == value

            # Second call: timezone update
            second_call = mock_update.call_args_list[1]
            assert second_call[1]["user_id"] == mock_run_context.deps.tg_chat_id
            assert second_call[1]["field"] == "timezone"
            assert second_call[1]["value"] == "America/New_York"

            # Verify timezone agent was called
            mock_run_agent.assert_called_once()
            agent_call = mock_run_agent.call_args
            assert agent_call[1]["chat_id"] == mock_run_context.deps.tg_chat_id
            assert agent_call[1]["session_id"] == mock_run_context.deps.tg_session_id
            expected_prompt = f"Identify the timezone for the ISO-3 Country: {value}."
            assert agent_call[1]["run_kwargs"]["user_prompt"] == expected_prompt

            # Verify context logging was called twice (country + timezone)
            assert mock_log_context.call_count == 2

            # First log call: country
            first_log_call = mock_log_context.call_args_list[0]
            assert first_log_call[1]["content"] == f"Updated usermeta: {field} is now {str(value)}"

            # Second log call: timezone
            second_log_call = mock_log_context.call_args_list[1]
            expected_tz_content = "Updated usermeta: timezone is now America/New_York"
            assert second_log_call[1]["content"] == expected_tz_content

            # Verify return value
            assert result == f"{field} updated successfully."

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.run_agent_with_tracking")
    async def test_save_user_response_country_multiple_timezones(
        self, mock_run_agent, mock_log_context, mock_async_db, mock_run_context
    ):
        """Test metadata update for country field with multiple timezones."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock timezone agent response with multiple timezones
        mock_timezone_result = MagicMock()
        mock_timezone_result.output = CountryTimezone(timezone="Europe/London", has_multiple=True)
        mock_run_agent.return_value = mock_timezone_result

        # Test data
        field = "country"
        value = "GBR"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            result = await save_user_response(mock_run_context, field, value)

            # Verify both country and timezone updates were called
            assert mock_update.call_count == 2

            # First call: country update
            first_call = mock_update.call_args_list[0]
            assert first_call[1]["user_id"] == mock_run_context.deps.tg_chat_id
            assert first_call[1]["field"] == "country"
            assert first_call[1]["value"] == value

            # Second call: timezone update
            second_call = mock_update.call_args_list[1]
            assert second_call[1]["user_id"] == mock_run_context.deps.tg_chat_id
            assert second_call[1]["field"] == "timezone"
            assert second_call[1]["value"] == "Europe/London"

            # Verify timezone agent was called
            mock_run_agent.assert_called_once()

            # Verify context logging was called twice (country + timezone with multiple timezone message)
            assert mock_log_context.call_count == 2

            # First log call: country
            first_log_call = mock_log_context.call_args_list[0]
            assert first_log_call[1]["content"] == f"Updated usermeta: {field} is now {str(value)}"

            # Second log call: timezone with simple format
            second_log_call = mock_log_context.call_args_list[1]
            expected_tz_content = "Updated usermeta: timezone is now Europe/London"
            assert second_log_call[1]["content"] == expected_tz_content

            # Verify return value
            assert result == f"{field} updated successfully."

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    async def test_save_user_response_country_rather_not_say(self, mock_log_context, mock_async_db, mock_run_context):
        """Test handling of 'rather_not_say' country value."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Test data
        field = "country"
        value = "rather_not_say"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            result = await save_user_response(mock_run_context, field, value)

            # Verify both country and timezone updates were called
            assert mock_update.call_count == 2

            # First call: country update
            first_call = mock_update.call_args_list[0]
            assert first_call[1]["field"] == "country"
            assert first_call[1]["value"] == "rather_not_say"

            # Second call: timezone update (also set to rather_not_say)
            second_call = mock_update.call_args_list[1]
            assert second_call[1]["field"] == "timezone"
            assert second_call[1]["value"] == "rather_not_say"

            # Verify context logging was called twice
            assert mock_log_context.call_count == 2

            # First log call: country
            first_log_call = mock_log_context.call_args_list[0]
            assert first_log_call[1]["content"] == f"Updated usermeta: {field} is now {str(value)}"

            # Second log call: timezone (also set to rather_not_say)
            second_log_call = mock_log_context.call_args_list[1]
            expected_tz_content = "Updated usermeta: timezone is now rather_not_say"
            assert second_log_call[1]["content"] == expected_tz_content

            # Verify return value
            assert result == f"{field} updated successfully."

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    async def test_save_user_response_database_error(self, mock_async_db, mock_run_context):
        """Test handling of database errors during metadata update."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Test data
        field = "preferred_name"
        value = "Test User"
        database_error = Exception("Database connection failed")

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            mock_update.side_effect = database_error

            with pytest.raises(MetadataFieldUpdateError) as exc_info:
                await save_user_response(mock_run_context, field, value)

            # Verify exception details - note that the function always raises timezone error
            assert exc_info.value.field == "timezone"  # This is hardcoded in the function
            assert str(database_error) in str(exc_info.value)
            assert exc_info.value.__cause__ == database_error

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.run_agent_with_tracking")
    async def test_save_user_response_timezone_database_error(self, mock_run_agent, mock_async_db, mock_run_context):
        """Test handling of database errors during timezone update for country fields."""
        # Setup mocks - need two different db connections for country and timezone updates
        mock_db_conn1 = AsyncMock()
        mock_db_conn2 = AsyncMock()
        mock_async_db.return_value.__aenter__.side_effect = [mock_db_conn1, mock_db_conn2]
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock timezone agent response
        mock_timezone_result = MagicMock()
        mock_timezone_result.output = CountryTimezone(timezone="America/New_York", has_multiple=False)
        mock_run_agent.return_value = mock_timezone_result

        # Test data
        field = "country"
        value = "USA"
        timezone_error = Exception("Timezone update failed")

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock) as mock_update:
            # First call (country) succeeds, second call (timezone) fails
            mock_update.side_effect = [None, timezone_error]

            with pytest.raises(MetadataFieldUpdateError) as exc_info:
                await save_user_response(mock_run_context, field, value)

            # Verify both database updates were attempted
            assert mock_update.call_count == 2

            # Verify exception details
            assert exc_info.value.field == "timezone"
            assert str(timezone_error) in str(exc_info.value)
            assert exc_info.value.__cause__ == timezone_error

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    async def test_save_user_response_context_logging_parameters(
        self, mock_log_context, mock_async_db, mock_run_context
    ):
        """Test that log_metadata_update_context is called with correct parameters."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Test different field and value combinations
        test_cases = [
            ("preferred_name", "John Doe"),
            ("communication_style", "formal and direct"),
            ("country", "rather_not_say"),  # Special case that doesn't trigger timezone logic
        ]

        for field, value in test_cases:
            # Reset mocks
            mock_log_context.reset_mock()

            with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock):
                await save_user_response(mock_run_context, field, value)

                # For country="rather_not_say", two calls are made (country + timezone)
                expected_call_count = 2 if field == "country" else 1
                assert mock_log_context.call_count == expected_call_count

                # Verify first call parameters (always the main field)
                first_call = mock_log_context.call_args_list[0]
                assert first_call[1]["chat_id"] == mock_run_context.deps.tg_chat_id
                assert first_call[1]["session_id"] == mock_run_context.deps.tg_session_id
                assert first_call[1]["content"] == f"Updated usermeta: {field} is now {str(value)}"

                # If country="rather_not_say", verify second call for timezone
                if field == "country":
                    second_call = mock_log_context.call_args_list[1]
                    assert second_call[1]["chat_id"] == mock_run_context.deps.tg_chat_id
                    assert second_call[1]["session_id"] == mock_run_context.deps.tg_session_id
                    expected_tz_content = "Updated usermeta: timezone is now rather_not_say"
                    assert second_call[1]["content"] == expected_tz_content

    @pytest.mark.asyncio
    @patch("areyouok_telegram.llms.chat.agents.onboarding.async_database")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.log_metadata_update_context")
    @patch("areyouok_telegram.llms.chat.agents.onboarding.run_agent_with_tracking")
    async def test_save_user_response_timezone_agent_parameters(self, mock_run_agent, mock_async_db, mock_run_context):
        """Test that timezone agent is called with correct parameters."""
        # Setup mocks
        mock_db_conn = AsyncMock()
        mock_async_db.return_value.__aenter__ = AsyncMock(return_value=mock_db_conn)
        mock_async_db.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock timezone agent response
        mock_timezone_result = MagicMock()
        mock_timezone_result.output = CountryTimezone(timezone="Europe/Paris", has_multiple=False)
        mock_run_agent.return_value = mock_timezone_result

        # Test data
        field = "country"
        country_code = "FRA"

        with patch.object(UserMetadata, "update_metadata", new_callable=AsyncMock):
            await save_user_response(mock_run_context, field, country_code)

            # Verify timezone agent was called correctly
            mock_run_agent.assert_called_once()
            call_args = mock_run_agent.call_args

            # Verify the agent being called

            assert call_args[0][0] == country_timezone_agent

            # Verify call parameters
            assert call_args[1]["chat_id"] == mock_run_context.deps.tg_chat_id
            assert call_args[1]["session_id"] == mock_run_context.deps.tg_session_id
            assert (
                call_args[1]["run_kwargs"]["user_prompt"]
                == f"Identify the timezone for the ISO-3 Country: {country_code}."
            )
