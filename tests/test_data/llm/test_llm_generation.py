"""Tests for LLMGeneration model."""

import dataclasses
from datetime import UTC, datetime

import pydantic
import pytest

from areyouok_telegram.data.models.llm.llm_generation import LLMGeneration, serialize_to_jsonb


def test_serialize_to_jsonb_pydantic_model():
    """Test serialize_to_jsonb() with Pydantic model."""

    class TestModel(pydantic.BaseModel):
        x: int
        y: str

    obj = TestModel(x=1, y="a")
    result = serialize_to_jsonb(obj)
    assert result == {"x": 1, "y": "a"}
    assert isinstance(result, dict)


def test_serialize_to_jsonb_dataclass():
    """Test serialize_to_jsonb() with dataclass."""

    @dataclasses.dataclass
    class TestData:
        a: int

    obj = TestData(a=5)
    result = serialize_to_jsonb(obj)
    assert result == {"a": 5}
    assert isinstance(result, dict)


def test_serialize_to_jsonb_none():
    """Test serialize_to_jsonb() returns None for None."""
    assert serialize_to_jsonb(None) is None


def test_serialize_to_jsonb_string():
    """Test serialize_to_jsonb() passes through strings."""
    result = serialize_to_jsonb("test string")
    assert result == "test string"
    assert isinstance(result, str)


def test_serialize_to_jsonb_primitives():
    """Test serialize_to_jsonb() passes through primitives."""
    assert serialize_to_jsonb(42) == 42
    assert serialize_to_jsonb(3.14) == 3.14
    assert serialize_to_jsonb(True) is True  # noqa: FBT003


def test_serialize_to_jsonb_fallback():
    """Test serialize_to_jsonb() falls back with metadata for non-serializable objects."""

    class CustomObj:
        def __str__(self):
            return "custom"

    result = serialize_to_jsonb(CustomObj())
    assert isinstance(result, dict)
    assert result["_serialized_fallback"] is True
    assert result["_type"] == "CustomObj"
    assert result["_value"] == "custom"


def test_serialize_to_jsonb_nested_pydantic():
    """Test serialize_to_jsonb() handles nested Pydantic models correctly."""

    class InnerModel(pydantic.BaseModel):
        value: int

    class OuterModel(pydantic.BaseModel):
        name: str
        inner: InnerModel

    obj = OuterModel(name="test", inner=InnerModel(value=42))
    result = serialize_to_jsonb(obj)
    assert result == {"name": "test", "inner": {"value": 42}}
    assert isinstance(result, dict)
    assert isinstance(result["inner"], dict)


def test_serialize_to_jsonb_dataclass_with_to_dict():
    """Test serialize_to_jsonb() uses to_dict() method when available."""

    @dataclasses.dataclass
    class DataWithToDict:
        x: int

        def to_dict(self) -> dict:
            return {"x": self.x, "custom": "value"}

    obj = DataWithToDict(x=10)
    result = serialize_to_jsonb(obj)
    assert result == {"x": 10, "custom": "value"}
    assert isinstance(result, dict)


def test_serialize_to_jsonb_dataclass_with_pydantic_and_to_dict():
    """Test serialize_to_jsonb() with dataclass containing Pydantic models that has to_dict()."""

    class PydanticModel(pydantic.BaseModel):
        id: int
        name: str

    @dataclasses.dataclass
    class DataWithPydanticAndToDict:
        user: PydanticModel
        chat: PydanticModel

        def to_dict(self) -> dict:
            # Simulate the pattern used in agent dependencies
            return {
                "user_id": self.user.id,
                "chat_id": self.chat.id,
            }

    user = PydanticModel(id=1, name="Alice")
    chat = PydanticModel(id=2, name="Chat")
    obj = DataWithPydanticAndToDict(user=user, chat=chat)

    result = serialize_to_jsonb(obj)
    assert result == {"user_id": 1, "chat_id": 2}
    assert isinstance(result, dict)
    # Verify it's serialized to IDs, not full Pydantic models
    assert "name" not in result


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_llm_generation_save_and_get_by_id(mock_db_session):
    """Test LLMGeneration.save() serializes JSONB and get_by_id() deserializes."""
    gen = LLMGeneration(
        chat_id=1,
        session_id=2,
        agent="test_agent",
        model="gpt-4",
        timestamp=datetime.now(UTC),
        response_type="str",
        output={"result": "ok"},
        messages=[],
        deps=None,
    )

    output_dict, messages_list, deps_dict = gen._serialize_for_storage()

    class Row:
        id = 20
        chat_id = 1
        session_id = 2
        agent = "test_agent"
        model = "gpt-4"
        timestamp = gen.timestamp
        response_type = "str"
        output = output_dict
        messages = messages_list
        deps = deps_dict

    class _ResOne:
        def scalar_one(self):
            return Row()

    mock_db_session.execute.return_value = _ResOne()
    saved = await gen.save()
    assert saved.id == 20

    # get_by_id
    class _ResOneOrNone:
        def scalar_one_or_none(self):
            return Row()

    mock_db_session.execute.return_value = _ResOneOrNone()
    fetched = await LLMGeneration.get_by_id(generation_id=20)
    assert fetched and fetched.agent == "test_agent"


@pytest.mark.usefixtures("patch_async_database")
@pytest.mark.asyncio
async def test_llm_generation_delete(mock_db_session):
    """Test LLMGeneration.delete() removes a single generation record."""
    gen = LLMGeneration(
        id=42,
        chat_id=1,
        session_id=2,
        agent="test_agent",
        model="gpt-4",
        timestamp=datetime.now(UTC),
        response_type="str",
        output={"result": "ok"},
        messages=[],
        deps=None,
    )

    class MockResult:
        pass

    mock_db_session.execute.return_value = MockResult()

    await gen.delete()

    assert mock_db_session.execute.called
    call_args = mock_db_session.execute.call_args
    stmt = call_args[0][0]
    assert "DELETE" in str(stmt).upper()
