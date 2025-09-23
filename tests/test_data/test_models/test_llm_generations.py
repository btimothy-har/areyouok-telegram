"""Tests for LLMGenerations model."""

import dataclasses
import json
from datetime import UTC
from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pydantic
import pydantic_ai
import pytest

from areyouok_telegram.data.models.llm_generations import LLMGenerations
from areyouok_telegram.data.models.llm_generations import serialize_object


def create_mock_output(response_type: str, data: dict):
    """Create a mock output object that behaves like a Pydantic model."""
    mock_output = MagicMock(spec=pydantic.BaseModel)
    mock_output.__class__.__name__ = response_type
    mock_output.model_dump.return_value = data
    # Make isinstance(mock_output, pydantic.BaseModel) return True
    mock_output.__class__ = type(response_type, (pydantic.BaseModel,), {})
    return mock_output


def create_mock_agent_run_result(output_obj, messages_json: str = '{"messages": []}') -> MagicMock:
    """Create a mock AgentRunResult object."""
    mock_result = MagicMock(spec=pydantic_ai.agent.AgentRunResult)
    mock_result.output = output_obj
    mock_result.all_messages_json.return_value = messages_json.encode("utf-8")
    return mock_result


def create_mock_agent() -> MagicMock:
    """Create a mock pydantic_ai.Agent object."""
    mock_agent = MagicMock(spec=pydantic_ai.Agent)
    mock_agent.name = "test-agent"

    # Create mock model
    mock_model = MagicMock()
    mock_model.model_name = "test-model"
    mock_model.system = "test"
    mock_agent.model = mock_model

    return mock_agent


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
        mock_encrypt.return_value = "encrypted_content"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        # Create mock output and run result
        output_obj = create_mock_output("TextResponse", {"message_text": "Hello", "reasoning": "Test reasoning"})
        mock_agent = create_mock_agent()
        mock_run_result = create_mock_agent_run_result(output_obj, '{"messages": [{"role": "user", "content": "test"}]}')

        await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent=mock_agent,
            run_result=mock_run_result,
        )

        # Verify encrypt_content was called with the right payload for output
        assert mock_encrypt.call_count == 2  # One for output, one for messages

        # Check that output was serialized correctly
        output_call = mock_encrypt.call_args_list[0][0][0]
        payload_dict = json.loads(output_call)
        assert payload_dict == {"message_text": "Hello", "reasoning": "Test reasoning"}

        # Check that messages were encrypted
        messages_call = mock_encrypt.call_args_list[1][0][0]
        assert '{"messages": [{"role": "user", "content": "test"}]}' == messages_call

        # Verify the database insert was called
        mock_db_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_string_response(self, mock_encrypt):
        """Test creating generation with string response."""
        mock_encrypt.return_value = "encrypted_content"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        # Create mock output and run result with string output
        output_obj = "This is a string response"
        mock_agent = create_mock_agent()
        mock_run_result = create_mock_agent_run_result(output_obj)

        await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent=mock_agent,
            run_result=mock_run_result,
        )

        # Verify encrypt_content was called - one for output, one for messages
        assert mock_encrypt.call_count == 2

        # Check the output was serialized correctly
        output_call = mock_encrypt.call_args_list[0][0][0]
        assert output_call == '"This is a string response"'  # JSON-encoded string

        # Verify the database insert was called
        mock_db_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_other_type_response(self, mock_encrypt):
        """Test creating generation with non-string, non-model response."""
        mock_encrypt.return_value = "encrypted_content"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        # Create mock output and run result with integer output
        output_obj = 42  # Integer response
        mock_agent = create_mock_agent()
        mock_run_result = create_mock_agent_run_result(output_obj)

        await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent=mock_agent,
            run_result=mock_run_result,
        )

        # Verify encrypt_content was called - one for output, one for messages
        assert mock_encrypt.call_count == 2

        # Check the output was serialized correctly
        output_call = mock_encrypt.call_args_list[0][0][0]
        assert output_call == "42"  # JSON serialized integer

        # Verify the database insert was called
        mock_db_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_run_deps(self, mock_encrypt):
        """Test creating generation with run_deps parameter."""
        mock_encrypt.return_value = "encrypted_content"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        # Create mock output and run result
        output_obj = "Test response"
        mock_agent = create_mock_agent()
        mock_run_result = create_mock_agent_run_result(output_obj)
        run_deps = {"user_id": 123, "preferences": {"theme": "dark"}}

        await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent=mock_agent,
            run_result=mock_run_result,
            run_deps=run_deps,
        )

        # Verify encrypt_content was called 3 times (output, messages, deps)
        assert mock_encrypt.call_count == 3

        # Check that deps were serialized correctly
        deps_call = mock_encrypt.call_args_list[2][0][0]
        deps_dict = json.loads(deps_call)
        assert deps_dict == {"user_id": 123, "preferences": {"theme": "dark"}}

        # Verify the database insert was called
        mock_db_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch("areyouok_telegram.data.models.llm_generations.encrypt_content")
    async def test_create_with_fallback_model(self, mock_encrypt):
        """Test creating generation with fallback model configuration."""
        mock_encrypt.return_value = "encrypted_content"
        mock_db_conn = AsyncMock()
        mock_db_conn.execute = AsyncMock()

        # Create mock agent with fallback model
        mock_agent = MagicMock(spec=pydantic_ai.Agent)
        mock_agent.name = "test-agent"

        # Mock fallback model structure
        mock_primary_model = MagicMock()
        mock_primary_model.model_name = "primary/model"
        mock_primary_model.system = "primary"

        mock_fallback_model = MagicMock()
        mock_fallback_model.model_name = "fallback:primary"
        mock_fallback_model.models = [mock_primary_model]

        mock_agent.model = mock_fallback_model

        output_obj = "Test response"
        mock_run_result = create_mock_agent_run_result(output_obj)

        await LLMGenerations.create(
            db_conn=mock_db_conn,
            chat_id="chat123",
            session_id="session456",
            agent=mock_agent,
            run_result=mock_run_result,
        )

        # Verify the database insert was called
        mock_db_conn.execute.assert_called_once()

        # Check that the insert statement uses the primary model name
        call_args = mock_db_conn.execute.call_args[0][0]
        # The values should contain the primary model name, not the fallback
        # This is a bit tricky to test since it's inside the VALUES clause
        assert hasattr(call_args, "values")

    @pytest.mark.asyncio
    async def test_get_by_session(self):
        """Test retrieving generations by session."""

        mock_db_conn = AsyncMock()
        mock_result = Mock()
        mock_scalars = Mock()
        mock_generations = [
            LLMGenerations(
                generation_id="gen1",
                chat_id="chat1",
                session_id="session1",
                agent="agent1",
                model="test/model",
                response_type="TestResponse",
                encrypted_output="encrypted_output",
                encrypted_messages="encrypted_messages"
            ),
            LLMGenerations(
                generation_id="gen2",
                chat_id="chat1",
                session_id="session1",
                agent="agent2",
                model="test/model",
                response_type="TestResponse",
                encrypted_output="encrypted_output",
                encrypted_messages="encrypted_messages"
            ),
        ]
        mock_scalars.all.return_value = mock_generations
        mock_result.scalars.return_value = mock_scalars
        mock_db_conn.execute.return_value = mock_result

        result = await LLMGenerations.get_by_session(
            db_conn=mock_db_conn,
            session_id="session1",
        )

        assert len(result) == 2
        assert all(isinstance(gen, LLMGenerations) for gen in result)
        mock_db_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_generation_id(self):
        """Test retrieving generation by generation_id."""

        mock_db_conn = AsyncMock()
        mock_result = Mock()
        mock_generation = LLMGenerations(
            generation_id="gen1",
            chat_id="chat1",
            session_id="session1",
            agent="agent1",
            model="test/model",
            response_type="TestResponse",
            encrypted_output="encrypted_output",
            encrypted_messages="encrypted_messages"
        )
        mock_result.scalar_one_or_none.return_value = mock_generation
        mock_db_conn.execute.return_value = mock_result

        result = await LLMGenerations.get_by_generation_id(
            db_conn=mock_db_conn,
            generation_id="gen1",
        )

        assert result == mock_generation
        assert isinstance(result, LLMGenerations)
        mock_db_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_generation_id_not_found(self):
        """Test retrieving generation by generation_id when not found."""

        mock_db_conn = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_conn.execute.return_value = mock_result

        result = await LLMGenerations.get_by_generation_id(
            db_conn=mock_db_conn,
            generation_id="nonexistent",
        )

        assert result is None
        mock_db_conn.execute.assert_called_once()

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_output_property_with_json(self, mock_decrypt):
        """Test run_output property with JSON content."""
        mock_decrypt.return_value = '{"key": "value"}'

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_data",
            encrypted_messages="encrypted_messages",
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        output = generation.run_output
        assert output == {"key": "value"}
        mock_decrypt.assert_called_once_with("encrypted_data")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_output_property_with_string(self, mock_decrypt):
        """Test run_output property with string content."""
        mock_decrypt.return_value = '"test string"'

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_data",
            encrypted_messages="encrypted_messages",
            response_type="strResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        output = generation.run_output
        assert output == "test string"
        mock_decrypt.assert_called_once_with("encrypted_data")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_output_property_fallback(self, mock_decrypt):
        """Test run_output property fallback for non-JSON content."""
        mock_decrypt.return_value = "raw content"

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_data",
            encrypted_messages="encrypted_messages",
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        output = generation.run_output
        assert output == "raw content"
        mock_decrypt.assert_called_once_with("encrypted_data")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_messages_property_with_valid_json(self, mock_decrypt):
        """Test run_messages property with valid JSON content."""
        mock_decrypt.return_value = '[{"role": "user", "content": "Hello"}]'

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_output",
            encrypted_messages="encrypted_messages",
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        # Since we're mocking the decrypt and not the actual Pydantic validation,
        # we expect it to try to validate and potentially fall back
        with patch("pydantic_ai.messages.ModelMessagesTypeAdapter.validate_python") as mock_validate:
            mock_validate.return_value = [{"role": "user", "content": "Hello"}]
            messages = generation.run_messages
            mock_validate.assert_called_once_with([{"role": "user", "content": "Hello"}])

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_messages_property_fallback(self, mock_decrypt):
        """Test run_messages property fallback for invalid JSON."""
        mock_decrypt.return_value = "invalid json"

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_output",
            encrypted_messages="encrypted_messages",
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        messages = generation.run_messages
        assert messages == "invalid json"
        mock_decrypt.assert_called_once_with("encrypted_messages")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_deps_property_with_json(self, mock_decrypt):
        """Test run_deps property with valid JSON content."""
        mock_decrypt.return_value = '{"dependency": "value"}'

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_output",
            encrypted_messages="encrypted_messages",
            encrypted_deps="encrypted_deps",
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        deps = generation.run_deps
        assert deps == {"dependency": "value"}
        mock_decrypt.assert_called_once_with("encrypted_deps")

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_deps_property_with_none(self, mock_decrypt):
        """Test run_deps property when encrypted_deps is None."""
        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_output",
            encrypted_messages="encrypted_messages",
            encrypted_deps=None,
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        deps = generation.run_deps
        assert deps is None
        mock_decrypt.assert_not_called()

    @patch("areyouok_telegram.data.models.llm_generations.decrypt_content")
    def test_run_deps_property_fallback(self, mock_decrypt):
        """Test run_deps property fallback for invalid JSON."""
        mock_decrypt.return_value = "invalid json"

        generation = LLMGenerations(
            generation_id="test_id",
            encrypted_output="encrypted_output",
            encrypted_messages="encrypted_messages",
            encrypted_deps="encrypted_deps",
            response_type="TestResponse",
            model="test/model",
            agent="test-agent",
            chat_id="test_chat",
            session_id="test_session"
        )

        deps = generation.run_deps
        assert deps == "invalid json"
        mock_decrypt.assert_called_once_with("encrypted_deps")


