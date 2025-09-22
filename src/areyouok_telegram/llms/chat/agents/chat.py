from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

import pydantic_ai
from pydantic_ai import RunContext
from telegram.ext import ContextTypes

from areyouok_telegram.data import Notifications
from areyouok_telegram.data import UserMetadata
from areyouok_telegram.data import async_database
from areyouok_telegram.llms.agent_anonymizer import anonymization_agent
from areyouok_telegram.llms.chat.constants import MESSAGE_FOR_USER_PROMPT
from areyouok_telegram.llms.chat.constants import PERSONALITY_PROMPT
from areyouok_telegram.llms.chat.constants import PERSONALITY_SWITCH_INSTRUCTIONS
from areyouok_telegram.llms.chat.constants import RESPONSE_PROMPT
from areyouok_telegram.llms.chat.constants import RESTRICT_PERSONALITY_SWITCH
from areyouok_telegram.llms.chat.constants import RESTRICT_TEXT_RESPONSE
from areyouok_telegram.llms.chat.constants import USER_PREFERENCES
from areyouok_telegram.llms.chat.personalities import PersonalityTypes
from areyouok_telegram.llms.chat.prompt import BaseChatPromptTemplate
from areyouok_telegram.llms.chat.responses import DoNothingResponse
from areyouok_telegram.llms.chat.responses import KeyboardResponse
from areyouok_telegram.llms.chat.responses import ReactionResponse
from areyouok_telegram.llms.chat.responses import SwitchPersonalityResponse
from areyouok_telegram.llms.chat.responses import TextResponse
from areyouok_telegram.llms.chat.utils import check_restricted_responses
from areyouok_telegram.llms.chat.utils import check_special_instructions
from areyouok_telegram.llms.chat.utils import validate_response_data
from areyouok_telegram.llms.exceptions import MetadataFieldUpdateError
from areyouok_telegram.llms.models import Gemini25Pro
from areyouok_telegram.llms.utils import log_metadata_update_context
from areyouok_telegram.llms.utils import run_agent_with_tracking

AgentResponse = TextResponse | ReactionResponse | SwitchPersonalityResponse | DoNothingResponse | KeyboardResponse


@dataclass
class ChatAgentDependencies:
    """Context data passed to the LLM agent for making decisions."""

    tg_context: ContextTypes.DEFAULT_TYPE
    tg_chat_id: str
    tg_session_id: str
    personality: str = PersonalityTypes.EXPLORATION.value
    restricted_responses: set[Literal["text", "reaction", "switch_personality"]] = field(default_factory=set)
    notification: Notifications | None = None

    def to_dict(self) -> dict:
        return {
            "tg_chat_id": self.tg_chat_id,
            "tg_session_id": self.tg_session_id,
            "personality": self.personality,
            "restricted_responses": list(self.restricted_responses),
            "notification_content": self.notification.content if self.notification else None,
        }


agent_model = Gemini25Pro(model_settings=pydantic_ai.models.google.GoogleModelSettings(temperature=0.5))

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
    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

    personality = PersonalityTypes.get_by_value(ctx.deps.personality)
    personality_text = personality.prompt_text()

    restrict_response_text = ""

    if "text" in ctx.deps.restricted_responses:
        restrict_response_text += RESTRICT_TEXT_RESPONSE
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


@chat_agent.tool
async def get_current_time(ctx: RunContext[ChatAgentDependencies]) -> str:
    """
    Get the current time in the user's timezone, if the user has set their timezone.
    This can be used to make the conversation more contextually relevant by being time-aware.

    e.g. In the day time, the user may be working or busy. In the evening, the user may be winding down.
    """
    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

    if user_metadata.timezone and user_metadata.timezone != "rather_not_say":
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
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        run_kwargs={
            "user_prompt": new_communication_style,
        },
    )

    async with async_database() as db_conn:
        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="communication_style",
                value=anon_text.output,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("communication_style", str(e)) from e

    # Log the metadata update to context
    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
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

    async with async_database() as db_conn:
        user_metadata = await UserMetadata.get_by_user_id(db_conn, user_id=ctx.deps.tg_chat_id)

        current_response_speed_adj = (user_metadata.response_speed_adj if user_metadata else 0) or 0

        if response_speed_adjustment == "faster":
            new_speed_adj = max(current_response_speed_adj - 1, -1)
        else:
            new_speed_adj = current_response_speed_adj + 1

        try:
            await UserMetadata.update_metadata(
                db_conn,
                user_id=ctx.deps.tg_chat_id,
                field="response_speed_adj",
                value=new_speed_adj,
            )

        except Exception as e:
            raise MetadataFieldUpdateError("response_speed_adj", str(e)) from e

    # Log the metadata update to context
    await log_metadata_update_context(
        chat_id=ctx.deps.tg_chat_id,
        session_id=ctx.deps.tg_session_id,
        content=f"Updated usermeta: adjusted response speed {response_speed_adjustment}.",
    )

    return f"Made response speed {response_speed_adjustment}."
