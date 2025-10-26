from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import logfire
import pydantic_ai
from pydantic_ai import RunContext

from areyouok_telegram.config import SIMULATION_MODE
from areyouok_telegram.data.models import Context, ContextType, UserMetadata
from areyouok_telegram.llms.agent_anonymizer import anonymization_agent
from areyouok_telegram.llms.chat.constants import (
    MESSAGE_FOR_USER_PROMPT,
    PERSONALITY_PROMPT,
    PERSONALITY_SWITCH_INSTRUCTIONS,
    RESPONSE_PROMPT,
    RESTRICT_KEYBOARD_RESPONSE,
    RESTRICT_PERSONALITY_SWITCH,
    RESTRICT_REACTION_RESPONSE,
    RESTRICT_TEXT_RESPONSE,
    USER_PREFERENCES,
    USER_PROFILE,
)
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.chat.responses import (
    DoNothingResponse,
    KeyboardResponse,
    ReactionResponse,
    SwitchPersonalityResponse,
    TextResponse,
)
from areyouok_telegram.llms.chat.utils import (
    CommonChatAgentDependencies,
    check_restricted_responses,
    check_special_instructions,
    validate_response_data,
)
from areyouok_telegram.llms.context_search import search_chat_context
from areyouok_telegram.llms.exceptions import ContextSearchError, MemoryUpdateError, MetadataFieldUpdateError
from areyouok_telegram.llms.models import Gemini25Pro
from areyouok_telegram.llms.utils import log_metadata_update_context, run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse | KeyboardResponse


@dataclass
class ChatAgentDependencies(CommonChatAgentDependencies):
    """Context data passed to the LLM agent for making decisions."""

    personality: str = PersonalityTypes.COMPANIONSHIP.value

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "personality": self.personality,
        }


agent_model = Gemini25Pro()

chat_agent = pydantic_ai.Agent(
    model=agent_model.model,
    output_type=AgentResponse,
    deps_type=ChatAgentDependencies,
    name="areyouok_chat_agent",
    end_strategy="exhaustive",
    retries=3,
)


@chat_agent.instructions
async def instructions_with_personality_switch(ctx: pydantic_ai.RunContext[ChatAgentDependencies]) -> str:
    if SIMULATION_MODE:
        user_metadata = None
    else:
        user_metadata = await UserMetadata.get_by_user_id(user_id=ctx.deps.user.id)

    personality = PersonalityTypes.get_by_value(ctx.deps.personality)
    personality_text = personality.prompt_text()

    restrict_response_text = ""

    if "text" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_TEXT_RESPONSE
        restrict_response_text += "\n"

    if "keyboard" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_KEYBOARD_RESPONSE
        restrict_response_text += "\n"

    if "reaction" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_REACTION_RESPONSE
        restrict_response_text += "\n"

    if "switch_personality" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_PERSONALITY_SWITCH
        restrict_response_text += "\n"

    if user_metadata:
        user_preferences_text = USER_PREFERENCES.format(
            preferred_name=user_metadata.preferred_name or "Not provided.",
            country=user_metadata.country or "Not provided.",
            timezone=user_metadata.timezone or "Not provided.",
            communication_style=user_metadata.communication_style or "",
        )
    else:
        user_preferences_text = ""

    # Fetch the latest profile for this chat
    user_profile_text = ""
    if not SIMULATION_MODE:
        try:
            profile_contexts = await Context.get_by_chat(
                chat=ctx.deps.chat,
                ctype=ContextType.PROFILE.value,
            )
            if profile_contexts:
                user_profile = profile_contexts[0]  # Most recent
                user_profile_text = USER_PROFILE.format(user_profile=user_profile.content)

        except Exception as e:
            # If profile fetch fails, just continue without it
            logfire.warning(
                "Failed to fetch user profile, continuing without it",
                chat_id=ctx.deps.chat.id,
                error=str(e),
                _exc_info=True,
            )

    prompt = BaseChatPromptTemplate(
        response=RESPONSE_PROMPT.format(response_restrictions=restrict_response_text),
        message=MESSAGE_FOR_USER_PROMPT.format(important_message_for_user=ctx.deps.notification.content)
        if ctx.deps.notification
        else None,
        personality=PERSONALITY_PROMPT.format(
            personality_text=personality_text,
            personality_switch_instructions=PERSONALITY_SWITCH_INSTRUCTIONS
            if "switch_personality" not in ctx.deps.restricted_responses
            else None,
        ),
        user_preferences=user_preferences_text,
        user_profile=user_profile_text,
    )
    return prompt.as_prompt_string()


