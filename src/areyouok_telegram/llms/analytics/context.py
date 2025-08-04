from datetime import UTC
from datetime import datetime

import dspy

from areyouok_telegram.data import MessageTypes
from areyouok_telegram.llms.utils import telegram_message_to_dict

LIFE_SITUATION_DESC = """
The person's immediate life circumstances and ongoing challenges that form the backdrop of their need for support. \
    This encompasses their current stressors, whether from work, relationships, health, finances, or major life \
    transitions.

Document recent triggering events or changes that prompted them to seek connection, along with their overall emotional \
    climate - are they feeling overwhelmed, stuck, hopeful, or exhausted? Understanding their day-to-day reality helps \
    ensure support remains grounded in their actual experience rather than abstract concepts.
"""

CONNECTION_DESC = """
The unique relational dynamic that has evolved between the person and their support system. This captures their \
    preferred mode of engagement - some people need to verbally process without interruption, others seek \
    collaborative problem-solving, while some simply need witnessing and validation. Document which conversational \
    approaches land well with them and which fall flat. Note moments of genuine connection, shared understanding, or \
    even humor that define the relationship's character. This ensures continuity in tone and approach that honors \
    the established relationship.
"""

PERSONAL_CONTEXT_DESC = """
The person's deeper identity markers, life philosophy, and historical experiences that shape their worldview. \
    This includes their stated values, cultural or spiritual frameworks, and the life experiences they reference \
    when making sense of current challenges. Capture their self-identified strengths and the internal or external \
    resources they draw upon. Understanding these foundational elements ensures support aligns with who they are \
    rather than imposing external frameworks that may not resonate.
"""

CONVERSATION_DESC = """
The narrative thread and momentum of ongoing dialogue. This tracks where the session concluded, which \
    topics remain open for exploration, and questions that await answers. Document any insights they've articulated \
    or commitments they've made to themselves. Note their conversational preferences - do they need time to sit \
    with ideas, or do they prefer rapid exploration? This continuity should prevent repetitive cycles and honor the \
    progressive nature of their journey.
"""

PRACTICAL_MATTERS_DESC = """
The concrete, actionable elements of their situation requiring attention or decision-making. This includes \
    specific dilemmas they're facing, time-sensitive decisions, and real-world constraints affecting their options. \
    Document strategies or resources previously discussed and their response to these suggestions. Keep track of \
    external factors like deadlines, appointments, or obligations that create structure around their support needs.
"""

FEEDBACK_DESC = """
The person's explicit and implicit communication about the support relationship itself, including the subtle \
    patterns that reveal their needs. This captures their direct feedback about what helps or hinders, but also \
    the unspoken elements - their processing style, their rhythm of engagement, and the specific qualities that \
    help them feel truly heard versus superficially acknowledged. Document patterns in their help-seeking, \
    their comfort with different depths of exploration, and preserve their exact language for breakthrough moments. \
    This meta-awareness ensures the support relationship remains responsive and authentic to their evolving needs.
"""

CONTEXT_TEMPLATE = """
## Life Situation
{life_situation}

## Connection
{connection}

## Personal Context
{personal_context}

## Conversation
{conversation}

## Practical Matters
{practical_matters}

## Feedback
{feedback}

## Others
{others}
"""


class _SessionContextCompression(dspy.Signature):
    """
    Compress the context of the provided chat session, summarizing only the essential elements that are \
    necessary for an AI Agent to continue the conversation effectively.

    You are provided with 7 fields, each representing a different aspect of the session context. \
    Analyze the provided messages and extract the relevant information for each field.

    Where there is no relevant information, provide "No relevant information." as your response.

    Output your summary in plain text.
    """

    messages: list[str] = dspy.InputField(desc="Chronological messages in the session between the Agent and the user.")

    life_situation: str = dspy.OutputField(desc=LIFE_SITUATION_DESC)
    connection: str = dspy.OutputField(desc=CONNECTION_DESC)
    personal_context: str = dspy.OutputField(desc=PERSONAL_CONTEXT_DESC)
    conversation: str = dspy.OutputField(desc=CONVERSATION_DESC)
    practical_matters: str = dspy.OutputField(desc=PRACTICAL_MATTERS_DESC)
    feedback: str = dspy.OutputField(desc=FEEDBACK_DESC)
    others: str = dspy.OutputField(desc="Any other relevant information that does not fit into the above categories.")


class DynamicContextCompression(dspy.Module):
    def __init__(self):
        self.analysis = dspy.ChainOfThought(_SessionContextCompression)

    def forward(self, messages: list[MessageTypes]) -> dspy.Prediction:
        now = datetime.now(UTC)

        message_data = [telegram_message_to_dict(message, ts_reference=now) for message in messages]
        compression = self.analysis(messages=message_data)

        context = CONTEXT_TEMPLATE.format(
            life_situation=compression.life_situation,
            connection=compression.connection,
            personal_context=compression.personal_context,
            conversation=compression.conversation,
            practical_matters=compression.practical_matters,
            feedback=compression.feedback,
            others=compression.others,
        )

        result = dspy.Prediction(
            context=context,
        )

        # Preserve LLM usage data from the compression prediction
        if hasattr(compression, "get_lm_usage"):
            usage = compression.get_lm_usage()
            if usage:
                result.set_lm_usage(usage)

        return result
