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

from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.chat.constants import MESSAGE_FOR_USER_PROMPT
from areyouok_telegram.llms.chat.constants import ONBOARDING_FIELDS
from areyouok_telegram.llms.chat.constants import ONBOARDING_OBJECTIVES
from areyouok_telegram.llms.chat.constants import RESPONSE_PROMPT
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.utils import check_restricted_responses
from areyouok_telegram.llms.chat.utils import check_special_instructions
from areyouok_telegram.llms.chat.utils import validate_response_data
from areyouok_telegram.llms.exceptions import CompleteOnboardingError
from areyouok_telegram.llms.exceptions import OnboardingFieldUpdateError
from areyouok_telegram.llms.models import ONBOARDING_SONNET_4
from areyouok_telegram.llms.utils import run_agent_with_tracking
from areyouok_telegram.llms.validators.country_timezone import CountryTimezone
from areyouok_telegram.llms.validators.country_timezone import country_timezone_agent

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
    model=ONBOARDING_SONNET_4.model,
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

    onboarding_fields = ["preferred_name", "country", "communication_style"]

    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

    if user_metadata:
        if user_metadata.preferred_name:
            onboarding_fields.remove("preferred_name")

        if user_metadata.country and not user_metadata.timezone:
            onboarding_fields.remove("country")
            onboarding_fields.insert(0, "timezone")

        if user_metadata.communication_style:
            onboarding_fields.remove("communication_style")

    prompt = BaseChatPromptTemplate(
        response=RESPONSE_PROMPT.format(response_restrictions=restrict_response_text),
        message=MESSAGE_FOR_USER_PROMPT.format(important_message_for_user=ctx.deps.instruction)
        if ctx.deps.instruction
        else None,
        objectives=ONBOARDING_OBJECTIVES.format(onboarding_fields=", ".join(onboarding_fields)),
    )

    return prompt.as_prompt_string()


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
    value_to_save: Any,
) -> str:
    """Save user response to metadata."""

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field=field,
                value=value_to_save,
            )

        except Exception as e:
            raise OnboardingFieldUpdateError("timezone", str(e)) from e

    if field == "country":
        if value_to_save == "rather_not_say":
            tz_value = "rather_not_say"
            has_multiple = False
        else:
            tz = await run_agent_with_tracking(
                country_timezone_agent,
                chat_id=ctx.deps.tg_chat_id,
                session_id=ctx.deps.tg_session_id,
                run_kwargs={
                    "user_prompt": f"Identify the timezone for the ISO-3 Country: {value_to_save}.",
                },
            )
            tz_data: CountryTimezone = tz.output
            tz_value = tz_data.timezone
            has_multiple = tz_data.has_multiple

        if has_multiple:
            return f"""
{field} updated successfully. The timezone {tz_data.timezone} seems to be the best fit option, but there are \
multiple timezones available. Confirm with the user what their timezone should be.
"""

        else:
            async with async_database() as db_conn:
                try:
                    await UserMetadata.update_metadata(
                        db_conn,
                        user_id=ctx.deps.tg_chat_id,
                        field="timezone",
                        value=tz_value,
                    )

                except Exception as e:
                    raise OnboardingFieldUpdateError("timezone", str(e)) from e

    return f"{field} updated successfully."


@onboarding_agent.tool
async def complete_onboarding(ctx: RunContext[OnboardingAgentDependencies]) -> str:
    """Mark the user's onboarding as complete."""
    async with async_database() as db_conn:
        try:
            onboarding = await GuidedSessions.get_by_guided_session_key(
                db_conn, guided_session_key=ctx.deps.onboarding_session_key
            )
        except Exception as e:
            raise CompleteOnboardingError(e) from e

        if not onboarding.is_active:
            raise CompleteOnboardingError(f"Onboarding session is currently {onboarding.state}.")  # noqa: TRY003

        await onboarding.complete(db_conn, timestamp=datetime.now(UTC))

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