@chat_agent.output_validator
async def validate_agent_response(
    ctx: pydantic_ai.RunContext[ChatAgentDependencies], data: AgentResponse
) -> AgentResponse:
    check_restricted_responses(
        response=data,
        restricted=ctx.deps.restricted_responses,
    )

    if SIMULATION_MODE:
        # In simulation mode, skip database-dependent validations
        return data

    await validate_response_data(
        response=data,
        chat=ctx.deps.chat,
        bot_id=ctx.deps.bot_id,
    )

    if ctx.deps.notification:
        await check_special_instructions(
            response=data,
            chat=ctx.deps.chat,
            session=ctx.deps.session,
            instruction=ctx.deps.notification.content,
        )

    return data


@chat_agent.tool
async def get_current_time(ctx: RunContext[ChatAgentDependencies]) -> str:
    """
    Get the current time in the user's timezone, if the user has set their timezone.
    This can be used to make the conversation more contextually relevant by being time-aware.

    e.g. In the day time, the user may be working or busy. In the evening, the user may be winding down.
    """
    user_metadata = await UserMetadata.get_by_user_id(user_id=ctx.deps.user.id)

    if user_metadata and user_metadata.timezone and user_metadata.timezone != "rather_not_say":
        try:
            current_time = datetime.now(ZoneInfo(user_metadata.timezone)).strftime("%Y-%m-%d %H:%M %Z")
        except ZoneInfoNotFoundError:
            pass
        else:
            return f"Current time in the user's timezone ({user_metadata.timezone}): {current_time}."

    return "The user's timezone is not set or invalid, so the current time cannot be determined."


@chat_agent.tool
async def update_communication_style(
    ctx: RunContext[ChatAgentDependencies],
    new_communication_style: str,
) -> str:
    """
    Update the user's preferred communication style as you learn more about the user.
    This should only be used for long-lasting preferences over in-the-moment changes in needs/demands.

    Text will be anonymized before being updated in the database.
    """

    anon_text = await run_agent_with_tracking(
        anonymization_agent,
        chat=ctx.deps.chat,
        session=ctx.deps.session,
        run_kwargs={
            "user_prompt": new_communication_style,
        },
    )

    try:
        user_metadata = await UserMetadata.get_by_user_id(user_id=ctx.deps.user.id)
        if not user_metadata:
            user_metadata = UserMetadata(user_id=ctx.deps.user.id)

        user_metadata.communication_style = anon_text.output
        await user_metadata.save()

    except Exception as e:
        raise MetadataFieldUpdateError("communication_style", str(e)) from e

    # Log the metadata update to context
    await log_metadata_update_context(
        chat=ctx.deps.chat,
        session=ctx.deps.session,
        content=f"Updated usermeta: communication_style is now {str(anon_text.output)}",
    )

    return f"User's new communication_style updated to: {anon_text.output}."


@chat_agent.tool
async def update_response_speed(
    ctx: RunContext[ChatAgentDependencies],
    response_speed_adjustment: Literal["faster", "slower"],
) -> str:
    """
    Adjust the agent's response speed as you learn more about the user.
    This tool may be used to granularly adjust the agent's response speed by one step faster or slower.
    """

    try:
        user_metadata = await UserMetadata.get_by_user_id(user_id=ctx.deps.user.id)
        if not user_metadata:
            user_metadata = UserMetadata(user_id=ctx.deps.user.id)

        current_response_speed_adj = user_metadata.response_speed_adj or 0

        if response_speed_adjustment == "faster":
            user_metadata.response_speed_adj = max(current_response_speed_adj - 1, -1)
        else:
            user_metadata.response_speed_adj = current_response_speed_adj + 1

        await user_metadata.save()

    except Exception as e:
        raise MetadataFieldUpdateError("response_speed_adj", str(e)) from e

    # Log the metadata update to context
    await log_metadata_update_context(
        chat=ctx.deps.chat,
        session=ctx.deps.session,
        content=f"Updated usermeta: adjusted response speed {response_speed_adjustment}.",
    )

    return f"Made response speed {response_speed_adjustment}."


@chat_agent.tool
async def update_memory(
    ctx: RunContext[ChatAgentDependencies],
    information_to_remember: str,
) -> str:
    """
    Update your memory bank with new information about the user that you want to remember.
    """
    try:
        context = Context(
            chat=ctx.deps.chat,
            session_id=ctx.deps.session.id,
            type=ContextType.MEMORY.value,
            content=information_to_remember,
        )
        await context.save()

    except Exception as e:
        raise MemoryUpdateError(information_to_remember, e) from e

    return f"Information committed to memory: {information_to_remember}."


@chat_agent.tool
async def search_history(
    ctx: RunContext[ChatAgentDependencies],
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
    try:
        result = await search_chat_context(
            chat=ctx.deps.chat,
            session=ctx.deps.session,
            search_query=search_query,
        )
    except Exception as e:
        raise ContextSearchError(search_query, e) from e
    else:
        return result
