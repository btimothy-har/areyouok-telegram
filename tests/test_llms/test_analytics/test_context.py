"""Tests for the DynamicContextCompression module."""

from datetime import UTC
from datetime import datetime
from unittest.mock import MagicMock
from unittest.mock import patch

import dspy
import pytest
from telegram import Message
from telegram import User

from areyouok_telegram.llms.analytics.context import DynamicContextCompression


@pytest.fixture
def mock_messages():
    """Create mock Telegram messages for testing."""
    user = User(id=123, first_name="Test", is_bot=False)

    msg1 = MagicMock(spec=Message)
    msg1.date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    msg1.text = "I'm feeling really stressed about work lately"
    msg1.from_user = user
    msg1.message_id = 1

    msg2 = MagicMock(spec=Message)
    msg2.date = datetime(2025, 1, 15, 10, 1, 0, tzinfo=UTC)
    msg2.text = "The deadlines are piling up and I can't sleep"
    msg2.from_user = user
    msg2.message_id = 2

    return [msg1, msg2]


class TestDynamicContextCompression:
    """Test the DynamicContextCompression class."""

    def test_init(self):
        """Test initialization of DynamicContextCompression."""
        compressor = DynamicContextCompression()

        assert hasattr(compressor, "analysis")
        assert isinstance(compressor.analysis, dspy.ChainOfThought)

    @patch("areyouok_telegram.llms.analytics.context.dspy.ChainOfThought")
    def test_forward_success(self, mock_chain_of_thought, mock_messages):
        """Test forward method successfully compresses context."""
        # Mock the ChainOfThought result
        mock_analysis = MagicMock()
        mock_prediction = MagicMock()
        mock_prediction.life_situation = "Work stress and deadlines"
        mock_prediction.connection = "User seeks support for stress"
        mock_prediction.personal_context = "Professional dealing with workload"
        mock_prediction.conversation = "Initial disclosure about work stress"
        mock_prediction.practical_matters = "Managing deadlines and sleep issues"
        mock_prediction.feedback = "Open to discussing stress"
        mock_prediction.others = "No relevant information."

        mock_analysis.return_value = mock_prediction
        mock_chain_of_thought.return_value = mock_analysis

        compressor = DynamicContextCompression()
        result = compressor.forward(mock_messages)

        # Verify the result
        assert isinstance(result, dspy.Prediction)
        assert "## Life Situation\nWork stress and deadlines" in result.context
        assert "## Connection\nUser seeks support for stress" in result.context
        assert "## Personal Context\nProfessional dealing with workload" in result.context
        assert "## Conversation\nInitial disclosure about work stress" in result.context
        assert "## Practical Matters\nManaging deadlines and sleep issues" in result.context
        assert "## Feedback\nOpen to discussing stress" in result.context
        assert "## Others\nNo relevant information." in result.context

        # Verify the analysis was called with proper message format
        mock_analysis.assert_called_once()
        call_args = mock_analysis.call_args
        messages_arg = call_args.kwargs["messages"]

        # Should have 2 messages formatted as dicts
        assert len(messages_arg) == 2
        # Messages are dicts, not JSON strings
        assert messages_arg[0]["text"] == "I'm feeling really stressed about work lately"
        assert messages_arg[1]["text"] == "The deadlines are piling up and I can't sleep"
        assert "timestamp" in messages_arg[0]
        assert "message_id" in messages_arg[0]

    @patch("areyouok_telegram.llms.analytics.context.dspy.ChainOfThought")
    def test_forward_empty_messages(self, mock_chain_of_thought):
        """Test forward method with empty message list."""
        # Mock the ChainOfThought result
        mock_analysis = MagicMock()
        mock_prediction = MagicMock()
        mock_prediction.life_situation = "No relevant information."
        mock_prediction.connection = "No relevant information."
        mock_prediction.personal_context = "No relevant information."
        mock_prediction.conversation = "No relevant information."
        mock_prediction.practical_matters = "No relevant information."
        mock_prediction.feedback = "No relevant information."
        mock_prediction.others = "No relevant information."

        mock_analysis.return_value = mock_prediction
        mock_chain_of_thought.return_value = mock_analysis

        compressor = DynamicContextCompression()
        result = compressor.forward([])

        # Verify the result
        assert isinstance(result, dspy.Prediction)
        assert result.context.count("No relevant information.") == 7

        # Verify the analysis was called with empty list
        mock_analysis.assert_called_once()
        call_args = mock_analysis.call_args
        assert call_args.kwargs["messages"] == []

    @patch("areyouok_telegram.llms.analytics.context.dspy.ChainOfThought")
    def test_forward_preserves_usage_data(self, mock_chain_of_thought, mock_messages):
        """Test that forward method preserves LLM usage data."""
        # Mock the ChainOfThought result with usage data
        mock_analysis = MagicMock()
        mock_prediction = MagicMock()
        mock_prediction.life_situation = "Test situation"
        mock_prediction.connection = "Test connection"
        mock_prediction.personal_context = "Test context"
        mock_prediction.conversation = "Test conversation"
        mock_prediction.practical_matters = "Test matters"
        mock_prediction.feedback = "Test feedback"
        mock_prediction.others = "Test others"
        
        # Add usage data to the mock prediction
        usage_data = {
            "openai/gpt-4": {
                "completion_tokens": 100,
                "prompt_tokens": 200,
                "total_tokens": 300,
                "completion_tokens_details": {"test": "data"},
                "prompt_tokens_details": {"test": "data"},
            }
        }
        mock_prediction.get_lm_usage.return_value = usage_data
        
        mock_analysis.return_value = mock_prediction
        mock_chain_of_thought.return_value = mock_analysis
        
        compressor = DynamicContextCompression()
        result = compressor.forward(mock_messages)
        
        # Verify the result has usage data
        assert isinstance(result, dspy.Prediction)
        assert hasattr(result, "get_lm_usage")
        assert result.get_lm_usage() == usage_data
