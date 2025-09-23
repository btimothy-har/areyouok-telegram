from dataclasses import dataclass

import pydantic_ai

from areyouok_telegram.llms.evaluators.evaluation_output import EvaluationResponse
from areyouok_telegram.llms.models import GPT5Mini


@dataclass
class ReasoningAlignmentDependencies:
    input_reasoning: str


agent_model = GPT5Mini(
    model_settings=pydantic_ai.models.openai.OpenAIChatModelSettings(
        temperature=0.0,
        openai_reasoning_effort="minimal",
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
