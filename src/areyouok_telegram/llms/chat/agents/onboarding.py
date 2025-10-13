"""Onboarding agent for new user initialization."""

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
from typing import Any
from typing import Literal

import pydantic_ai
from pydantic_ai import RunContext

from areyouok_telegram.data import GuidedSessions
from areyouok_telegram.data import Notifications
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.agent_country_timezone import CountryTimezone
from areyouok_telegram.llms.agent_country_timezone import country_timezone_agent
from areyouok_telegram.llms.agent_preferences import PreferencesAgentDependencies
from areyouok_telegram.llms.agent_preferences import PreferencesUpdateResponse
from areyouok_telegram.llms.agent_preferences import preferences_agent
from areyouok_telegram.llms.chat.agents.tools import search_history_impl
from areyouok_telegram.llms.chat.agents.tools import update_memory_impl
from areyouok_telegram.llms.chat.constants import MESSAGE_FOR_USER_PROMPT
from areyouok_telegram.llms.chat.constants import ONBOARDING_FIELDS
from areyouok_telegram.llms.chat.constants import ONBOARDING_OBJECTIVES
from areyouok_telegram.llms.chat.constants import RESPONSE_PROMPT
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import KeyboardResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.utils import check_restricted_responses
from areyouok_telegram.llms.chat.utils import check_special_instructions
from areyouok_telegram.llms.chat.utils import validate_response_data
from areyouok_telegram.llms.context_search import search_chat_context
from areyouok_telegram.llms.exceptions import CompleteOnboardingError
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import Gemini25Pro
from areyouok_telegram.llms.utils import log_metadata_update_context
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | DoNothingResponse | KeyboardResponse


@dataclass
class OnboardingAgentDependencies:
    """Dependencies for the onboarding agent."""

    tg_bot_id: str
    tg_chat_id: str
    tg_session_id: str
    onboarding_session_key: str
    restricted_responses: set[Literal["text", "reaction", "switch_personality"]] = field(default_factory=set)
    notification: Notifications | None = None

    def to_dict(self) -> dict:
        return {
            "tg_bot_id": self.tg_bot_id,
            "tg_chat_id": self.tg_chat_id,
            "tg_session_id": self.tg_session_id,
            "onboarding_session_key": self.onboarding_session_key,
            "restricted_responses": list(self.restricted_responses),
            "notification_content": self.notification.content if self.notification else None,
        }


agent_model = Gemini25Pro()


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
    value_to_save: str,
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
        preferences_agent,
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        run_kwargs={
            "user_prompt": update_instruction,
            "deps": PreferencesAgentDependencies(
                tg_chat_id=ctx.deps.tg_chat_id,
                tg_session_id=ctx.deps.tg_session_id,
            ),
        },
    )
    update_outcome: PreferencesUpdateResponse = update.output

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


@onboarding_agent.tool
async def terminate_onboarding(ctx: RunContext[OnboardingAgentDependencies]) -> str:
    """Stop the user's onboarding without marking it as complete."""
    async with async_database() as db_conn:
        try:
            onboarding = await GuidedSessions.get_by_guided_session_key(
                db_conn, guided_session_key=ctx.deps.onboarding_session_key
            )
        except Exception as e:
            raise CompleteOnboardingError(e) from e

        if not onboarding.is_active:
            raise CompleteOnboardingError(f"Onboarding session is currently {onboarding.state}.")  # noqa: TRY003

        await onboarding.inactivate(db_conn, timestamp=datetime.now(UTC))

    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content="Stopped the user's onboarding without completing.",
    )

    return "Onboarding terminated successfully."


@onboarding_agent.tool
async def search_past_conversations(
    ctx: RunContext[OnboardingAgentDependencies],
    search_query: str,
) -> str:
    """
    Search past conversations for relevant context using semantic search.

    Use this when you need to recall specific topics, emotions, events, or patterns
    from previous conversations with this user. This helps maintain continuity and
    shows the user you remember important details from your relationship.

    Args:
        search_query: Natural language query describing what to search for
                     (e.g., "times user felt anxious about work", "user's goals")

    Returns:
        A formatted response with direct answer and context summary, or error message
    """
    try:
        result = await search_chat_context(
            chat_id=ctx.deps.tg_chat_id,
            session_id=ctx.deps.tg_session_id,
            search_query=search_query,
        )
    except Exception as e:
        return f"Unable to search past conversations: {str(e)}"
    else:
        return result


@onboarding_agent.tool
async def update_memory(
    ctx: RunContext[OnboardingAgentDependencies],
    information_to_remember: str,
) -> str:
    """
    Update your memory bank with new information about the user that you want to remember.
    """
    return await update_memory_impl(ctx.deps, information_to_remember)


@onboarding_agent.tool
async def search_history(
    ctx: RunContext[OnboardingAgentDependencies],
    search_query: str,
) -> str:
    """
    Search history for relevant context using semantic search.

    Use this when you need to recall specific topics, emotions, events, or patterns
    from previous conversations with this user. This helps maintain continuity and
    shows the user you remember important details from your relationship.

    Args:
        search_query: Natural language query describing what to search for. The query should be
        phrased from a 3rd-party perspective and pronoun-neutral.
                    (e.g., "times user felt anxious about work", "user's goals")

    Returns:
        A formatted response with direct answer and context summary, or error message
    """
    return await search_history_impl(ctx.deps, search_query)


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
        bot_id=ctx.deps.tg_bot_id,
    )

    if ctx.deps.notification:
        await check_special_instructions(
            response=data,
            chat_id=ctx.deps.tg_chat_id,
            session_id=ctx.deps.tg_session_id,
            instruction=ctx.deps.notification.content,
        )

    return data
