"""Tests for LLMGenerations model."""

import json
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from areyouok_telegram.data.models.llm_generations import LLMGenerations


class MockResponse:
    """Mock response object with model_dump and response_type."""

    def __init__(self, response_type: str, data: dict):
        self.response_type = response_type
        self._data = data

    def model_dump(self) -> dict:
        return self._data


class TestLLMGenerations:
    """Test LLMGenerations model."""

    def test_generate_generation_id(self):
        """Test generation ID creation."""
        chat_id = "chat123"
        session_id = "session456"
        agent = "test-agent"
        timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

        generation_id = LLMGenerations.generate_generation_id(chat_id, session_id, timestamp, agent)

        assert isinstance(generation_id, str)
        assert len(generation_id) == 64  # SHA256 hex digest length

    def test_generate_generation_id_consistency(self):
        """Test that same inputs generate same ID."""
        chat_id = "chat123"
        session_id = "session456"
        agent = "test-agent"
        timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

        id1 = LLMGenerations.generate_generation_id(chat_id, session_id, timestamp, agent)
        id2 = LLMGenerations.generate_generation_id(chat_id, session_id, timestamp, agent)

        assert id1 == id2

    def test_generate_generation_id_uniqueness(self):
        """Test that different inputs generate different IDs."""
        timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

        id1 = LLMGenerations.generate_generation_id("chat1", "session1", timestamp, "agent1")
        id2 = LLMGenerations.generate_generation_id("chat2", "session1", timestamp, "agent1")
        id3 = LLMGenerations.generate_generation_id("chat1", "session2", timestamp, "agent1")
        id4 = LLMGenerations.generate_generation_id("chat1", "session1", timestamp, "agent2")

        assert len({id1, id2, id3, id4}) == 4  # All should be unique

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_structured_response(self, mock_encrypt):
        """Test creating generation with structured response object."""
        mock_encrypt.return_value = "encrypted_payload"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        response = MockResponse("TextResponse", {"message_text": "Hello", "reasoning": "Test reasoning"})

        result = await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent="test-agent",
            response=response,
        )

        # Verify encrypt_content was called with the right payload
        mock_encrypt.assert_called_once()
        call_args = mock_encrypt.call_args[0][0]
        payload_dict = json.loads(call_args)
        assert payload_dict == {"message_text": "Hello", "reasoning": "Test reasoning"}

        # Verify the database insert was called
        mock_db_conn.execute.assert_called_once()

        # Verify the returned object
        assert result.chat_id == "chat123"
        assert result.session_id == "session456"
        assert result.agent == "test-agent"
        assert result.response_type == "TextResponse"
        assert result.encrypted_payload == "encrypted_payload"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_string_response(self, mock_encrypt):
        """Test creating generation with string response."""
        mock_encrypt.return_value = "encrypted_payload"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        response = "This is a string response"

        result = await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent="test-agent",
            response=response,
        )

        # Verify encrypt_content was called with the JSON-encoded string
        mock_encrypt.assert_called_once()
        call_args = mock_encrypt.call_args[0][0]
        assert call_args == '"This is a string response"'  # JSON-encoded string

        # Verify the response type
        assert result.response_type == "strResponse"

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_other_type_response(self, mock_encrypt):
        """Test creating generation with non-string, non-model response."""
        mock_encrypt.return_value = "encrypted_payload"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        response = 42  # Integer response

        result = await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent="test-agent",
            response=response,
        )

        # Verify encrypt_content was called with the serialized value directly
        mock_encrypt.assert_called_once()
        call_args = mock_encrypt.call_args[0][0]
        assert call_args == "42"  # JSON serialized integer

        # Verify the response type
        assert result.response_type == "intResponse"

    @pytest.mark.asyncio
    async def test_get_by_session(self):
        """Test retrieving generations by session."""

        mock_db_conn = AsyncMock()
        mock_result = Mock()
        mock_scalars = Mock()
        mock_generations = [
            LLMGenerations(generation_id="gen1", chat_id="chat1", session_id="session1", agent="agent1"),
            LLMGenerations(generation_id="gen2", chat_id="chat1", session_id="session1", agent="agent2"),
        ]
        mock_scalars.all.return_value = mock_generations
        mock_result.scalars.return_value = mock_scalars
        mock_db_conn.execute.return_value = mock_result

        result = await LLMGenerations.get_by_session(
            db_conn=mock_db_conn,
            chat_id="chat1",
            session_id="session1",
        )

        assert len(result) == 2
        assert all(isinstance(gen, LLMGenerations) for gen in result)
        mock_db_conn.execute.assert_called_once()

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_payload_property_with_json(self, mock_decrypt):
        """Test payload property with JSON content."""
        mock_decrypt.return_value = '{"key": "value"}'

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_payload="encrypted_data",
            response_type="TestResponse"
        )

        payload = generation.payload
        assert payload == {"key": "value"}
        mock_decrypt.assert_called_once_with("encrypted_data")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_payload_property_with_string(self, mock_decrypt):
        """Test payload property with string content."""
        mock_decrypt.return_value = '"test string"'

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_payload="encrypted_data",
            response_type="strResponse"
        )

        payload = generation.payload
        assert payload == "test string"
        mock_decrypt.assert_called_once_with("encrypted_data")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_payload_property_fallback(self, mock_decrypt):
        """Test payload property fallback for non-JSON content."""
        mock_decrypt.return_value = "raw content"

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_payload="encrypted_data",
            response_type="TestResponse"
        )

        payload = generation.payload
        assert payload == "raw content"
        mock_decrypt.assert_called_once_with("encrypted_data")
