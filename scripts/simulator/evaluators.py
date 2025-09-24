from dataclasses import dataclass

import pydantic_evals

from areyouok_telegram.llms.evaluators import run_personality_alignment_evaluation
from areyouok_telegram.llms.evaluators import run_reasoning_alignment_evaluation
from areyouok_telegram.llms.evaluators import run_sycophancy_evaluation


@dataclass
class ConversationReasoningAlignmentEvaluator(pydantic_evals.evaluators.Evaluator):
    """Evaluates reasoning alignment for a specific conversation turn."""

    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        turn_data = ctx.output  # This comes from get_turn_data()

        # Create clean output without reasoning
        bot_output = {
            "message_text": turn_data["bot_message"],
            "timestamp": turn_data["timestamp"].isoformat(),
        }

        # Use the new evaluation interface
        return await run_reasoning_alignment_evaluation(
            output=bot_output,
            reasoning=turn_data["bot_reasoning"],
        )


@dataclass
class ConversationPersonalityAlignmentEvaluator(pydantic_evals.evaluators.Evaluator):
    """Evaluates personality alignment for a specific conversation turn."""

    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        turn_data = ctx.output

        bot_output = {
            "message_text": turn_data["bot_message"],
            "timestamp": turn_data["timestamp"].isoformat(),
        }

        # Use the new evaluation interface
        return await run_personality_alignment_evaluation(
            output=bot_output,
            personality=turn_data["personality"],
        )


@dataclass
class ConversationSycophancyEvaluator(pydantic_evals.evaluators.Evaluator):
    """Evaluates sycophancy for the conversation up to a specific turn."""

    async def evaluate(self, ctx: pydantic_evals.evaluators.EvaluatorContext):
        turn_data = ctx.output

        conversation_history = turn_data["conversation_history"]
        if len(conversation_history) < 2:  # Need at least one exchange
            return {"SycophancyTest": None, "Sycophancy": None}

        # Convert ConversationMessages to model message format for sycophancy evaluation
        model_messages = [
            {
                "role": msg.role,
                "content": msg.text,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in conversation_history
        ]

        # Use the new evaluation interface
        return await run_sycophancy_evaluation(
            message_history=model_messages,
        )
