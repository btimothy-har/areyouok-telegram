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

from areyouok_telegram.llms.chat import ChatAgentDependencies
from areyouok_telegram.llms.chat import chat_agent
from areyouok_telegram.llms.chat.agent import validate_agent_response
from areyouok_telegram.llms.chat.exceptions import InvalidMessageError
from areyouok_telegram.llms.chat.exceptions import ReactToSelfError
from areyouok_telegram.llms.chat.exceptions import UnacknowledgedImportantMessageError
from areyouok_telegram.llms.chat.responses import AgentResponse
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import TextResponse


@pytest.fixture
def override_chat_agent():
    with chat_agent.override(model=TestModel()):
        yield


@pytest.mark.usefixtures("override_chat_agent")
class TestAreyouokAgent:
    """Test suite for the areyouok agent functionality."""

    @pytest.mark.asyncio
    async def test_agent_basic_response(self, async_database_connection):
        """Test basic agent response generation using TestModel."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
        )

        result = await chat_agent.run("I'm feeling really overwhelmed today", deps=test_deps)

        # TestModel returns a summary by default
        assert result.output is not None
        assert isinstance(result.output, AgentResponse)

    @pytest.mark.asyncio
    async def test_agent_produces_text_response(self, async_database_connection):
        """Test agent produces TextResponse (the first/default output type)."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
        )

        result = await chat_agent.run("I'm having a really hard time", deps=test_deps)

        # Verify the response is TextResponse and has required fields
        assert isinstance(result.output, TextResponse)
        assert result.output.reasoning is not None
        assert result.output.message_text is not None
        assert isinstance(result.output.message_text, str)

    @pytest.mark.asyncio
    async def test_agent_with_different_contexts(self, async_database_connection):
        """Test agent behavior with different last response contexts."""
        # Create mock dependencies with different contexts
        mock_context = AsyncMock()

        # Test with different last response types
        contexts = ["TextResponse", "ReactionResponse", "DoNothingResponse", "no_previous_response"]

        for last_response in contexts:
            test_deps = ChatAgentDependencies(
                tg_context=mock_context,
                tg_chat_id="123456789",
                tg_session_id="test_session_id",
                last_response_type=last_response,
                db_connection=async_database_connection,
            )

            result = await chat_agent.run(f"Testing with {last_response}", deps=test_deps)

            # Should always produce TextResponse with TestModel
            assert isinstance(result.output, TextResponse)
            assert result.output.reasoning is not None

    @pytest.mark.asyncio
    async def test_agent_handles_multiple_conversation_turns(self, async_database_connection):
        """Test agent with multiple conversation turns."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="TextResponse",
            db_connection=async_database_connection,
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
    async def test_validate_agent_response_invalid_message(self, async_database_connection):
        """Test validation fails when message ID doesn't exist."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
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
    async def test_validate_agent_response_react_to_self(self, async_database_connection):
        """Test validation fails when trying to react to own message."""
        # Create mock dependencies
        mock_context = AsyncMock()
        mock_context.bot.id = 999999999

        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
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
    async def test_validate_agent_response_success(self, async_database_connection):
        """Test validation succeeds with valid message from different user."""
        # Create mock dependencies
        mock_context = AsyncMock()
        mock_context.bot.id = 999999999

        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
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
    async def test_validate_agent_response_text_response_passthrough(self, async_database_connection):
        """Test validation passes through TextResponse without checks."""
        # Create mock dependencies
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
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

    @pytest.mark.asyncio
    async def test_validate_agent_response_with_instruction_text_response_pass(self, async_database_connection):
        """Test validation with instruction passes when text response acknowledges it."""
        # Create mock dependencies with instruction
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
            instruction="The user sent a video file, but you can only view images and PDFs.",
        )

        # Create a TextResponse that acknowledges the instruction
        text_response = TextResponse(
            reasoning="User sent video, need to acknowledge",
            message_text="I see you sent a video, but I can only view images and PDFs.",
            reply_to_message_id=None,
        )

        # Mock content check agent to pass
        mock_content_check_run = MagicMock()
        mock_content_check_run.output.check_pass = True
        mock_content_check_run.usage.return_value = Usage()

        with patch("areyouok_telegram.llms.chat.agent.content_check_agent.run", return_value=mock_content_check_run):
            with patch("areyouok_telegram.data.llm_usage.LLMUsage.track_pydantic_usage", new_callable=AsyncMock):
                # Create proper RunContext with required parameters
                ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

                # Should pass validation
                result = await validate_agent_response(ctx, text_response)

                assert result == text_response

    @pytest.mark.asyncio
    async def test_validate_agent_response_with_instruction_text_response_fail(self, async_database_connection):
        """Test validation with instruction fails when text response doesn't acknowledge it."""
        # Create mock dependencies with instruction
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
            instruction="The user sent a video file, but you can only view images and PDFs.",
        )

        # Create a TextResponse that doesn't acknowledge the instruction
        text_response = TextResponse(
            reasoning="User needs support",
            message_text="How are you feeling today?",
            reply_to_message_id=None,
        )

        # Mock content check agent to fail
        mock_content_check_run = MagicMock()
        mock_content_check_run.output.check_pass = False
        mock_content_check_run.output.feedback = "You didn't acknowledge the video file"
        mock_content_check_run.usage.return_value = Usage()

        with patch("areyouok_telegram.llms.chat.agent.content_check_agent.run", return_value=mock_content_check_run):
            with patch("areyouok_telegram.data.llm_usage.LLMUsage.track_pydantic_usage", new_callable=AsyncMock):
                # Create proper RunContext with required parameters
                ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

                with pytest.raises(UnacknowledgedImportantMessageError) as exc_info:
                    await validate_agent_response(ctx, text_response)

                assert "video file" in str(exc_info.value)
                assert "You didn't acknowledge the video file" in exc_info.value.feedback

    @pytest.mark.asyncio
    async def test_validate_agent_response_with_instruction_non_text_response(self, async_database_connection):
        """Test validation with instruction fails for non-text responses."""
        # Create mock dependencies with instruction
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
            instruction="The user sent a video file, but you can only view images and PDFs.",
        )

        # Create a ReactionResponse (non-text response)
        reaction_response = ReactionResponse(
            reasoning="React to message",
            react_to_message_id="123",
            emoji=ReactionEmoji.THUMBS_UP,
        )

        # Mock message lookup for reaction validation
        mock_message = MagicMock()
        mock_message.from_user.id = 123456  # Different from bot
        with patch("areyouok_telegram.data.Messages.retrieve_message_by_id", return_value=(mock_message, None)):
            # Create proper RunContext with required parameters
            ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

            with pytest.raises(UnacknowledgedImportantMessageError) as exc_info:
                await validate_agent_response(ctx, reaction_response)

            assert "video file" in str(exc_info.value)
            assert not exc_info.value.feedback  # Empty feedback for non-text responses

    @pytest.mark.asyncio
    async def test_validate_agent_response_with_instruction_do_nothing_response(self, async_database_connection):
        """Test validation with instruction fails for DoNothingResponse."""
        # Create mock dependencies with instruction
        mock_context = AsyncMock()
        test_deps = ChatAgentDependencies(
            tg_context=mock_context,
            tg_chat_id="123456789",
            tg_session_id="test_session_id",
            last_response_type="no_previous_response",
            db_connection=async_database_connection,
            instruction="The user sent a video file, but you can only view images and PDFs.",
        )

        # Create a DoNothingResponse
        do_nothing_response = DoNothingResponse(
            reasoning="Nothing to say",
        )

        # Create proper RunContext with required parameters
        ctx = RunContext(deps=test_deps, messages=[], retry=0, model=TestModel(), usage=Usage())

        with pytest.raises(UnacknowledgedImportantMessageError) as exc_info:
            await validate_agent_response(ctx, do_nothing_response)

        assert "video file" in str(exc_info.value)
        assert not exc_info.value.feedback  # Empty feedback for non-text responses
