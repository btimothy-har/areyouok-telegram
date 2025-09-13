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
from areyouok_telegram.data import Notifications
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.agent_country_timezone import CountryTimezone
from areyouok_telegram.llms.agent_country_timezone import country_timezone_agent
from areyouok_telegram.llms.agent_settings import SettingsAgentDependencies
from areyouok_telegram.llms.agent_settings import SettingsUpdateResponse
from areyouok_telegram.llms.agent_settings import settings_agent
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
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import ClaudeSonnet4
from areyouok_telegram.llms.utils import log_metadata_update_context
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | DoNothingResponse


@dataclass
class OnboardingAgentDependencies:
    """Dependencies for the onboarding agent."""

    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    tg_session_id: str
    onboarding_session_key: str
    restricted_responses: set[Literal["text", "reaction", "switch_personality"]] = field(default_factory=set)
    notification: Notifications | None = None


agent_model = ClaudeSonnet4(
    model_settings=pydantic_ai.settings.ModelSettings(
        temperature=0.2,
        parallel_tool_calls=False,
    )
)


onboarding_agent = pydantic_ai.Agent(
    model=agent_model.model,
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

    onboarding_fields = [
        "preferred_name",
        "country",
        "communication_style",
        "response_speed",
    ]

    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

    if user_metadata:
        if user_metadata.preferred_name:
            onboarding_fields.remove("preferred_name")

        if user_metadata.country:
            onboarding_fields.remove("country")

        if user_metadata.communication_style:
            onboarding_fields.remove("communication_style")

        if user_metadata.response_speed:
            onboarding_fields.remove("response_speed")

    prompt = BaseChatPromptTemplate(
        response=RESPONSE_PROMPT.format(response_restrictions=restrict_response_text),
        message=MESSAGE_FOR_USER_PROMPT.format(important_message_for_user=ctx.deps.notification.content)
        if ctx.deps.notification
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

    if field not in ONBOARDING_FIELDS:
        raise MetadataFieldUpdateError(field, f"Field {field} is invalid.")

    update_instruction = f"Update {field} to value: {value_to_save}."

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

        update_instruction += f"\nUpdate timezone to value: {tz_value}."

        if has_multiple:
            async with async_database() as db_conn:
                await Notifications.add(
                    db_conn,
                    chat_id=ctx.deps.tg_chat_id,
                    content=(
                        f"There are multiple timezones for the user's country {value_to_save}. "
                        f"The default has been picked as {tz_value}. "
                        "Inform the user of this and that they may change their timezone via the `/settings` command."
                    ),
                    priority=1,
                )

    update = await run_agent_with_tracking(
        settings_agent,
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        run_kwargs={
            "user_prompt": update_instruction,
            "deps": SettingsAgentDependencies(
                tg_chat_id=ctx.deps.tg_chat_id,
                tg_session_id=ctx.deps.tg_session_id,
            ),
        },
    )
    update_outcome: SettingsUpdateResponse = update.output

    if not update_outcome.completed:
        raise MetadataFieldUpdateError(field, f"Error updating {field}: {update_outcome.feedback}.")

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

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content="Marked the user's onboarding as complete.",
    )

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

    if ctx.deps.notification:
        await check_special_instructions(
            response=data,
            chat_id=ctx.deps.tg_chat_id,
            session_id=ctx.deps.tg_session_id,
            instruction=ctx.deps.notification.content,
        )

    return data
