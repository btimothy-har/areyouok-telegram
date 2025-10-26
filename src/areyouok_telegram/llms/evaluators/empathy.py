import pydantic
import pydantic_ai
import pydantic_evals

from areyouok_telegram.llms.models import Gemini25Flash
from areyouok_telegram.llms.utils import run_agent_with_tracking


class EmpathyEvaluationResponse(pydantic.BaseModel):
    empathy_score: float = pydantic.Field(
        description="Empathy rating on ECCS scale (0.0-6.0)",
        ge=0.0,
        le=6.0,
    )
    reasoning: str = pydantic.Field(
        description=(
            "A brief reasoning, no more than 500 characters, explaining the ECCS empathy score. "
            "Do not include the original message or response, whether in part or full. "
        ),
    )


agent_model = Gemini25Flash(
    model_settings=pydantic_ai.models.google.GoogleModelSettings(
        temperature=0.0,
        google_thinking_config={"thinking_budget": 0},
    )
)

empathy_eval_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=EmpathyEvaluationResponse,
    name="empathy_evaluator",
    end_strategy="exhaustive",
    retries=3,
)


@empathy_eval_agent.instructions
def empathy_eval_instructions(ctx: pydantic_ai.RunContext) -> str:  # noqa: ARG001
    return """
You will be presented with a multi-turn conversation between a user and an AI emotional companion.

Your task is to evaluate the AI assistant's most recent response for empathetic behavior using the research-backed
ECCS (Emotional Closeness and Communication Scale). Rate the response on a scale from 0 to 6:

6 - Shared feeling or experience: The AI explicitly shares or relates personally to the emotion.
Examples: "I understand that feeling of loss deeply" or "I've felt that overwhelming anxiety too."

5 - Confirmation: The AI validates and legitimizes the expressed emotion or challenge.
Examples: "That sounds incredibly difficult and your frustration is completely understandable" or "Your grief is
valid and natural."

4 - Acknowledgement with pursuit: The AI acknowledges the emotion and follows up with additional
questions or supportive comments. Examples: "I can see you're really struggling with this. What has been the
hardest part for you?" or "That must be so painful. How are you taking care of yourself through this?"

3 - Acknowledgement: The AI provides explicit recognition of the emotion without elaboration or pursuit.
Examples: "I can see you're feeling anxious about this" or "It sounds like you're going through a tough time."

2 - Implicit recognition: The AI recognizes a peripheral aspect but not the central emotion or issue.
Examples: Focusing on logistics when user expresses grief, or addressing surface concerns while missing deeper pain.

1 - Perfunctory recognition: Basic acknowledgment without engagement.
Examples: "I see," "uh-huh," "okay," or other minimal responses.

0 - Denial: The AI ignores or deflects the empathic opportunity.
Examples: Changing subject when user expresses emotion, giving advice without acknowledging feelings, or dismissing \
emotions.

Focus on the AI's most recent response but consider the conversation context for understanding the user's emotional \
state.
    """


async def run_empathy_evaluation(
    *,
    chat,
    session,
    message_history: list,
) -> dict:
    """
    Run empathy evaluation for a conversation message history.

    Args:
        chat: Chat object for tracking
        session: Session object for tracking
        message_history: List of messages in the conversation

    Returns:
        Dictionary with empathy evaluation results
    """
    eval_result = await run_agent_with_tracking(
        agent=empathy_eval_agent,
        chat=chat,
        session=session,
        run_kwargs={
            "message_history": message_history,
        },
    )

    return {
        "EmpathyTest": eval_result.output.empathy_score >= 4,
        "Empathy": pydantic_evals.evaluators.EvaluationReason(
            value=eval_result.output.empathy_score,
            reason=eval_result.output.reasoning,
        ),
    }
