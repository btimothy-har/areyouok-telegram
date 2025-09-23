from dataclasses import dataclass

import pydantic_ai

from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.evaluators.evaluation_output import EvaluationResponse
from areyouok_telegram.llms.models import GPT5Mini


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
