"""Onboarding agent for new user initialization."""

from dataclasses import dataclass
from typing import Any

import pydantic_ai
from pydantic_ai import RunContext
from telegram.ext import ContextTypes

from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat.constants import ONBOARDING_AGENT_PROMPT
from areyouok_telegram.llms.chat.constants import ONBOARDING_FIELDS
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.exceptions import OnboardingFieldUpdateError
from areyouok_telegram.llms.models import CHAT_SONNET_4

AgentResponse = TextResponse | ReactionResponse | DoNothingResponse


@dataclass
class OnboardingAgentDependencies:
    """Dependencies for the onboarding agent."""

    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    tg_user_id: str
    session_key: str


onboarding_agent = pydantic_ai.Agent(
    model=CHAT_SONNET_4.model,
    output_type=AgentResponse,
    deps_type=OnboardingAgentDependencies,
    name="areyouok_onboarding_agent",
    end_strategy="exhaustive",
    retries=3,
)


@onboarding_agent.instructions
async def onboarding_instructions(ctx: RunContext[OnboardingAgentDependencies]) -> str:
    """Provide instructions for the onboarding agent."""

    onboarding_fields = []

    async with async_database() as db_conn:
        user_metadata = UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_user_id)

    if not user_metadata.preferred_name:
        onboarding_fields.append("preferred_name")

    if not user_metadata.country and not user_metadata.timezone:
        onboarding_fields.append("country")

    if user_metadata.country and not user_metadata.timezone:
        onboarding_fields.append("timezone")

    if not user_metadata.communication_style:
        onboarding_fields.append("communication_style")

    return ONBOARDING_AGENT_PROMPT.format(onboarding_fields=", ".join(onboarding_fields))


@onboarding_agent.tool
def get_question_details(question_key: str) -> dict[str, Any]:
    """Get details for a specific onboarding question."""
    return ONBOARDING_FIELDS.get(question_key, {})


@onboarding_agent.tool
async def save_user_response(
    ctx: RunContext[OnboardingAgentDependencies],
    field: str,
    value: Any,
) -> bool:
    """Save user response to metadata."""
    async with async_database() as db_conn:
        try:
            metadata = await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_user_id,
                field=field,
                value=value,
            )

        except Exception as e:
            raise OnboardingFieldUpdateError(field) from e

    return f"{field} updated successfully. Saved value: {metadata.to_dict()}."
