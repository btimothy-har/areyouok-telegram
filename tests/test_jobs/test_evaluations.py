"""Tests for jobs/evaluations.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pydantic_evals
import pytest

from areyouok_telegram.data.models import LLMGeneration
from areyouok_telegram.jobs.evaluations import (
    GEN_CACHE,
    EvaluationsJob,
    PersonalityAlignmentEvaluator,
    ReasoningAlignmentEvaluator,
    SycophancyEvaluator,
    eval_production_response,
    get_generation_by_id_cached,
)


class TestGetGenerationByIdCached:
    """Test the get_generation_by_id_cached function."""

    def setup_method(self):
        """Clear cache before each test."""
        GEN_CACHE.clear()

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit scenario."""
        # Add item to cache
        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.id = 1
        GEN_CACHE["test_gen_id"] = mock_generation

        result = await get_generation_by_id_cached("test_gen_id")

        assert result == mock_generation
        assert "test_gen_id" in GEN_CACHE

    @pytest.mark.asyncio
    async def test_cache_miss_database_retrieval(self, mock_db_session):
        """Test cache miss with database retrieval."""
        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.id = 1

        with patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_id") as mock_get:
            mock_get.return_value = mock_generation

            result = await get_generation_by_id_cached("new_gen_id")

            assert result == mock_generation
            assert GEN_CACHE["new_gen_id"] == mock_generation
            mock_get.assert_called_once_with(mock_db_session, generation_id="new_gen_id")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_cache_miss_none_result(self):
        """Test cache miss with None result from database raises ValueError."""
        with patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_id") as mock_get:
            mock_get.return_value = None

            with pytest.raises(ValueError, match="Generation with ID nonexistent_gen_id not found"):
                await get_generation_by_id_cached("nonexistent_gen_id")

            # Cache should not contain the failed lookup
            assert "nonexistent_gen_id" not in GEN_CACHE


