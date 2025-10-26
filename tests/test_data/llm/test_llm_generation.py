"""Tests for LLMGeneration model."""

import dataclasses
import json
from datetime import UTC, datetime

import pydantic
import pytest

from areyouok_telegram.data.models.llm.llm_generation import LLMGeneration, serialize_object


def test_serialize_object_pydantic_model():
    """Test serialize_object() with Pydantic model."""

    class TestModel(pydantic.BaseModel):
        x: int
        y: str

    obj = TestModel(x=1, y="a")
    result = serialize_object(obj)
    assert json.loads(result) == {"x": 1, "y": "a"}


def test_serialize_object_dataclass():
    """Test serialize_object() with dataclass."""

    @dataclasses.dataclass
    class TestData:
        a: int

    obj = TestData(a=5)
    result = serialize_object(obj)
    assert json.loads(result) == {"a": 5}


def test_serialize_object_none():
    """Test serialize_object() returns empty string for None."""
    assert serialize_object(None) == ""


def test_serialize_object_fallback():
    """Test serialize_object() falls back to str() for non-serializable objects."""

    class CustomObj:
        def __str__(self):
            return "custom"

    result = serialize_object(CustomObj())
    assert result == "custom"


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
