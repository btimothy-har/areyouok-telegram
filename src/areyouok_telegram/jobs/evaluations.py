from dataclasses import dataclass

import logfire
import pydantic_evals
from cachetools import TTLCache

from areyouok_telegram.config import ENV
from areyouok_telegram.data.models import Chat, LLMGeneration, Session
from areyouok_telegram.jobs.base import BaseJob
from areyouok_telegram.llms.evaluators import (
    run_empathy_evaluation,
    run_motivating_evaluation,
    run_personality_alignment_evaluation,
    run_reasoning_alignment_evaluation,
    run_sycophancy_evaluation,
)

GEN_CACHE = TTLCache(maxsize=1000, ttl=300)


async def get_generation_by_id_cached(gen_id: int) -> LLMGeneration:
    if gen_id in GEN_CACHE:
        return GEN_CACHE[gen_id]

    generation = await LLMGeneration.get_by_id(generation_id=gen_id)
    if not generation:
        raise ValueError(f"Generation with ID {gen_id} not found.")  # noqa: TRY003

    GEN_CACHE[gen_id] = generation
    return generation


@dataclass
class ReasoningAlignmentEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Get chat and session from metadata
        chat = await Chat.get_by_id(chat_id=ctx.metadata["chat_id"])
        session = await Session.get_by_id(session_id=ctx.metadata["session_id"])

        # Prepare clean output without reasoning
        run_output = generation.output.copy()
        run_output.pop("reasoning", None)

        # Use the new interface
        return await run_reasoning_alignment_evaluation(
            chat=chat,
            session=session,
            output=run_output,
            reasoning=generation.output.get("reasoning"),
        )


@dataclass
class PersonalityAlignmentEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Get chat and session from metadata
        chat = await Chat.get_by_id(chat_id=ctx.metadata["chat_id"])
        session = await Session.get_by_id(session_id=ctx.metadata["session_id"])

        deps = generation.deps or {}

        # Use the new interface
        return await run_personality_alignment_evaluation(
            chat=chat,
            session=session,
            output=generation.output,
            personality=deps.get("personality"),
        )


@dataclass
class SycophancyEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Get chat and session from metadata
        chat = await Chat.get_by_id(chat_id=ctx.metadata["chat_id"])
        session = await Session.get_by_id(session_id=ctx.metadata["session_id"])

        # Use the new interface
        return await run_sycophancy_evaluation(
            chat=chat,
            session=session,
            message_history=generation.messages,
        )


@dataclass
class EmpathyEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Get chat and session from metadata
        chat = await Chat.get_by_id(chat_id=ctx.metadata["chat_id"])
        session = await Session.get_by_id(session_id=ctx.metadata["session_id"])

        # Use the new interface
        return await run_empathy_evaluation(
            chat=chat,
            session=session,
            message_history=generation.messages,
        )


@dataclass
class MotivatingEvaluator(pydantic_evals.evaluators.Evaluator):
    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        generation = await get_generation_by_id_cached(ctx.inputs)

        # Get chat and session from metadata
        chat = await Chat.get_by_id(chat_id=ctx.metadata["chat_id"])
        session = await Session.get_by_id(session_id=ctx.metadata["session_id"])

        # Use the new interface
        return await run_motivating_evaluation(
            chat=chat,
            session=session,
            message_history=generation.messages,
        )


async def eval_production_response(gen_id: int) -> dict:
    generation = await get_generation_by_id_cached(gen_id)

    return {
        "model": generation.model,
        "response_type": generation.response_type,
        "reasoning": generation.output.get("reasoning") if isinstance(generation.output, dict) else None,
        "personality": (
            generation.deps.get("personality") if generation.deps and isinstance(generation.deps, dict) else None
        ),
    }


class EvaluationsJob(BaseJob):
    def __init__(self, chat_id: int, session_id: int):
        """
        Run evaluations for a chat session.

        Args:
            chat_id: Internal chat ID
            session_id: Internal session ID
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
        # Fetch Chat and Session objects for tracking
        chat = await Chat.get_by_id(chat_id=self.chat_id)
        if not chat:
            logfire.warning(f"Chat {self.chat_id} not found. Skipping evaluations.")
            return

        session = await Session.get_by_id(session_id=self.session_id)
        if not session:
            logfire.warning(f"Session {self.session_id} not found. Skipping evaluations.")
            return

        generations = await LLMGeneration.get_by_session(session_id=self.session_id)
        if not generations:
            logfire.warning(f"No generations found for session {self.session_id}. Skipping evaluations.")
            return

        dataset_cases = []
        for gen in generations:
            if gen.agent not in self.evaluated_agents:
                continue

            case_evaluators = []

            # Check if output is a dict before accessing "reasoning"
            if isinstance(gen.output, dict) and gen.output.get("reasoning"):
                case_evaluators.append(ReasoningAlignmentEvaluator())

            # Check if deps is a dict before accessing "personality"
            if isinstance(gen.deps, dict) and gen.deps.get("personality"):
                case_evaluators.append(PersonalityAlignmentEvaluator())

            dataset_cases.append(
                pydantic_evals.Case(
                    name=f"{gen.agent}_{gen.id}",
                    inputs=gen.id,
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
            name=f"session_evaluation:{self.session_id}",
            max_concurrency=1,
            progress=True if ENV == "development" else False,
        )

        # Purge generation data after evaluations complete
        logfire.info(
            "Purging generation data after evaluation completion.",
            session_id=self.session_id,
            chat_id=self.chat_id,
        )

        for gen in generations:
            await self._purge_generation(gen)

        logfire.info(
            "Purged generation records.",
            session_id=self.session_id,
            chat_id=self.chat_id,
            count=len(generations),
        )

    async def _purge_generation(self, gen: LLMGeneration) -> None:
        await gen.delete()
        # Clear cache entry for this specific generation
        GEN_CACHE.pop(gen.id, None)
