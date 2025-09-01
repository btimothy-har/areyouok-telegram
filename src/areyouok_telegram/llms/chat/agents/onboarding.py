"""Onboarding agent for new user initialization."""

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import Literal

import pydantic_ai
from pydantic_ai import RunContext
from telegram.ext import ContextTypes

from areyouok_telegram.data import OnboardingSession
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat.constants import ONBOARDING_AGENT_PROMPT
from areyouok_telegram.llms.chat.constants import ONBOARDING_FIELDS
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.utils import check_restricted_responses
from areyouok_telegram.llms.chat.utils import check_special_instructions
from areyouok_telegram.llms.chat.utils import validate_response_data
from areyouok_telegram.llms.exceptions import CompleteOnboardingError
from areyouok_telegram.llms.exceptions import OnboardingFieldUpdateError
from areyouok_telegram.llms.models import CHAT_SONNET_4

AgentResponse = TextResponse | ReactionResponse | DoNothingResponse


@dataclass
class OnboardingAgentDependencies:
    """Dependencies for the onboarding agent."""

    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    tg_session_id: str
    onboarding_session_key: str
    restricted_responses: set[Literal["text", "reaction", "switch_personality"]] = field(default_factory=set)
    instruction: str | None = None


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

    restrict_response_text = ""

    if "text" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_TEXT_RESPONSE
        restrict_response_text += "\n"

    onboarding_fields = ["preferred_name", "country", "timezone", "communication_style"]

    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

    if user_metadata:
        if user_metadata.preferred_name:
            onboarding_fields.remove("preferred_name")

        if user_metadata.country and user_metadata.timezone:
            onboarding_fields.remove("country")
            onboarding_fields.remove("timezone")

        if user_metadata.communication_style:
            onboarding_fields.append("communication_style")

    return ONBOARDING_AGENT_PROMPT.format(
        important_message_for_user=ctx.deps.instruction if ctx.deps.instruction else "None",
        response_restrictions=restrict_response_text or "",
        onboarding_fields=", ".join(onboarding_fields),
    )


@onboarding_agent.tool
def get_question_details(
    ctx: RunContext[OnboardingAgentDependencies],  # noqa: ARG001
    question_key: str,
) -> dict[str, Any]:
    """Get details for a specific onboarding question."""
    return ONBOARDING_FIELDS.get(question_key, {})


@onboarding_agent.tool
async def save_user_response(
    ctx: RunContext[OnboardingAgentDependencies],
    field: str,
    value: Any,
) -> str:
    """Save user response to metadata."""
    async with async_database() as db_conn:
        try:
            metadata = await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field=field,
                value=value,
            )

        except Exception as e:
            raise OnboardingFieldUpdateError(field) from e

    return f"{field} updated successfully. Saved value: {metadata.to_dict()}."


@onboarding_agent.tool
async def complete_onboarding(ctx: RunContext[OnboardingAgentDependencies]) -> str:
    """Mark the user's onboarding as complete."""
    async with async_database() as db_conn:
        try:
            onboarding = await OnboardingSession.get_by_session_key(
                db_conn, session_key=ctx.deps.onboarding_session_key
            )
        except Exception as e:
            raise CompleteOnboardingError(e) from e

        if not onboarding.is_active:
            raise CompleteOnboardingError(f"Onboarding session is currently {onboarding.state}.")  # noqa: TRY003

        await onboarding.end_onboarding(db_conn, timestamp=datetime.now(UTC))

    return "Onboarding completed successfully."


@onboarding_agent.output_validator
async def validate_agent_response(
    ctx: pydantic_ai.RunContext[OnboardingAgentDependencies], data: AgentResponse
) -> AgentResponse:
    check_restricted_responses(
        response=data,
        restricted=ctx.deps.restricted_responses,
    )

    await validate_response_data(
        response=data,
        chat_id=ctx.deps.tg_chat_id,
        bot_id=str(ctx.deps.tg_context.bot.id),
    )

    if ctx.deps.instruction:
        await check_special_instructions(
            response=data,
            chat_id=ctx.deps.tg_chat_id,
            session_id=ctx.deps.tg_session_id,
            instruction=ctx.deps.instruction,
        )

    return data
