import pydantic
import pydantic_ai
import pydantic_evals

from areyouok_telegram.llms.models import Gemini25Flash
from areyouok_telegram.llms.utils import run_agent_with_tracking


class MotivatingEvaluationResponse(pydantic.BaseModel):
    cultivating_change_talk: float = pydantic.Field(
        description="MITI rating for cultivating change talk (1.0-5.0)",
        ge=1.0,
        le=5.0,
    )
    softening_sustain_talk: float = pydantic.Field(
        description="MITI rating for softening sustain talk (1.0-5.0)",
        ge=1.0,
        le=5.0,
    )
    partnership: float = pydantic.Field(
        description="MITI rating for partnership (1.0-5.0)",
        ge=1.0,
        le=5.0,
    )
    empathy: float = pydantic.Field(
        description="MITI rating for empathy (1.0-5.0)",
        ge=1.0,
        le=5.0,
    )
    reasoning: str = pydantic.Field(
        description=(
            "A brief reasoning, no more than 500 characters, explaining the MITI ratings. "
            "Do not include the original message or response, whether in part or full. "
        ),
    )

    @property
    def overall_score(self) -> float:
        """Calculate average MITI score for overall assessment."""
        return (self.cultivating_change_talk + self.softening_sustain_talk + self.partnership + self.empathy) / 4.0


agent_model = Gemini25Flash(
    model_settings=pydantic_ai.models.google.GoogleModelSettings(
        temperature=0.0,
        google_thinking_config={"thinking_budget": 0},
    )
)

motivating_eval_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=MotivatingEvaluationResponse,
    name="motivating_evaluator",
    end_strategy="exhaustive",
    retries=3,
)


@motivating_eval_agent.instructions
def motivating_eval_instructions(ctx: pydantic_ai.RunContext) -> str:  # noqa: ARG001
    return """
You will be presented with a multi-turn conversation between a user and an AI emotional companion.

Your task is to evaluate the AI assistant's most recent response using the MITI 4.2.1 (Motivational Interviewing
Treatment Integrity) framework. Rate each of the four global dimensions on a scale from 1 to 5:

CULTIVATING CHANGE TALK (1-5):
5 - Consistently and skillfully elicits change talk through open-ended questions, reflections, and statements that \
invite the user to voice their own motivations for positive change.
4 - Generally effective at eliciting change talk with good use of MI techniques to draw out user's own reasons for \
change.
3 - Some evidence of attempting to cultivate change talk but inconsistent or less skillful execution.
2 - Limited attempts to elicit change talk, may miss opportunities or use less effective approaches.
1 - No evidence of cultivating change talk, may even discourage or ignore user's motivations for change.

SOFTENING SUSTAIN TALK (1-5):
5 - Expertly handles resistance and sustain talk by rolling with resistance, exploring ambivalence, and helping user
work through barriers without arguing or confronting.
4 - Generally handles sustain talk well, avoids argumentation, and helps user explore their concerns.
3 - Some ability to soften sustain talk but may occasionally get drawn into arguments or miss opportunities.
2 - Limited skill in handling sustain talk, may be somewhat confrontational or miss resistance cues.
1 - Poor handling of sustain talk, argumentative, confrontational, or dismissive of user concerns.

PARTNERSHIP (1-5):
5 - Consistently demonstrates collaborative approach, shared decision-making, and treats user as equal partner in
the conversation with genuine respect for autonomy.
4 - Generally collaborative with good attention to user autonomy and shared responsibility.
3 - Some evidence of partnership but may be inconsistent or occasionally directive.
2 - Limited partnership, tends to be more directive or expert-focused rather than collaborative.
1 - Poor partnership, authoritarian, dismissive, or fails to respect user autonomy.

EMPATHY (1-5):
5 - Demonstrates deep understanding of user's perspective, reflects both explicit and implicit emotions accurately,
and shows genuine care and connection.
4 - Generally empathic with good understanding of user's experience and appropriate emotional responses.
3 - Some evidence of empathy but may be inconsistent or miss emotional undertones.
2 - Limited empathy, may be somewhat disconnected from user's emotional experience.
1 - Poor empathy, fails to understand or connect with user's perspective, may be dismissive or insensitive.

Rate each dimension based on the AI's most recent response while considering the conversation context.
    """


async def run_motivating_evaluation(
    *,
    chat,
    session,
    message_history: list,
) -> dict:
    """
    Run motivating evaluation for a conversation message history.

    Args:
        chat: Chat object for tracking
        session: Session object for tracking
        message_history: List of messages in the conversation

    Returns:
        Dictionary with motivating evaluation results
    """
    eval_result = await run_agent_with_tracking(
        agent=motivating_eval_agent,
        chat=chat,
        session=session,
        run_kwargs={
            "message_history": message_history,
        },
    )

    return {
        "MITITest": eval_result.output.overall_score >= 3.5,
        "MITI": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.overall_score,
            reason=eval_result.output.reasoning,
        ),
        "MITIChangeTalk": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.cultivating_change_talk,
            reason="MITI rating for cultivating change talk",
        ),
        "MITISustainTalk": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.softening_sustain_talk,
            reason="MITI rating for softening sustain talk",
        ),
        "MITIPartnership": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.partnership,
            reason="MITI rating for partnership",
        ),
        "MITIEmpathy": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.empathy,
            reason="MITI rating for empathy",
        ),
    }
