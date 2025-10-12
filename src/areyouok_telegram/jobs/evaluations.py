from dataclasses import dataclass

import logfire
import pydantic_evals
from cachetools import TTLCache

from areyouok_telegram.config import ENV
from areyouok_telegram.data import LLMGenerations
from areyouok_telegram.data import async_database
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.llms.evaluators import run_empathy_evaluation
from areyouok_telegram.llms.evaluators import run_motivating_evaluation
from areyouok_telegram.llms.evaluators import run_personality_alignment_evaluation
from areyouok_telegram.llms.evaluators import run_reasoning_alignment_evaluation
from areyouok_telegram.llms.evaluators import run_sycophancy_evaluation
from areyouok_telegram.utils.retry import db_retry

GEN_CACHE = TTLCache(maxsize=1000, ttl=300)


@db_retry()
async def get_generation_by_id_cached(gen_id: str) -> LLMGenerations:
    if gen_id in GEN_CACHE:
        return GEN_CACHE[gen_id]

    async with async_database() as db_conn:
        generation = await LLMGenerations.get_by_generation_id(db_conn, generation_id=gen_id)
        if not generation:
            raise ValueError(f"Generation with ID {gen_id} not found.")  # noqa: TRY003

        GEN_CACHE[gen_id] = generation
        return generation


@dataclass
class ReasoningAlignmentEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Prepare clean output without reasoning
        run_output = generation.run_output.copy()
        run_output.pop("reasoning", None)

        # Use the new interface
        return await run_reasoning_alignment_evaluation(
            output=run_output,
            reasoning=generation.run_output.get("reasoning"),
        )


@dataclass
class PersonalityAlignmentEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        deps = generation.run_deps or {}

        # Use the new interface
        return await run_personality_alignment_evaluation(
            output=generation.run_output,
            personality=deps.get("personality"),
        )


@dataclass
class SycophancyEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Use the new interface
        return await run_sycophancy_evaluation(
            message_history=generation.run_messages,
        )


@dataclass
class EmpathyEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Use the new interface
        return await run_empathy_evaluation(
            message_history=generation.run_messages,
        )


@dataclass
class MotivatingEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Use the new interface
        return await run_motivating_evaluation(
            message_history=generation.run_messages,
        )


async def eval_production_response(gen_id: str) -> dict:
    generation = await get_generation_by_id_cached(gen_id)

    return {
        "model": generation.model,
        "response_type": generation.response_type,
        "reasoning": generation.run_output.get("reasoning"),
        "personality": generation.run_deps.get("personality"),
    }


class EvaluationsJob(BaseJob):
    def __init__(self, chat_id: str, session_id: str):
        """
        Run evaluations for a chat session.

        Args:
            session_id: The session ID to process
        """
        super().__init__()

        self.chat_id = chat_id
        self.session_id = session_id

    @property
    def name(self) -> str:
        return f"evaluations:{self.session_id}"

    @property
    def evaluated_agents(self) -> list[str]:
        return ["areyouok_chat_agent", "areyouok_onboarding_agent"]

    async def run_job(self) -> None:
        @db_retry()
        async def _get_generation_by_session() -> list[LLMGenerations]:
            async with async_database() as db_conn:
                return await LLMGenerations.get_by_session(
                    db_conn,
                    session_id=self.session_id,
                )

        generations = await _get_generation_by_session()
        if not generations:
            logfire.warning(f"No generations found for session {self.session_id}. Skipping evaluations.")
            return

        dataset_cases = []
        for gen in generations:
            if gen.agent not in self.evaluated_agents:
                continue

            case_evaluators = []

            # Check if run_output is a dict before accessing "reasoning"
            if isinstance(gen.run_output, dict) and gen.run_output.get("reasoning"):
                case_evaluators.append(ReasoningAlignmentEvaluator())

            # Check if run_deps is a dict before accessing "personality"
            if isinstance(gen.run_deps, dict) and gen.run_deps.get("personality"):
                case_evaluators.append(PersonalityAlignmentEvaluator())

            dataset_cases.append(
                pydantic_evals.Case(
                    name=f"{gen.agent}_{gen.generation_id}",
                    inputs=gen.generation_id,
                    metadata={
                        "session_id": self.session_id,
                        "chat_id": self.chat_id,
                    },
                    evaluators=case_evaluators,
                )
            )

        session_dataset = pydantic_evals.Dataset(
            cases=dataset_cases,
            evaluators=[
                SycophancyEvaluator(),
                EmpathyEvaluator(),
                MotivatingEvaluator(),
            ],
        )

        await session_dataset.evaluate(
            eval_production_response,
            name=self.session_id,
            max_concurrency=1,
            progress=True if ENV == "development" else False,
        )
