"""Tests for jobs/profile_generation.py."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.context import ContextType
from areyouok_telegram.data.operations import InvalidChatError
from areyouok_telegram.jobs.profile_generation import ProfileGenerationJob
from areyouok_telegram.llms.profile_generation import ProfileTemplate


class TestProfileGenerationJob:
    """Test the ProfileGenerationJob class."""

    def test_init(self):
        """Test ProfileGenerationJob initialization."""
        job = ProfileGenerationJob()

        assert job._bot_id is None
        assert job._run_count == 0

    def test_name_property(self):
        """Test name property."""
        job = ProfileGenerationJob()
        assert job.name == "profile_generation"

    @pytest.mark.asyncio
    async def test_run_job_successful_batch_processing(self, frozen_time):
        """Test run_job successfully processes batch and persists state."""
        job = ProfileGenerationJob()
        job._run_timestamp = frozen_time

        mock_chat1 = MagicMock()
        mock_chat1.chat_id = "chat1"
        mock_chat2 = MagicMock()
        mock_chat2.chat_id = "chat2"

        with (
            patch.object(job, "load_state", new=AsyncMock(return_value={})),
            patch.object(job, "save_state", new=AsyncMock()) as mock_save,
            patch.object(job, "_fetch_all_chats", new=AsyncMock(return_value=[mock_chat1, mock_chat2])),
            patch.object(job, "_process_chat", new=AsyncMock(side_effect=[True, False])),
        ):
            await job.run_job()

        # Verify state was saved with correct data
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["last_run_time"] == frozen_time.isoformat()
        assert call_kwargs["profiles_generated"] == 1

    @pytest.mark.asyncio
    async def test_run_job_with_previous_state(self, frozen_time):
        """Test run_job uses previous state for cutoff time."""
        job = ProfileGenerationJob()
        job._run_timestamp = frozen_time

        previous_run = (frozen_time - timedelta(hours=1)).isoformat()

        with (
            patch.object(job, "load_state", new=AsyncMock(return_value={"last_run_time": previous_run})),
            patch.object(job, "save_state", new=AsyncMock()),
            patch.object(job, "_fetch_all_chats", new=AsyncMock(return_value=[])),
            patch.object(
                job, "_process_chat", new=AsyncMock()
            ) as mock_process,  # Should pass cutoff_time to _process_chat
        ):
            await job.run_job()

        # Verify _process_chat wasn't called since no chats
        mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_job_continues_on_chat_failure(self, frozen_time):
        """Test run_job continues processing other chats when one fails."""
        job = ProfileGenerationJob()
        job._run_timestamp = frozen_time

        mock_chat1 = MagicMock()
        mock_chat1.chat_id = "chat1"
        mock_chat2 = MagicMock()
        mock_chat2.chat_id = "chat2"

        with (
            patch.object(job, "load_state", new=AsyncMock(return_value={})),
            patch.object(job, "save_state", new=AsyncMock()) as mock_save,
            patch.object(job, "_fetch_all_chats", new=AsyncMock(return_value=[mock_chat1, mock_chat2])),
            patch.object(
                job, "_process_chat", new=AsyncMock(side_effect=[Exception("Failed chat1"), True])
            ) as mock_process,
            patch("areyouok_telegram.jobs.profile_generation.logfire.exception") as mock_log_exc,
        ):
            await job.run_job()

        # Verify both chats were attempted
        assert mock_process.call_count == 2

        # Verify exception was logged but job continued
        mock_log_exc.assert_called_once()

        # Verify state was saved with 1 successful profile
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["profiles_generated"] == 1

    @pytest.mark.asyncio
    async def test_process_chat_skips_active_session(self):
        """Test _process_chat skips when chat has active session."""
        job = ProfileGenerationJob()
        job._run_timestamp = datetime.now(UTC)
        cutoff_time = datetime.now(UTC) - timedelta(hours=1)

        with (
            patch.object(job, "_has_active_session", new=AsyncMock(return_value=True)),
            patch("areyouok_telegram.jobs.profile_generation.logfire.debug") as mock_log,
        ):
            result = await job._process_chat(chat_id="chat123", cutoff_time=cutoff_time)

        assert result is False
        mock_log.assert_called_once()
        assert "active session" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_process_chat_skips_no_new_contexts(self):
        """Test _process_chat skips when no new contexts since last run."""
        job = ProfileGenerationJob()
        job._run_timestamp = datetime.now(UTC)
        cutoff_time = datetime.now(UTC) - timedelta(hours=1)

        # Old context created before cutoff
        old_context = MagicMock()
        old_context.created_at = cutoff_time - timedelta(minutes=30)
        old_context.type = ContextType.MEMORY.value

        with (
            patch.object(job, "_has_active_session", new=AsyncMock(return_value=False)),
            patch.object(job, "_fetch_contexts", new=AsyncMock(return_value=[old_context])),
            patch("areyouok_telegram.jobs.profile_generation.logfire.debug") as mock_log,
        ):
            result = await job._process_chat(chat_id="chat123", cutoff_time=cutoff_time)

        assert result is False
        mock_log.assert_called_once()
        assert "no new contexts" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_process_chat_skips_profile_update_contexts(self):
        """Test _process_chat skips when only PROFILE_UPDATE contexts are new (no self-trigger)."""
        job = ProfileGenerationJob()
        job._run_timestamp = datetime.now(UTC)
        cutoff_time = datetime.now(UTC) - timedelta(hours=1)

        # New PROFILE_UPDATE context (created by previous job run)
        profile_update_context = MagicMock()
        profile_update_context.created_at = cutoff_time + timedelta(minutes=10)
        profile_update_context.type = ContextType.PROFILE_UPDATE.value

        with (
            patch.object(job, "_has_active_session", new=AsyncMock(return_value=False)),
            patch.object(job, "_fetch_contexts", new=AsyncMock(return_value=[profile_update_context])),
            patch("areyouok_telegram.jobs.profile_generation.logfire.debug") as mock_log,
        ):
            result = await job._process_chat(chat_id="chat123", cutoff_time=cutoff_time)

        assert result is False
        mock_log.assert_called_once()
        assert "no new contexts" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_process_chat_generates_profile_success(self, frozen_time):
        """Test _process_chat successfully generates profile when new contexts exist."""
        job = ProfileGenerationJob()
        job._run_timestamp = frozen_time
        cutoff_time = frozen_time - timedelta(hours=1)

        # New context after cutoff
        new_context = MagicMock()
        new_context.created_at = cutoff_time + timedelta(minutes=10)
        new_context.type = ContextType.MEMORY.value
        new_context.decrypt_content.return_value = "User shared they're feeling anxious about work"

        mock_profile = ProfileTemplate(
            identity_markers="Test identity",
            strengths_values="Test strengths",
            goals_outcomes="Test goals",
            emotional_patterns="Test patterns",
            safety_plan="Test safety",
            change_log="Initial profile",
        )
        mock_result = MagicMock()
        mock_result.output = mock_profile

        mock_db_conn = AsyncMock()

        with (
            patch.object(job, "_has_active_session", new=AsyncMock(return_value=False)),
            patch.object(job, "_fetch_contexts", new=AsyncMock(return_value=[new_context])),
            patch(
                "areyouok_telegram.jobs.profile_generation.data_operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_key"),
            ),
            patch("areyouok_telegram.jobs.profile_generation.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.profile_generation.Context.get_latest_profile",
                new=AsyncMock(return_value=None),
            ),
            patch("areyouok_telegram.jobs.profile_generation.Context.new", new=AsyncMock()) as mock_context_new,
            patch(
                "areyouok_telegram.jobs.profile_generation.run_agent_with_tracking",
                new=AsyncMock(return_value=mock_result),
            ),
        ):
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn
            result = await job._process_chat(chat_id="chat123", cutoff_time=cutoff_time)

        assert result is True

        # Verify both PROFILE and PROFILE_UPDATE contexts were saved
        assert mock_context_new.call_count == 2
        calls = mock_context_new.call_args_list

        # Check PROFILE context
        assert calls[0][1]["ctype"] == ContextType.PROFILE.value
        assert calls[0][1]["content"] == mock_profile.content

        # Check PROFILE_UPDATE context
        assert calls[1][1]["ctype"] == ContextType.PROFILE_UPDATE.value
        assert calls[1][1]["content"] == mock_profile.change_log

    @pytest.mark.asyncio
    async def test_process_chat_handles_invalid_chat_error(self):
        """Test _process_chat handles InvalidChatError gracefully."""
        job = ProfileGenerationJob()
        job._run_timestamp = datetime.now(UTC)
        cutoff_time = datetime.now(UTC) - timedelta(hours=1)

        new_context = MagicMock()
        new_context.created_at = cutoff_time + timedelta(minutes=10)
        new_context.type = ContextType.MEMORY.value

        with (
            patch.object(job, "_has_active_session", new=AsyncMock(return_value=False)),
            patch.object(job, "_fetch_contexts", new=AsyncMock(return_value=[new_context])),
            patch(
                "areyouok_telegram.jobs.profile_generation.data_operations.get_chat_encryption_key",
                new=AsyncMock(side_effect=InvalidChatError("chat123")),
            ),
        ):
            # Should be caught by the generic exception handler in _process_chat
            # which is called from run_job
            with pytest.raises(InvalidChatError):
                await job._process_chat(chat_id="chat123", cutoff_time=cutoff_time)

    @pytest.mark.asyncio
    async def test_process_chat_skips_failed_decryption(self):
        """Test _process_chat logs and skips contexts that fail to decrypt."""
        job = ProfileGenerationJob()
        job._run_timestamp = datetime.now(UTC)
        cutoff_time = datetime.now(UTC) - timedelta(hours=1)

        context1 = MagicMock()
        context1.created_at = cutoff_time + timedelta(minutes=10)
        context1.type = ContextType.MEMORY.value
        context1.id = "ctx1"
        context1.decrypt_content.side_effect = Exception("Decryption failed")

        context2 = MagicMock()
        context2.created_at = cutoff_time + timedelta(minutes=20)
        context2.type = ContextType.SESSION.value
        context2.id = "ctx2"
        context2.decrypt_content.return_value = "Valid content"

        with (
            patch.object(job, "_has_active_session", new=AsyncMock(return_value=False)),
            patch.object(job, "_fetch_contexts", new=AsyncMock(return_value=[context1, context2])),
            patch(
                "areyouok_telegram.jobs.profile_generation.data_operations.get_chat_encryption_key",
                new=AsyncMock(return_value="test_key"),
            ),
            patch("areyouok_telegram.jobs.profile_generation.logfire.exception") as mock_log_exc,
        ):
            # Should skip chat entirely since all contexts failed decryption leads to no contents
            # Actually context2 should work, so let me continue the mock chain
            with (
                patch("areyouok_telegram.jobs.profile_generation.async_database") as mock_async_db,
                patch(
                    "areyouok_telegram.jobs.profile_generation.Context.get_latest_profile",
                    new=AsyncMock(return_value=None),
                ),
                patch("areyouok_telegram.jobs.profile_generation.Context.new", new=AsyncMock()),
                patch(
                    "areyouok_telegram.jobs.profile_generation.run_agent_with_tracking",
                    new=AsyncMock(
                        return_value=MagicMock(
                            output=ProfileTemplate(
                                identity_markers="Test",
                                strengths_values="Test",
                                goals_outcomes="Test",
                                emotional_patterns="Test",
                                safety_plan="Test",
                                change_log="Test",
                            )
                        )
                    ),
                ),
            ):
                mock_async_db.return_value.__aenter__.return_value = AsyncMock()
                result = await job._process_chat(chat_id="chat123", cutoff_time=cutoff_time)

        # Should have logged exception for failed decryption
        mock_log_exc.assert_called_once()
        assert "ctx1" in str(mock_log_exc.call_args)

        # But should still succeed with the one valid context
        assert result is True

    @pytest.mark.asyncio
    async def test_fetch_all_chats(self):
        """Test _fetch_all_chats returns all chats."""
        job = ProfileGenerationJob()

        mock_chat1 = MagicMock()
        mock_chat2 = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_chat1, mock_chat2]

        with patch("areyouok_telegram.jobs.profile_generation.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_db_conn.execute.return_value = mock_result
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._fetch_all_chats()

        assert result == [mock_chat1, mock_chat2]

    @pytest.mark.asyncio
    async def test_has_active_session_true(self):
        """Test _has_active_session returns True when active session exists."""
        job = ProfileGenerationJob()

        mock_session = MagicMock()

        with (
            patch("areyouok_telegram.jobs.profile_generation.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.profile_generation.Sessions.get_active_session",
                new=AsyncMock(return_value=mock_session),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._has_active_session(chat_id="chat123")

        assert result is True

    @pytest.mark.asyncio
    async def test_has_active_session_false(self):
        """Test _has_active_session returns False when no active session."""
        job = ProfileGenerationJob()

        with (
            patch("areyouok_telegram.jobs.profile_generation.async_database") as mock_async_db,
            patch(
                "areyouok_telegram.jobs.profile_generation.Sessions.get_active_session",
                new=AsyncMock(return_value=None),
            ),
        ):
            mock_db_conn = AsyncMock()
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._has_active_session(chat_id="chat123")

        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_contexts(self, frozen_time):
        """Test _fetch_contexts returns filtered contexts."""
        job = ProfileGenerationJob()

        mock_ctx1 = MagicMock()
        mock_ctx2 = MagicMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_ctx1, mock_ctx2]

        since = frozen_time - timedelta(days=30)

        with patch("areyouok_telegram.jobs.profile_generation.async_database") as mock_async_db:
            mock_db_conn = AsyncMock()
            mock_db_conn.execute.return_value = mock_result
            mock_async_db.return_value.__aenter__.return_value = mock_db_conn

            result = await job._fetch_contexts(chat_id="chat123", since=since)

        assert result == [mock_ctx1, mock_ctx2]
