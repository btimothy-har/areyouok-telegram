"""Chat-related test helper utilities."""

import json
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock

import pydantic_ai

from areyouok_telegram.data.models.media import MediaFiles


def create_message_dict(text="Test", message_id="123", timestamp="10 seconds ago", reasoning=None):
    """Helper to create consistent message dictionaries."""
    result = {
        "text": text,
        "message_id": message_id,
        "timestamp": timestamp,
    }
    if reasoning:
        result["reasoning"] = reasoning
    return result


def assert_model_message_format(model_message, expected_type):
    """Helper to validate pydantic_ai message structure."""
    assert isinstance(model_message, expected_type)

    if expected_type == pydantic_ai.messages.ModelRequest:
        assert model_message.kind == "request"
        assert len(model_message.parts) >= 1
        assert isinstance(model_message.parts[0], pydantic_ai.messages.UserPromptPart)
        assert model_message.parts[0].part_kind == "user-prompt"

    elif expected_type == pydantic_ai.messages.ModelResponse:
        assert model_message.kind == "response"
        assert len(model_message.parts) >= 1
        assert isinstance(model_message.parts[0], pydantic_ai.messages.TextPart)
        assert model_message.parts[0].part_kind == "text"


def create_mock_media_files(count=1, mime_type="image/png", *, is_anthropic_supported=True):
    """Helper to create mock media file objects."""
    files = []
    for _ in range(count):
        mock_file = MagicMock(spec=MediaFiles)
        mock_file.mime_type = mime_type
        mock_file.is_anthropic_supported = is_anthropic_supported
        mock_file.bytes_data = b"fake image data"
        files.append(mock_file)

    return files if count > 1 else files[0]


def assert_json_content_structure(content, expected_keys):
    """Helper to validate JSON content structure."""
    try:
        content_dict = json.loads(content)
    except json.JSONDecodeError as e:
        msg = f"Content is not valid JSON: {content}"
        raise AssertionError(msg) from e

    for key in expected_keys:
        assert key in content_dict, f"Expected key '{key}' not found in content: {content_dict}"

    return content_dict


def create_timestamp_reference(seconds_ago=0):
    """Helper to create timestamp references for testing."""
    base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)  # Match FROZEN_TIME
    return base_time - timedelta(seconds=seconds_ago)
