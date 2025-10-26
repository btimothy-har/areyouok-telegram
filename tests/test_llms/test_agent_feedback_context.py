"""Tests for llms/agent_feedback_context.py."""

from areyouok_telegram.llms.agent_feedback_context import ContextAgentDependencies, feedback_context_agent


class TestFeedbackContextAgent:
    """Test the feedback_context_agent configuration and components."""

    def test_feedback_context_agent_configuration(self):
        """Test that agent is configured correctly."""
        assert feedback_context_agent.name == "feedback_context_agent"
        assert feedback_context_agent.end_strategy == "exhaustive"

    def test_feedback_context_agent_has_model(self):
        """Test that the agent has a model configured."""
        assert feedback_context_agent.model is not None

    def test_feedback_context_agent_has_instructions(self):
        """Test that the agent has instructions configured."""
        # Check that the agent has instructions functions
        assert len(feedback_context_agent._instructions_functions) > 0

    def test_feedback_context_agent_has_output_validator(self):
        """Test that the agent has an output validator configured."""
        # Check that the agent has output validators
        assert len(feedback_context_agent._output_validators) > 0

    def test_context_agent_dependencies_structure(self, chat_factory):
        """Test that ContextAgentDependencies is properly structured."""
        mock_chat = chat_factory(id_value=123)
        mock_session = MagicMock()
        mock_session.id = 456
        
        deps = ContextAgentDependencies(chat=mock_chat, session=mock_session)
        assert deps.chat == mock_chat
        assert deps.session == mock_session

    def test_context_agent_dependencies_dataclass(self, chat_factory):
        """Test that ContextAgentDependencies behaves as expected dataclass."""
        mock_chat = chat_factory(id_value=789)
        mock_session = MagicMock()
        mock_session.id = 101
        
        deps = ContextAgentDependencies(chat=mock_chat, session=mock_session)

        # Test that it's a dataclass
        assert dataclasses.is_dataclass(deps)

        # Test string representation
        deps_str = str(deps)
        assert "chat_id" in deps_str
        assert "session_id" in deps_str
