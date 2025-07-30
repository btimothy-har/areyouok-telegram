"""Tests for the core agent functionality using PydanticAI TestModel.

Testing Strategy:
1. Agent run tests: Focus on testing that the agent produces valid TextResponse (first output type)
2. Response unit tests: Test execution of all response types (TextResponse, ReactionResponse, DoNothingResponse)
3. Validation unit tests: Test the output validator logic as unit functions
"""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import Usage
from telegram.constants import ReactionEmoji

from areyouok_telegram.agent import ChatAgentDependencies
from areyouok_telegram.agent import chat_agent
from areyouok_telegram.agent.chat import validate_agent_response
from areyouok_telegram.agent.exceptions import InvalidMessageError
from areyouok_telegram.agent.exceptions import ReactToSelfError
from areyouok_telegram.agent.responses import AgentResponse
from areyouok_telegram.agent.responses import ReactionResponse
from areyouok_telegram.agent.responses import TextResponse


@pytest.fixture
def override_chat_agent():
    with chat_agent.override(model=TestModel()):
        yield


@pytest.mark.usefixtures("override_chat_agent")
class TestAreyouokAgent:
    """Test suite for the areyouok agent functionality."""

    @pytest.mark.asyncio
    async def test_agent_basic_response(self, mock_async_database_session):
        """Test basic agent response generation using TestModel."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="no_previous_response",
            db_connection=mock_async_database_session,
        )

        result = await chat_agent.run("I'm feeling really overwhelmed today", deps=test_deps)

        # TestModel returns a summary by default
        assert result.output is not None
        assert isinstance(result.output, AgentResponse)

    @pytest.mark.asyncio
    async def test_agent_produces_text_response(self, mock_async_database_session):
        """Test agent produces TextResponse (the first/default output type)."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="no_previous_response",
            db_connection=mock_async_database_session,
        )

        result = await chat_agent.run("I'm having a really hard time", deps=test_deps)

        # Verify the response is TextResponse and has required fields
        assert isinstance(result.output, TextResponse)
        assert result.output.reasoning is not None
        assert result.output.message_text is not None
        assert isinstance(result.output.message_text, str)

    @pytest.mark.asyncio
    async def test_agent_with_different_contexts(self, mock_async_database_session):
        """Test agent behavior with different last response contexts."""
        # Create mock dependencies with different contexts
        mock_context = AsyncMock()

        # Test with different last response types
        contexts = ["TextResponse", "ReactionResponse", "DoNothingResponse", "no_previous_response"]

        for last_response in contexts:
            test_deps = ChatAgentDependencies(
                tg_context=mock_context,
                tg_chat_id="123456789",
                last_response_type=last_response,
                db_connection=mock_async_database_session,
            )

            result = await chat_agent.run(f"Testing with {last_response}", deps=test_deps)

            # Should always produce TextResponse with TestModel
            assert isinstance(result.output, TextResponse)
            assert result.output.reasoning is not None

    @pytest.mark.asyncio
    async def test_agent_handles_multiple_conversation_turns(self, mock_async_database_session):
        """Test agent with multiple conversation turns."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="TextResponse",
            db_connection=mock_async_database_session,
        )

        # Test multiple conversation turns
        conversation_messages = [
            "I've been having trouble sleeping lately",
            "Work has been really stressful",
            "I don't know how to cope with all this pressure",
        ]

        for message in conversation_messages:
            result = await chat_agent.run(message, deps=test_deps)

            # Each response should be valid TextResponse
            assert isinstance(result.output, TextResponse)
            assert result.output.reasoning is not None
            assert result.output.message_text is not None


class TestAgentValidation:
    """Test suite for agent output validation logic as unit functions."""

    @pytest.mark.asyncio
    async def test_validate_agent_response_invalid_message(self, mock_async_database_session):
        """Test validation fails when message ID doesn't exist."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="no_previous_response",
            db_connection=mock_async_database_session,
        )

        # Create a ReactionResponse that will fail validation
        reaction_response = ReactionResponse(
            reasoning="Want to react to non-existent message",
            react_to_message_id="999999",
            emoji=ReactionEmoji.THUMBS_UP,
        )

        # Mock the database lookup to return None (message not found)
        with patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(None, None)):
            # Create proper RunContext with required parameters
            ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

            with pytest.raises(InvalidMessageError) as exc_info:
                await validate_agent_response(ctx, reaction_response)

            assert exc_info.value.message_id == "999999"
            assert "Message with ID 999999 not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_agent_response_react_to_self(self, mock_async_database_session):
        """Test validation fails when trying to react to own message."""
        # Create mock dependencies
        mock_context = AsyncMock()
        mock_context.bot.id = 999999999

        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="no_previous_response",
            db_connection=mock_async_database_session,
        )

        # Mock a message from the bot itself
        mock_message = MagicMock()
        mock_message.from_user.id = 999999999  # Same as bot ID

        # Create a ReactionResponse that will fail validation
        reaction_response = ReactionResponse(
            reasoning="Want to react to my own message", react_to_message_id="123", emoji=ReactionEmoji.RED_HEART
        )

        # Mock the database lookup to return bot's own message
        with patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)):
            # Create proper RunContext with required parameters
            ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

            with pytest.raises(ReactToSelfError) as exc_info:
                await validate_agent_response(ctx, reaction_response)

            assert exc_info.value.message_id == "123"
            assert "You cannot react to your own message 123" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_agent_response_success(self, mock_async_database_session):
        """Test validation succeeds with valid message from different user."""
        # Create mock dependencies
        mock_context = AsyncMock()
        mock_context.bot.id = 999999999

        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="no_previous_response",
            db_connection=mock_async_database_session,
        )

        # Mock a valid message from a different user
        mock_message = MagicMock()
        mock_message.from_user.id = 123456789  # Different from bot ID

        # Create a valid ReactionResponse
        reaction_response = ReactionResponse(
            reasoning="User message deserves a reaction", react_to_message_id="456", emoji=ReactionEmoji.RED_HEART
        )

        # Mock the database lookup to return valid user message
        with patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)):
            # Create proper RunContext with required parameters
            ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

            # Should not raise any exception
            result = await validate_agent_response(ctx, reaction_response)

            # Should return the same response unchanged
            assert result == reaction_response
            assert result.react_to_message_id == "456"
            assert result.emoji == ReactionEmoji.RED_HEART

    @pytest.mark.asyncio
    async def test_validate_agent_response_text_response_passthrough(self, mock_async_database_session):
        """Test validation passes through TextResponse without checks."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            last_response_type="no_previous_response",
            db_connection=mock_async_database_session,
        )

        # Create a TextResponse
        text_response = TextResponse(
            reasoning="User needs supportive message", message_text="I'm here to listen", reply_to_message_id=None
        )

        # Create proper RunContext with required parameters
        ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

        # Should pass through without any validation checks
        result = await validate_agent_response(ctx, text_response)

        # Should return the same response unchanged
        assert result == text_response
        assert result.message_text == "I'm here to listen"