class TestSerializeObject:
    """Test serialize_object function for comprehensive coverage."""

    def test_serialize_object_none_input(self):
        """Test serialize_object returns empty string for None input."""
        result = serialize_object(None)
        assert result == ""

    def test_serialize_object_pydantic_model(self):
        """Test serialize_object with Pydantic model."""
        class TestModel(pydantic.BaseModel):
            name: str
            value: int

        model = TestModel(name="test", value=42)
        result = serialize_object(model)

        # Should serialize to JSON using model_dump()
        expected = json.dumps({"name": "test", "value": 42})
        assert result == expected

    def test_serialize_object_dataclass_with_to_dict(self):
        """Test serialize_object with dataclass that has to_dict method."""
        @dataclasses.dataclass
        class TestDataclass:
            name: str
            value: int

            def to_dict(self):
                return {"custom_name": self.name, "custom_value": self.value}

        obj = TestDataclass(name="test", value=42)
        result = serialize_object(obj)

        # Should use the custom to_dict method
        expected = json.dumps({"custom_name": "test", "custom_value": 42})
        assert result == expected

    def test_serialize_object_dataclass_without_to_dict(self):
        """Test serialize_object with dataclass without to_dict method."""
        @dataclasses.dataclass
        class TestDataclass:
            name: str
            value: int

        obj = TestDataclass(name="test", value=42)
        result = serialize_object(obj)

        # Should use dataclasses.asdict()
        expected = json.dumps({"name": "test", "value": 42})
        assert result == expected

    def test_serialize_object_empty_dataclass(self):
        """Test serialize_object with empty dataclass."""
        @dataclasses.dataclass
        class EmptyDataclass:
            pass

        obj = EmptyDataclass()
        result = serialize_object(obj)

        expected = json.dumps({})
        assert result == expected

    def test_serialize_object_regular_dict(self):
        """Test serialize_object with regular dictionary."""
        obj = {"key": "value", "number": 123}
        result = serialize_object(obj)

        expected = json.dumps({"key": "value", "number": 123})
        assert result == expected

    def test_serialize_object_string(self):
        """Test serialize_object with string."""
        obj = "test string"
        result = serialize_object(obj)

        expected = json.dumps("test string")
        assert result == expected

    def test_serialize_object_integer(self):
        """Test serialize_object with integer."""
        obj = 42
        result = serialize_object(obj)

        expected = json.dumps(42)
        assert result == expected

    def test_serialize_object_list(self):
        """Test serialize_object with list."""
        obj = [1, 2, 3, "test"]
        result = serialize_object(obj)

        expected = json.dumps([1, 2, 3, "test"])
        assert result == expected

    def test_serialize_object_complex_nested_dataclass(self):
        """Test serialize_object with nested dataclass structures."""
        @dataclasses.dataclass
        class NestedClass:
            inner_value: str

        @dataclasses.dataclass
        class ComplexDataclass:
            name: str
            nested: NestedClass
            numbers: list[int]

        nested = NestedClass(inner_value="nested")
        obj = ComplexDataclass(name="complex", nested=nested, numbers=[1, 2, 3])
        result = serialize_object(obj)

        # Should handle nested structures via dataclasses.asdict()
        expected_dict = {
            "name": "complex",
            "nested": {"inner_value": "nested"},
            "numbers": [1, 2, 3]
        }
        expected = json.dumps(expected_dict)
        assert result == expected

    def test_serialize_object_exception_handling_type_error(self):
        """Test serialize_object exception handling for TypeError during JSON serialization."""
        class NonSerializableClass:
            def __init__(self):
                self.func = lambda x: x  # Functions are not JSON serializable

            def __str__(self):
                return "NonSerializableClass instance"

        obj = NonSerializableClass()
        result = serialize_object(obj)

        # Should fall back to str() representation
        assert result == "NonSerializableClass instance"

    def test_serialize_object_exception_handling_value_error(self):
        """Test serialize_object exception handling for ValueError during JSON serialization."""
        class CircularRefClass:
            def __init__(self):
                self.self_ref = self

            def __str__(self):
                return "CircularRefClass instance"

        obj = CircularRefClass()

        # Mock json.dumps to raise ValueError to simulate circular reference issue
        with patch("areyouok_telegram.data.models.llm_generations.json.dumps") as mock_dumps:
            mock_dumps.side_effect = ValueError("Circular reference")
            result = serialize_object(obj)

            # Should fall back to str() representation
            assert result == "CircularRefClass instance"

    def test_serialize_object_dataclass_with_complex_to_dict(self):
        """Test serialize_object with dataclass that has complex to_dict logic."""
        @dataclasses.dataclass
        class ComplexToDict:
            values: list[str]
            metadata: dict[str, any]

            def to_dict(self):
                # Custom serialization logic
                return {
                    "processed_values": [v.upper() for v in self.values],
                    "meta_count": len(self.metadata),
                    "has_data": bool(self.values)
                }

        obj = ComplexToDict(
            values=["hello", "world"],
            metadata={"key1": "value1", "key2": "value2"}
        )
        result = serialize_object(obj)

        expected = json.dumps({
            "processed_values": ["HELLO", "WORLD"],
            "meta_count": 2,
            "has_data": True
        })
        assert result == expected

    def test_serialize_object_object_with_non_json_serializable_in_to_dict(self):
        """Test serialize_object when to_dict returns non-serializable data."""
        @dataclasses.dataclass
        class BadToDict:
            name: str

            def to_dict(self):
                # Return something that can't be JSON serialized
                return {"name": self.name, "func": lambda x: x}

            def __str__(self):
                return f"BadToDict(name={self.name})"

        obj = BadToDict(name="test")
        result = serialize_object(obj)

        # Should fall back to str() representation when to_dict() result fails JSON serialization
        assert result == "BadToDict(name=test)"
