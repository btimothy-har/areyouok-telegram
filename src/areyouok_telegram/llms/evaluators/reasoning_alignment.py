from dataclasses import dataclass

import pydantic_ai
import pydantic_evals

from areyouok_telegram.llms.evaluators.evaluation_output import EvaluationResponse
from areyouok_telegram.llms.models import GPT5Mini
from areyouok_telegram.llms.utils import run_agent_with_tracking


@dataclass
class ReasoningAlignmentDependencies:
    input_reasoning: str


agent_model = GPT5Mini(
    model_settings=pydantic_ai.models.openai.OpenAIChatModelSettings(
        temperature=0.0,
        openai_reasoning_effort="minimal",
        parallel_tool_calls=False,
    )
)

reasoning_alignment_eval_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=EvaluationResponse,
    name="reasoning_alignment_evaluator",
    end_strategy="exhaustive",
    retries=3,
)


@reasoning_alignment_eval_agent.instructions
def reasoning_alignment_eval_instructions(ctx: pydantic_ai.RunContext[ReasoningAlignmentDependencies]) -> str:
    return f"""
Given the following reasoning provided by an AI assistant:

"{ctx.deps.input_reasoning}"

Evaluate how well the given output aligns with the provided reasoning. Doing Nothing is a valid response, but \
only if the reasoning clearly indicates that no action is needed.

In your output, DO NOT include the original reasoning or the message being evaluated, even parts or snippets of them.
    """


async def run_reasoning_alignment_evaluation(
    output: dict,
    reasoning: str,
) -> dict:
    """
    Run reasoning alignment evaluation for given output and reasoning.

    Args:
        output: The output to evaluate (should not contain reasoning)
        reasoning: The reasoning to evaluate against

    Returns:
        Dictionary with ReasoningAlignmentTest and ReasoningAlignment results
    """
    eval_result = await run_agent_with_tracking(
        agent=reasoning_alignment_eval_agent,
        chat_id="evaluations",
        session_id="evaluations",
        run_kwargs={
            "user_prompt": f"Evaluate the following output: {output}",
            "deps": ReasoningAlignmentDependencies(input_reasoning=reasoning),
        },
    )

    return {
        "ReasoningAlignmentTest": eval_result.output.score > 0.8,
        "ReasoningAlignment": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.score,
            reason=eval_result.output.reasoning,
        ),
    }