class TestReasoningAlignmentEvaluator:
    """Test the ReasoningAlignmentEvaluator class."""

    @pytest.mark.asyncio
    async def test_evaluate_success_high_score(self):
        """Test evaluate method with high score (> 0.8)."""
        evaluator = ReasoningAlignmentEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_output = {
            "reasoning": "test reasoning",
            "message_text": "test message",
            "other_data": "test",
        }

        mock_eval_return = {
            "ReasoningAlignmentTest": True,
            "ReasoningAlignment": MagicMock(value=0.9, reason="Good reasoning alignment"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch(
                "areyouok_telegram.jobs.evaluations.run_reasoning_alignment_evaluation", return_value=mock_eval_return
            ),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["ReasoningAlignmentTest"] is True
        assert result["ReasoningAlignment"].value == 0.9
        assert result["ReasoningAlignment"].reason == "Good reasoning alignment"

    @pytest.mark.asyncio
    async def test_evaluate_success_low_score(self):
        """Test evaluate method with low score (< 0.8)."""
        evaluator = ReasoningAlignmentEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_output = {"reasoning": "poor reasoning", "message_text": "test message"}

        mock_eval_return = {
            "ReasoningAlignmentTest": False,
            "ReasoningAlignment": MagicMock(value=0.6, reason="Poor reasoning alignment"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch(
                "areyouok_telegram.jobs.evaluations.run_reasoning_alignment_evaluation", return_value=mock_eval_return
            ),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["ReasoningAlignmentTest"] is False
        assert result["ReasoningAlignment"].value == 0.6

    @pytest.mark.asyncio
    async def test_evaluate_removes_reasoning_from_output(self):
        """Test that reasoning is removed from run_output before evaluation."""
        evaluator = ReasoningAlignmentEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        original_output = {"reasoning": "test reasoning", "message_text": "test message", "other_data": "test"}
        mock_generation.run_output.copy.return_value = original_output.copy()

        mock_eval_return = {
            "ReasoningAlignmentTest": True,
            "ReasoningAlignment": MagicMock(value=0.9, reason="Good reasoning alignment"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch(
                "areyouok_telegram.jobs.evaluations.run_reasoning_alignment_evaluation",
                return_value=mock_eval_return,
            ) as mock_run,
        ):
            await evaluator.evaluate(ctx)

        # Check that reasoning was removed from the output passed to the evaluation function
        call_args = mock_run.call_args[1]
        output_arg = call_args["output"]
        assert "reasoning" not in output_arg


class TestPersonalityAlignmentEvaluator:
    """Test the PersonalityAlignmentEvaluator class."""

    @pytest.mark.asyncio
    async def test_evaluate_success_high_score(self):
        """Test evaluate method with high score and personality data."""
        evaluator = PersonalityAlignmentEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_output = {"message_text": "test message"}
        mock_generation.run_deps = MagicMock()
        mock_generation.run_deps.get.return_value = "exploration"

        mock_eval_return = {
            "PersonalityAlignmentTest": True,
            "PersonalityAlignment": MagicMock(value=0.95, reason="Excellent personality alignment"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch(
                "areyouok_telegram.jobs.evaluations.run_personality_alignment_evaluation", return_value=mock_eval_return
            ),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["PersonalityAlignmentTest"] is True
        assert result["PersonalityAlignment"].value == 0.95
        assert result["PersonalityAlignment"].reason == "Excellent personality alignment"

    @pytest.mark.asyncio
    async def test_evaluate_success_low_score(self):
        """Test evaluate method with low score."""
        evaluator = PersonalityAlignmentEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_output = {"message_text": "test message"}
        mock_generation.run_deps = MagicMock()
        mock_generation.run_deps.get.return_value = "anchoring"

        mock_eval_return = {
            "PersonalityAlignmentTest": False,
            "PersonalityAlignment": MagicMock(value=0.7, reason="Poor personality alignment"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch(
                "areyouok_telegram.jobs.evaluations.run_personality_alignment_evaluation", return_value=mock_eval_return
            ),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["PersonalityAlignmentTest"] is False
        assert result["PersonalityAlignment"].value == 0.7
        assert result["PersonalityAlignment"].reason == "Poor personality alignment"

    @pytest.mark.asyncio
    async def test_evaluate_missing_personality(self):
        """Test evaluate method when personality is missing from run_deps."""
        evaluator = PersonalityAlignmentEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_output = {"message_text": "test message"}
        mock_generation.run_deps = MagicMock()
        mock_generation.run_deps.get.return_value = None

        mock_eval_return = {
            "PersonalityAlignmentTest": False,
            "PersonalityAlignment": MagicMock(value=0.5, reason="No personality alignment possible"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch(
                "areyouok_telegram.jobs.evaluations.run_personality_alignment_evaluation", return_value=mock_eval_return
            ),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["PersonalityAlignmentTest"] is False


class TestSycophancyEvaluator:
    """Test the SycophancyEvaluator class."""

    @pytest.mark.asyncio
    async def test_evaluate_success_low_sycophancy(self):
        """Test evaluate method with low sycophancy score (good)."""
        evaluator = SycophancyEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_messages = [{"role": "user", "content": "test"}]

        mock_eval_return = {
            "SycophancyTest": True,
            "Sycophancy": MagicMock(value=0.2, reason="Low sycophancy detected"),
            "SycoAgreement": MagicMock(value=0.3, reason="Agreement strength description"),
            "SycoCritical": MagicMock(value=0.8, reason="Critical engagement description"),
            "SycoDeference": MagicMock(value=0.1, reason="Deference level description"),
            "SycoMimicry": MagicMock(value=0.2, reason="Mimicry level description"),
            "SycoPresupposition": MagicMock(value=0.4, reason="Presupposition alignment description"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch("areyouok_telegram.jobs.evaluations.run_sycophancy_evaluation", return_value=mock_eval_return),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["SycophancyTest"] is True  # < 0.25 threshold
        assert result["Sycophancy"].value == 0.2
        assert result["Sycophancy"].reason == "Low sycophancy detected"
        assert result["SycoAgreement"].value == 0.3
        assert result["SycoCritical"].value == 0.8
        assert result["SycoDeference"].value == 0.1
        assert result["SycoMimicry"].value == 0.2
        assert result["SycoPresupposition"].value == 0.4

    @pytest.mark.asyncio
    async def test_evaluate_success_high_sycophancy(self):
        """Test evaluate method with high sycophancy score (bad)."""
        evaluator = SycophancyEvaluator()

        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.run_messages = [{"role": "user", "content": "test"}]

        mock_eval_return = {
            "SycophancyTest": False,
            "Sycophancy": MagicMock(value=0.8, reason="High sycophancy detected"),
            "SycoAgreement": MagicMock(value=0.9, reason="Agreement strength description"),
            "SycoCritical": MagicMock(value=0.1, reason="Critical engagement description"),
            "SycoDeference": MagicMock(value=0.8, reason="Deference level description"),
            "SycoMimicry": MagicMock(value=0.7, reason="Mimicry level description"),
            "SycoPresupposition": MagicMock(value=0.9, reason="Presupposition alignment description"),
        }

        ctx = MagicMock(spec=pydantic_evals.evaluators.EvaluatorContext)
        ctx.inputs = "test_gen_id"

        with (
            patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation),
            patch("areyouok_telegram.jobs.evaluations.run_sycophancy_evaluation", return_value=mock_eval_return),
        ):
            result = await evaluator.evaluate(ctx)

        assert result["SycophancyTest"] is False  # >= 0.25 threshold
        assert result["Sycophancy"].value == 0.8
        assert result["Sycophancy"].reason == "High sycophancy detected"
        assert result["SycoAgreement"].value == 0.9
        assert result["SycoCritical"].value == 0.1
        assert result["SycoDeference"].value == 0.8
        assert result["SycoMimicry"].value == 0.7
        assert result["SycoPresupposition"].value == 0.9


class TestEvalProductionResponse:
    """Test the eval_production_response function."""

    @pytest.mark.asyncio
    async def test_eval_production_response_success(self):
        """Test eval_production_response with complete data."""
        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.model = "anthropic/claude-3-haiku"
        mock_generation.response_type = "TextResponse"
        mock_generation.run_output = MagicMock()
        mock_generation.run_deps = MagicMock()
        mock_generation.run_output.get.return_value = "test reasoning"
        mock_generation.run_deps.get.return_value = "exploration"

        with patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation):
            result = await eval_production_response("test_gen_id")

        expected = {
            "model": "anthropic/claude-3-haiku",
            "response_type": "TextResponse",
            "reasoning": "test reasoning",
            "personality": "exploration",
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_eval_production_response_missing_data(self):
        """Test eval_production_response with missing reasoning and personality."""
        mock_generation = MagicMock(spec=LLMGenerations)
        mock_generation.model = "anthropic/claude-3-sonnet"
        mock_generation.response_type = "ReactionResponse"
        mock_generation.run_output = MagicMock()
        mock_generation.run_deps = MagicMock()
        mock_generation.run_output.get.return_value = None
        mock_generation.run_deps.get.return_value = None

        with patch("areyouok_telegram.jobs.evaluations.get_generation_by_id_cached", return_value=mock_generation):
            result = await eval_production_response("test_gen_id")

        expected = {
            "model": "anthropic/claude-3-sonnet",
            "response_type": "ReactionResponse",
            "reasoning": None,
            "personality": None,
        }
        assert result == expected


class TestEvaluationsJob:
    """Test the EvaluationsJob class."""

    def test_init(self):
        """Test EvaluationsJob initialization."""
        job = EvaluationsJob("chat123", "session456")

        assert job.chat_id == "chat123"
        assert job.session_id == "session456"

    def test_name_property(self):
        """Test name property generates correct job name."""
        job = EvaluationsJob("chat123", "session456")
        assert job.name == "evaluations:session456"

    def test_evaluated_agents_property(self):
        """Test evaluated_agents property returns correct agent list."""
        job = EvaluationsJob("chat123", "session456")
        expected_agents = ["areyouok_chat_agent", "areyouok_onboarding_agent"]
        assert job.evaluated_agents == expected_agents

    @pytest.mark.asyncio
    async def test_run_job_no_generations(self):
        """Test run_job when no generations are found."""
        job = EvaluationsJob("chat123", "session456")

        with (
            patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_session", return_value=[]),
            patch("logfire.warning") as mock_warning,
        ):
            await job.run_job()

        mock_warning.assert_called_once_with("No generations found for session session456. Skipping evaluations.")

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_run_job_with_generations_reasoning_only(self):
        """Test run_job with generations that have reasoning but no personality."""
        job = EvaluationsJob("chat123", "session456")

        mock_gen1 = MagicMock(spec=LLMGenerations)
        mock_gen1.agent = "areyouok_chat_agent"
        mock_gen1.generation_id = "gen1"
        mock_gen1.run_output = MagicMock()
        mock_gen1.run_deps = MagicMock()
        mock_gen1.run_output.get.side_effect = lambda key: "test reasoning" if key == "reasoning" else None
        mock_gen1.run_deps.get.side_effect = lambda _: None

        mock_dataset = MagicMock(spec=pydantic_evals.Dataset)
        mock_dataset.evaluate = AsyncMock()

        with (
            patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_session", return_value=[mock_gen1]),
            patch("pydantic_evals.Dataset", return_value=mock_dataset),
            patch("areyouok_telegram.jobs.evaluations.ENV", "development"),
        ):
            await job.run_job()

        # Verify dataset creation and evaluation
        mock_dataset.evaluate.assert_called_once()
        call_args = mock_dataset.evaluate.call_args
        assert call_args[1]["name"] == "session456"
        assert call_args[1]["max_concurrency"] == 1
        assert call_args[1]["progress"] is True  # development environment

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_run_job_with_generations_personality_only(self):
        """Test run_job with generations that have personality but no reasoning."""
        job = EvaluationsJob("chat123", "session456")

        mock_gen1 = MagicMock(spec=LLMGenerations)
        mock_gen1.agent = "areyouok_onboarding_agent"
        mock_gen1.generation_id = "gen1"
        mock_gen1.run_output = MagicMock()
        mock_gen1.run_deps = MagicMock()
        mock_gen1.run_output.get.side_effect = lambda _: None
        mock_gen1.run_deps.get.side_effect = lambda key: "exploration" if key == "personality" else None

        mock_dataset = MagicMock(spec=pydantic_evals.Dataset)
        mock_dataset.evaluate = AsyncMock()

        with (
            patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_session", return_value=[mock_gen1]),
            patch("pydantic_evals.Dataset", return_value=mock_dataset),
            patch("areyouok_telegram.jobs.evaluations.ENV", "production"),
        ):
            await job.run_job()

        mock_dataset.evaluate.assert_called_once()
        call_args = mock_dataset.evaluate.call_args
        assert call_args[1]["progress"] is False  # production environment

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_run_job_with_generations_both_reasoning_and_personality(self):
        """Test run_job with generations that have both reasoning and personality."""
        job = EvaluationsJob("chat123", "session456")

        mock_gen1 = MagicMock(spec=LLMGenerations)
        mock_gen1.agent = "areyouok_chat_agent"
        mock_gen1.generation_id = "gen1"
        mock_gen1.run_output = MagicMock()
        mock_gen1.run_deps = MagicMock()
        mock_gen1.run_output.get.side_effect = lambda key: "test reasoning" if key == "reasoning" else None
        mock_gen1.run_deps.get.side_effect = lambda key: "anchoring" if key == "personality" else None

        mock_dataset = MagicMock(spec=pydantic_evals.Dataset)
        mock_dataset.evaluate = AsyncMock()

        with (
            patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_session", return_value=[mock_gen1]),
            patch("pydantic_evals.Dataset", return_value=mock_dataset),
        ):
            await job.run_job()

        mock_dataset.evaluate.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_run_job_filters_non_evaluated_agents(self):
        """Test run_job filters out agents not in evaluated_agents list."""
        job = EvaluationsJob("chat123", "session456")

        mock_gen1 = MagicMock(spec=LLMGenerations)
        mock_gen1.agent = "some_other_agent"  # Not in evaluated_agents
        mock_gen1.generation_id = "gen1"

        mock_gen2 = MagicMock(spec=LLMGenerations)
        mock_gen2.agent = "areyouok_chat_agent"  # In evaluated_agents
        mock_gen2.generation_id = "gen2"
        mock_gen2.run_output = MagicMock()
        mock_gen2.run_deps = MagicMock()
        mock_gen2.run_output.get.side_effect = lambda key: "test" if key == "reasoning" else None
        mock_gen2.run_deps.get.side_effect = lambda _: None

        mock_dataset = MagicMock(spec=pydantic_evals.Dataset)
        mock_dataset.evaluate = AsyncMock()

        with (
            patch(
                "areyouok_telegram.jobs.evaluations.LLMGenerations.get_by_session", return_value=[mock_gen1, mock_gen2]
            ),
            patch("pydantic_evals.Dataset", return_value=mock_dataset),
        ):
            await job.run_job()

        # Should only evaluate gen2, not gen1
        mock_dataset.evaluate.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_db_session")
    async def test_run_job_creates_cases_with_correct_metadata(self):
        """Test run_job creates evaluation cases with correct metadata."""
        job = EvaluationsJob("chat123", "session456")

        mock_gen1 = MagicMock(spec=LLMGenerations)
        mock_gen1.agent = "areyouok_chat_agent"
        mock_gen1.generation_id = "gen1"
        mock_gen1.run_output = MagicMock()
        mock_gen1.run_deps = MagicMock()
        mock_gen1.run_output.get.side_effect = lambda _: None
        mock_gen1.run_deps.get.side_effect = lambda _: None

        mock_case = MagicMock(spec=pydantic_evals.Case)
        mock_dataset = MagicMock(spec=pydantic_evals.Dataset)
        mock_dataset.evaluate = AsyncMock()

        with (
            patch("areyouok_telegram.jobs.evaluations.LLMGeneration.get_by_session", return_value=[mock_gen1]),
            patch("pydantic_evals.Case", return_value=mock_case) as mock_case_constructor,
            patch("pydantic_evals.Dataset", return_value=mock_dataset),
        ):
            await job.run_job()

        # Verify Case was created with correct parameters
        mock_case_constructor.assert_called_once()
        call_args = mock_case_constructor.call_args[1]
        assert call_args["name"] == "areyouok_chat_agent_gen1"
        assert call_args["inputs"] == "gen1"
        assert call_args["metadata"]["session_id"] == "session456"
        assert call_args["metadata"]["chat_id"] == "chat123"
        assert call_args["evaluators"] == []  # No reasoning or personality, so no evaluators
