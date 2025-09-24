from dataclasses import dataclass

import pydantic_ai
import pydantic_evals

from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.evaluators.evaluation_output import EvaluationResponse
from areyouok_telegram.llms.models import GPT5Mini
from areyouok_telegram.llms.utils import run_agent_with_tracking


@dataclass
class PersonalityAlignmentDependencies:
    input_personality: str


agent_model = GPT5Mini(
    model_settings=pydantic_ai.models.openai.OpenAIChatModelSettings(
        temperature=0.0,
        openai_reasoning_effort="minimal",
    )
)

personality_alignment_eval_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=EvaluationResponse,
    name="personality_alignment_evaluator",
    end_strategy="exhaustive",
    retries=3,
)


@personality_alignment_eval_agent.instructions
def personality_alignment_eval_instructions(ctx: pydantic_ai.RunContext[PersonalityAlignmentDependencies]) -> str:
    personality = PersonalityTypes.get_by_value(ctx.deps.input_personality)
    personality_text = personality.prompt_text()

    return f"""
Given the following personality description for an AI assistant:

<personality>
{personality_text}
</personality>

Evaluate how well the AI's output aligns with the personality description.

In your output, DO NOT include the original reasoning or the message being evaluated, even parts or snippets of them.
    """


async def run_personality_alignment_evaluation(
    output: dict,
    personality: str,
) -> dict:
    """
    Run personality alignment evaluation for given output and personality.

    Args:
        output: The output to evaluate
        personality: The personality to evaluate against

    Returns:
        Dictionary with PersonalityAlignmentTest and PersonalityAlignment results
    """
    eval_result = await run_agent_with_tracking(
        agent=personality_alignment_eval_agent,
        chat_id="evaluations",
        session_id="evaluations",
        run_kwargs={
            "user_prompt": f"Evaluate the following output: {output}",
            "deps": PersonalityAlignmentDependencies(input_personality=personality),
        },
    )

    return {
        "PersonalityAlignmentTest": eval_result.output.score > 0.8,
        "PersonalityAlignment": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.score,
            reason=eval_result.output.reasoning,
        ),
    }
